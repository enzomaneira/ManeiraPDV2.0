# =============================================================================
#  image_service.py  —  Fotos do cardápio: valida, ajusta e envia ao Cloudflare R2
# =============================================================================
#
#  A Keeta exige fotos JPG/PNG de pelo menos 600×450 px e menos de 5 MB, de
#  preferência 4:3. O lojista envia a foto como estiver (celular, PNG etc.) e
#  aqui ela é ajustada para esse padrão antes de ir para o R2:
#    - corrige a rotação do celular (EXIF) e remove metadados (inclusive GPS);
#    - fundo branco em PNG transparente;
#    - recorte central em 4:3 e redução para no máximo 1200×900;
#    - JPEG progressivo com menos de ~1 MB.
#  Fotos menores que 600×450 são recusadas (aumentar a imagem só a borra).
#
#  Variáveis (Railway → Backend): R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
#  R2_SECRET_ACCESS_KEY, R2_BUCKET e R2_PUBLIC_BASE_URL (ex.: https://pub-xxxx.r2.dev).
#  Sem elas o upload responde que não está configurado; o resto do PDV funciona.
# =============================================================================

import hashlib
import io
import os
import re
import unicodedata

from PIL import Image, ImageOps, UnidentifiedImageError

MIN_WIDTH, MIN_HEIGHT = 600, 450
MAX_WIDTH, MAX_HEIGHT = 1200, 900
TARGET_RATIO = 4 / 3
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageRejected(ValueError):
    """Foto que não pode ser usada; a mensagem é mostrada ao lojista."""


class StorageNotConfigured(RuntimeError):
    pass


def r2_configured() -> bool:
    return all(os.getenv(name) for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE_URL"))


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "foto"


def process_image(data: bytes) -> dict:
    """Valida e ajusta a foto. Retorna os bytes JPEG finais e o que foi alterado."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected(f"A foto tem {len(data) / 1024 / 1024:.1f} MB; o limite de envio é 15 MB.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except Image.DecompressionBombError:
        raise ImageRejected("A imagem é grande demais para ser processada.")
    except (UnidentifiedImageError, OSError, SyntaxError):
        if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
            raise ImageRejected("Fotos HEIC (iPhone) não são aceitas. Envie em JPG ou PNG "
                                "(no iPhone: Ajustes > Câmera > Formatos > Mais Compatível).")
        raise ImageRejected("O arquivo não é uma imagem válida. Envie uma foto JPG, PNG ou WebP.")

    original_format = image.format
    if original_format not in ACCEPTED_FORMATS:
        raise ImageRejected(f"Formato {original_format or 'desconhecido'} não aceito. Envie JPG, PNG ou WebP.")

    original_size = image.size
    changes = []

    # Celulares gravam a foto "deitada" e marcam a rotação no EXIF (tag 0x0112).
    if image.getexif().get(0x0112, 1) != 1:
        changes.append("rotação corrigida")
    image = ImageOps.exif_transpose(image)

    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        if rgba.getchannel("A").getextrema()[0] < 255:
            changes.append("fundo transparente trocado por branco")
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        raise ImageRejected(f"A foto tem {width}×{height} px; o mínimo é {MIN_WIDTH}×{MIN_HEIGHT} px. "
                            "Envie uma foto maior (aumentar a imagem deixaria ela borrada).")

    # Recorte central em 4:3
    if abs(width / height - TARGET_RATIO) > 0.01:
        if width / height > TARGET_RATIO:
            new_width = round(height * TARGET_RATIO)
            left = (width - new_width) // 2
            box = (left, 0, left + new_width, height)
        else:
            new_height = round(width / TARGET_RATIO)
            top = (height - new_height) // 2
            box = (0, top, width, top + new_height)
        image = image.crop(box)
        changes.append("recortada no formato 4:3 (centro da foto)")
        width, height = image.size
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            raise ImageRejected(f"Depois do recorte em 4:3 a foto fica com {width}×{height} px; o mínimo é "
                                f"{MIN_WIDTH}×{MIN_HEIGHT} px. Envie uma foto maior ou mais próxima do formato 4:3.")

    if width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)
        changes.append(f"reduzida para {MAX_WIDTH}×{MAX_HEIGHT} px")

    for quality in (88, 82, 76, 70, 64, 58):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
        output = buffer.getvalue()
        if len(output) <= MAX_OUTPUT_BYTES:
            break
    if original_format != "JPEG":
        changes.append(f"convertida de {original_format} para JPG")

    return {
        "bytes": output,
        "width": image.size[0],
        "height": image.size[1],
        "originalWidth": original_size[0],
        "originalHeight": original_size[1],
        "originalFormat": original_format,
        "sizeKb": round(len(output) / 1024),
        "changes": changes,
    }


def upload_to_r2(data: bytes, store_id: int, name: str) -> str:
    """Envia o JPEG ao bucket e devolve a URL pública. O nome inclui o hash do
    conteúdo: reenviar a mesma foto gera a mesma URL e nada é sobrescrito."""
    if not r2_configured():
        raise StorageNotConfigured()
    import boto3  # import tardio: o PDV funciona sem o upload configurado

    digest = hashlib.sha256(data).hexdigest()[:12]
    key = f"restaurante/{store_id}/produtos/{_slug(name)}-{digest}.jpg"
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )
    client.put_object(
        Bucket=os.getenv("R2_BUCKET"), Key=key, Body=data,
        ContentType="image/jpeg", CacheControl="public, max-age=31536000, immutable",
    )
    return f"{os.getenv('R2_PUBLIC_BASE_URL').rstrip('/')}/{key}"

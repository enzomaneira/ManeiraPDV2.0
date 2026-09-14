# =============================================================================
#  keeta_client.py  —  Integração com a Keeta Open Delivery API
# =============================================================================
#
#  Este arquivo centraliza TODA a comunicação com a Keeta.
#  Cada função representa uma chamada de API diferente.
#
#  Fluxo geral:
#    1. get_access_token()     →  autentica e obtém o Bearer Token
#    2. _generate_signature()  →  assina cada requisição com HMAC-SHA256
#    3. Funções de pedido      →  confirm, ready, dispatch, cancel
#    4. Funções de loja        →  onboarding, status, auth URL
# =============================================================================

import hmac
import hashlib
import base64
import time
import requests
import json
import os
import rfc8785
import uuid
import traceback
from datetime import datetime

# -----------------------------------------------------------------------------
#  CREDENCIAIS (em produção, use variáveis de ambiente)
# -----------------------------------------------------------------------------
CLIENT_ID     = os.getenv("KEETA_CLIENT_ID", "2816859805")
CLIENT_SECRET = os.getenv("KEETA_CLIENT_SECRET", "2f6729bdd4be467aa15df35244f2a65e")

# Base da API da Keeta. O host precisa ser o mesmo host usado na URL HTTP
# e na string da assinatura. Em algumas contas/regiões a Keeta usa o host
# `open-eu.mykeeta.com`; deixar isso configurável evita assinar `open.mykeeta.com`
# e enviar a requisição para outro host.
BASE_URL = os.getenv(
    "KEETA_BASE_URL",
    "https://open-eu.mykeeta.com/api/open/opendelivery",
).rstrip("/")

# A Keeta valida a assinatura usando o host global documentado, mesmo quando
# a requisição HTTP é enviada pelo endpoint regional open-eu.mykeeta.com.
# Pode ser sobrescrito caso a conta/região tenha uma regra diferente.
SIGNATURE_BASE_URL = os.getenv(
    "KEETA_SIGNATURE_BASE_URL",
    "https://open.mykeeta.com/api/open/opendelivery",
).rstrip("/")

# apiKey usada para proteger o NOSSO endpoint GET /merchant (GET /api/keeta/menu).
# É registrada no onboarding (getMerchantURL.apiKey) e a Keeta passa a enviar
# esse mesmo valor no header X-API-KEY em toda chamada futura a esse endpoint.
# Mantida centralizada aqui para que register_merchant() e a validação da
# rota (routes/keeta_webhook.py) nunca fiquem dessincronizadas.
MERCHANT_MENU_API_KEY = os.getenv("MERCHANT_MENU_API_KEY", "123456")

# Timeout (em segundos) para TODAS as chamadas HTTP feitas à Keeta.
#
# IMPORTANTE: sem um timeout explícito, a biblioteca `requests` espera
# INDEFINIDAMENTE por uma resposta. Isso é extremamente perigoso no fluxo do
# webhook: se a Keeta (ou a rede) demorar/travar, o worker do Gunicorn que
# está processando o webhook fica preso para sempre, nunca respondendo 200
# para a Keeta. Como resultado, a Keeta entende que o webhook falhou
# ("Failed" / "Unknown Protocol" — a conexão é derrubada pelo proxy antes de
# terminar) e reenvia o MESMO evento repetidamente em loop (a cada ~12s),
# esgotando os workers disponíveis.
#
# (connect_timeout, read_timeout) — generosos o suficiente para não afetar
# operação normal, mas curtos o suficiente para nunca travar um worker.
REQUEST_TIMEOUT = (5, 15)

# Identificador do merchant gerado pelo nosso sistema e usado no onboarding
# (query merchantId), no body keetaMerchantId e no path merchantUpdate.
INTERNAL_MERCHANT_ID = os.getenv("INTERNAL_MERCHANT_ID", "159633716").strip()

# Alias legado mantido para compatibilidade com integrações antigas. O fluxo
# atual deve usar INTERNAL_MERCHANT_ID ou o valor persistido após o onboarding.
KEETA_MERCHANT_ID = INTERNAL_MERCHANT_ID

MERCHANT_UPDATE_ENTITY_TYPES = frozenset({
    "MERCHANT",
    "BASIC_INFO",
    "SERVICE",
    "MENU",
    "CATEGORY",
    "ITEM",
    "ITEM_OFFER",
    "OPTION_GROUP",
    "OPTION",
    "AVAILABILITY",
})

# URL pública do backend — usada no onboarding para informar à Keeta:
#   - onde fazer POST dos eventos de pedido (webhook)
#   - onde fazer GET do cardápio (menu endpoint)
#
# No Railway: já está configurada via variável de ambiente MY_PUBLIC_URL
#   (ver backend/.env): https://backend-production-818f.up.railway.app/api/keeta
#
# Localmente com ngrok: defina MY_PUBLIC_URL no seu .env local com a URL do ngrok.
#
# O fallback abaixo é a própria URL de produção do backend no Railway, para
# nunca cairmos em um placeholder inválido caso a env var não esteja setada.
_PRODUCTION_URL_FALLBACK = "https://backend-production-818f.up.railway.app/api/keeta"
MY_PUBLIC_URL = os.getenv("MY_PUBLIC_URL", _PRODUCTION_URL_FALLBACK)

# --- Proteção extra: se a variável de ambiente estiver configurada no Railway
# com um valor placeholder esquecido (ex: "SEU-BACKEND"), ignoramos o valor da
# env var e usamos a URL de produção correta, para nunca enviar um webhook
# quebrado no onboarding da Keeta.
if "SEU-BACKEND" in MY_PUBLIC_URL or "seu-backend" in MY_PUBLIC_URL.lower():
    print(f"[Keeta][INIT] AVISO: MY_PUBLIC_URL contém um placeholder inválido ('{MY_PUBLIC_URL}'). "
          f"Corrija a variável de ambiente no Railway! Usando fallback de produção por segurança.")
    MY_PUBLIC_URL = _PRODUCTION_URL_FALLBACK

# Normalização: remove sufixos de rota que podem ter sido incluídos por engano
# na env var. MY_PUBLIC_URL deve ser a raiz do blueprint (/api/keeta), sem
# /orders, /menu etc. Caso contrário as URLs ficam quebradas como:
#   .../api/keeta/orders/menu   (invés de .../api/keeta/menu)
#   .../api/keeta/orders/orders (invés de .../api/keeta/orders)
_original = MY_PUBLIC_URL
MY_PUBLIC_URL = MY_PUBLIC_URL.rstrip("/")  # remove trailing slash
for _suffix in ("/onboard", "/store-status", "/authorization", "/orders", "/menu"):
    if MY_PUBLIC_URL.endswith(_suffix):
        MY_PUBLIC_URL = MY_PUBLIC_URL[:-len(_suffix)]
        print(f"[Keeta][INIT] CORRIGIDO: removido sufixo '{_suffix}' de MY_PUBLIC_URL. "
              f"Antes='{_original}' → Depois='{MY_PUBLIC_URL}'. Corrija a env var no Railway!")
        break

print(f"[Keeta][INIT] Módulo keeta_client carregado | BASE_URL={BASE_URL} | MY_PUBLIC_URL={MY_PUBLIC_URL} | CLIENT_ID={CLIENT_ID}")

# -----------------------------------------------------------------------------
#  CACHE DO TOKEN
#  A Keeta gera tokens com validade de ~5h. Guardamos em memória para não
#  ficar fazendo login a cada requisição.
# -----------------------------------------------------------------------------
_cached_token = None
_token_expires_at = 0  # timestamp UNIX de quando o token expira


def merchant_uuid(store_id) -> str:
    """
    Gera o `id` do Merchant no formato exigido pelo schema oficial da Keeta
    (GET /v1/merchant): string de 36 a 100 caracteres, único por loja.

    IMPORTANTE: nosso `store.id` no banco é só um Integer autoincrement
    (ex: "1", "2"...), que tem só 1-2 caracteres — MUITO abaixo do mínimo
    de 36 exigido pelo schema (`id: string, minLength: 36, maxLength: 100`,
    required). Enviar um id curto pode fazer a Keeta rejeitar ou processar
    incorretamente o cardápio, mesmo que o GET retorne 200 OK.

    Para resolver isso sem precisar migrar o banco, geramos aqui um
    identificador estável e determinístico (sempre o mesmo para o mesmo
    store_id) com pelo menos 36 caracteres, prefixado com "store-" e
    preenchido com zeros à esquerda.

    Exemplo: store_id=1 → "store-00000000000000000000000000000001"
    """
    value = str(store_id)
    if value.startswith("store-") and len(value) >= 36:
        return value
    return f"store-{int(value):030d}"


# =============================================================================
#  1. AUTENTICAÇÃO
# =============================================================================

def get_access_token() -> str | None:
    """
    Obtém um App-Level Access Token da Keeta.

    Como funciona:
      - Faz POST /oauth/token com client_id, client_secret e grant_type
      - Retorna um Bearer Token que deve ser enviado no header de toda requisição
      - O token é cacheado por 4 horas para evitar chamadas desnecessárias

    Documentação: https://api-docs.mykeeta.com/apis/opendelivery/authentication
    """
    global _cached_token, _token_expires_at

    print(f"[Keeta][get_access_token] INÍCIO | token_em_cache={bool(_cached_token)} | expira_em={_token_expires_at} | agora={time.time()}")

    # Se o token ainda é válido, retorna o que está em cache
    if _cached_token and time.time() < _token_expires_at:
        print(f"[Keeta][get_access_token] Usando token cacheado | preview={_cached_token[:20]}... | válido por mais {_token_expires_at - time.time():.0f}s")
        return _cached_token

    print("[Keeta][get_access_token] Token expirado ou inexistente. Solicitando novo Access Token...")

    url = f"{BASE_URL}/oauth/token"

    # O body da requisição de autenticação
    payload = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "app_level_token",  # Modo App-Level (software level)
    }
    print(f"[Keeta][get_access_token] POST {url} | payload (secret oculto): {{'client_id': '{CLIENT_ID}', 'grant_type': 'app_level_token'}}")

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][get_access_token] Resposta recebida | status_code={response.status_code}")
        response.raise_for_status()

        data = response.json()
        _cached_token = data["access_token"]
        _token_expires_at = time.time() + (4 * 60 * 60)  # expira em 4 horas

        print(f"[Keeta][get_access_token] Novo token obtido com sucesso | preview={_cached_token[:20]}... | expira_em(unix)={_token_expires_at}")
        print("[Keeta][get_access_token] FIM (sucesso)")
        return _cached_token

    except Exception as e:
        print(f"[Keeta][get_access_token] ERRO ao obter token: {type(e).__name__}: {e}")
        print("[Keeta][get_access_token] FIM (falha)")
        return None


# =============================================================================
#  2. ASSINATURA (X-App-Signature)
# =============================================================================

def canonical_json(payload) -> str:
    """
    Serializa um dict em JSON "canônico", seguindo o espírito da RFC 8785
    (JSON Canonicalization Scheme) exigido pela Keeta para o cálculo da
    assinatura:

      - Chaves ordenadas alfabeticamente (recursivamente, em sub-objetos)
      - SEM espaços após ":" e "," (separators compactos)
      - Sem espaços/indentação extra

    Isso é crítico: o texto que vira `body` da requisição precisa ser
    EXATAMENTE igual (byte a byte) ao texto usado para calcular a assinatura.
    Se usarmos json.dumps(payload) "normal", o Python insere espaços
    (ex: '{"key": "value"}') e a Keeta rejeita com 401 Invalid signature.

    Retorna uma string vazia se payload for None.
    """
    if payload is None:
        return ""
    # Keeta explicitly requires RFC 8785 (JCS), not merely sorted keys and
    # compact separators. In particular, RFC 8785 defines canonical number
    # formatting, escaping, and Unicode handling.
    return rfc8785.dumps(payload).decode("utf-8")


def extract_merchant_id(payload) -> str | None:
    """Extrai com segurança `updatedObjects[0].id` de um payload de merchant.

    Aceita tanto um objeto Python quanto uma string JSON. Retorna None quando
    a estrutura não contém um ID válido; nunca altera o payload recebido.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return None

    if not isinstance(payload, dict):
        return None

    updated_objects = payload.get("updatedObjects")
    if not isinstance(updated_objects, list) or not updated_objects:
        return None

    first_object = updated_objects[0]
    if not isinstance(first_object, dict):
        return None

    merchant_id = first_object.get("id")
    if not isinstance(merchant_id, str) or not merchant_id.strip():
        return None

    return merchant_id.strip()


def _secret_fingerprint() -> str:
    """Returns a safe fingerprint for comparing the deployed secret."""
    return hashlib.sha256(CLIENT_SECRET.encode("utf-8")).hexdigest()[:12]


def _generate_signature(url: str, query_params: dict = None, body: str = None) -> str:
    """
    Gera a assinatura HMAC-SHA256 exigida pela Keeta.

    A string assinada é formada por:

      URL sem query string
      + "&" + parâmetros de query ordenados por nome (quando existirem)
      + "&" + body JSON canônico (quando não estiver vazio)

    O texto assinado precisa ser exatamente o mesmo texto enviado em ``data``;
    por isso os chamadores devem serializar o payload uma única vez com
    ``canonical_json`` e reutilizar essa string. Um body JSON válido como ``{}``
    também participa da assinatura; somente um body realmente ausente fica
    representado por uma string vazia.

    O merchantId do path não é descoberto a partir do body: ele vem do
    mapeamento local e deve ser definido antes de montar o payload. Se o body
    tiver ``updatedObjects[0].id``, ele é validado contra esse mesmo ID.

    O resultado é HMAC-SHA256 com CLIENT_SECRET, codificado em Base64.

    Documentação: https://api-docs.mykeeta.com/apis/opendelivery/signature-calculation
    """
    print(
        f"[Keeta][_generate_signature] INÍCIO | url={url} | "
        f"query_params={query_params} | body_len={len(body or '')} | "
        f"secret_fingerprint={_secret_fingerprint()}"
    )

    # A Keeta assina a URL base, sem a query string. O endpoint regional pode
    # ser usado no transporte, mas a documentação e a validação do servidor
    # usam o host global open.mykeeta.com por padrão.
    from urllib.parse import urlsplit

    request_url = urlsplit(url)
    signature_base = urlsplit(SIGNATURE_BASE_URL)
    base_url = request_url._replace(
        scheme=signature_base.scheme,
        netloc=signature_base.netloc,
        query="",
        fragment="",
    ).geturl()

    # Parâmetros de query DEVEM ser ordenados alfabeticamente. Não fazemos URL
    # encoding aqui: a especificação define a forma textual key=value usada na
    # string de assinatura.
    sorted_query_params = ""
    if query_params:
        sorted_query_params = "&".join(
            f"{key}={'' if query_params[key] is None else str(query_params[key])}"
            for key in sorted(query_params.keys())
        )

    # O body enviado pelo requests deve ser exatamente o body usado aqui.
    # Não use strip() nem remova `{}`: qualquer byte diferente altera o HMAC.
    # A implementação da Keeta usa apenas um separador quando não há query:
    # URL + "&" + body. Com query, os componentes são concatenados por `&`.
    request_body = body if body is not None else ""
    signature_parts = [base_url]
    if sorted_query_params:
        signature_parts.append(sorted_query_params)
    if request_body:
        signature_parts.append(request_body)
    string_to_sign = "&".join(signature_parts)
    print(
        f"[Keeta][_generate_signature] base_url={base_url} | "
        f"string_sha256={hashlib.sha256(string_to_sign.encode('utf-8')).hexdigest()} | "
        f"string_utf8_len={len(string_to_sign.encode('utf-8'))} | "
        f"body_utf8_len={len((body or '').encode('utf-8'))}"
    )

    # Calcula o HMAC-SHA256
    signature_bytes = hmac.new(
        key=CLIENT_SECRET.encode("utf-8"),
        msg=string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    # Codifica em Base64 e retorna como string
    signature = base64.b64encode(signature_bytes).decode("utf-8")
    print(
        f"[Keeta][_generate_signature] FIM | signature={signature} | "
        f"secret_fingerprint={_secret_fingerprint()}"
    )
    return signature


def _build_headers(url: str, query_params: dict = None, body: str = None) -> dict:
    """
    Monta o dicionário de headers padrão para qualquer chamada à Keeta.
    Inclui: Authorization (Bearer Token) + Content-Type + X-App-Signature
    """
    print(f"[Keeta][_build_headers] INÍCIO | url={url}")
    token = get_access_token()
    signature = _generate_signature(url, query_params, body)

    headers = {
        "Authorization":   f"Bearer {token}",
        "Content-Type":    "application/json; charset=utf-8",
        "X-App-Signature": signature,
    }
    print(f"[Keeta][_build_headers] FIM | headers montados (token oculto parcialmente): Authorization=Bearer {str(token)[:15]}... | X-App-Signature={signature[:15]}...")
    return headers


# =============================================================================
#  3. CHAMADAS DE PEDIDO (Order API)
# =============================================================================

def confirm_order(order_id: str) -> bool:
    """
    Confirma (aceita) um pedido na Keeta.

    Quando usar: quando o restaurante aceita o pedido do cliente.
    O pedido muda de estado: PLACED → CONFIRMED

    Endpoint: POST /v1/orders/{orderId}/confirm

    Campos obrigatórios no body (documentação oficial):
      - createdAt: UTC timestamp ISO (date-time, required)
      - orderExternalCode: código externo do pedido (string, required)
    """
    print(f"\n[Keeta][confirm_order] INÍCIO | order_id={order_id}")
    url = f"{BASE_URL}/v1/orders/{order_id}/confirm"

    # createdAt e orderExternalCode são REQUIRED segundo a doc da Keeta.
    # Enviar body vazio {} gera erro de assinatura ou validação.
    payload = {
        "createdAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "orderExternalCode": order_id,
    }
    body = canonical_json(payload)

    print(f"[Keeta][confirm_order] POST {url}")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][confirm_order] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][confirm_order] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][confirm_order] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][confirm_order] FIM (falha) | order_id={order_id}")
        return False


def notify_ready_for_pickup(order_id: str) -> bool:
    """
    Informa a Keeta que o pedido está pronto para retirada.

    Quando usar: quando a cozinha terminou de preparar o pedido.
    O pedido muda de estado: CONFIRMED → READY_FOR_PICKUP

    Endpoint: POST /v1/orders/{orderId}/readyForPickup
    (sem body obrigatório segundo a documentação)
    """
    print(f"\n[Keeta][notify_ready_for_pickup] INÍCIO | order_id={order_id}")
    url = f"{BASE_URL}/v1/orders/{order_id}/readyForPickup"
    body = ""  # sem body → não incluído na assinatura nem enviado

    print(f"[Keeta][notify_ready_for_pickup] POST {url}")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][notify_ready_for_pickup] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][notify_ready_for_pickup] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][notify_ready_for_pickup] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][notify_ready_for_pickup] FIM (falha) | order_id={order_id}")
        return False


def notify_dispatched(order_id: str) -> bool:
    """
    Informa a Keeta que o pedido saiu para entrega (despacho do motoboy).

    Quando usar: quando o entregador saiu com o pedido.
    O pedido muda de estado: READY_FOR_PICKUP → DISPATCHED

    Endpoint: POST /v1/orders/{orderId}/dispatch
    (sem body obrigatório segundo a documentação)
    """
    print(f"\n[Keeta][notify_dispatched] INÍCIO | order_id={order_id}")
    url = f"{BASE_URL}/v1/orders/{order_id}/dispatch"
    body = ""  # sem body → não incluído na assinatura nem enviado

    print(f"[Keeta][notify_dispatched] POST {url}")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][notify_dispatched] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][notify_dispatched] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][notify_dispatched] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][notify_dispatched] FIM (falha) | order_id={order_id}")
        return False


def request_cancellation(order_id: str, reason: str = "Dificuldades internas do restaurante") -> bool:
    """
    Solicita o cancelamento de um pedido na Keeta.

    Quando usar: quando o restaurante não consegue atender o pedido.

    Códigos válidos (code):
      SYSTEMIC_ISSUES, UNAVAILABLE_ITEM, OUTDATED_MENU,
      INTERNAL_DIFFICULTIES_OF_THE_RESTAURANT, etc.

    Endpoint: POST /v1/orders/{orderId}/requestCancellation
    """
    print(f"\n[Keeta][request_cancellation] INÍCIO | order_id={order_id} | reason='{reason}'")
    url = f"{BASE_URL}/v1/orders/{order_id}/requestCancellation"

    payload = {
        "reason": reason,
        "code":   "INTERNAL_DIFFICULTIES_OF_THE_RESTAURANT",
        "mode":   "MANUAL",
    }
    body = canonical_json(payload)
    print(f"[Keeta][request_cancellation] POST {url} | payload={payload} | body_canonico={body}")

    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][request_cancellation] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][request_cancellation] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][request_cancellation] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][request_cancellation] FIM (falha) | order_id={order_id}")
        return False


def get_order_details(order_id: str, order_url: str | None = None) -> dict | None:
    """
    Busca os detalhes completos de um pedido na Keeta.

    Retorna um dicionário com todos os dados do pedido:
    itens, cliente, endereço, valores, pagamento, etc.

    Endpoint: GET /v1/orders/{orderId}

    IMPORTANTE: sempre que um evento de webhook/polling for recebido, a Keeta
    já envia o campo `orderURL` — "The URL to get the order details" — dentro
    do próprio payload do evento. Por segurança e para seguir exatamente a
    documentação oficial, damos preferência a essa URL (order_url) em vez de
    montar `{BASE_URL}/v1/orders/{orderId}` manualmente.

    Se `order_url` não for informado (ex: chamadas antigas/manuais), caímos
    no fallback de montar a URL padrão a partir do order_id.
    """
    print(f"\n[Keeta][get_order_details] INÍCIO | order_id={order_id} | order_url_recebida={order_url}")

    # A orderURL vinda do evento da Keeta pode estar incompleta (sem o ID no
    # final). Verificamos se o order_id está presente na URL; se não estiver,
    # ignoramos a order_url e montamos a URL correta a partir do order_id.
    if order_url and order_id in order_url:
        url = order_url
        print(f"[Keeta][get_order_details] Usando orderURL vinda do evento: {url}")
    else:
        url = f"{BASE_URL}/v1/orders/{order_id}"
        if order_url:
            print(f"[Keeta][get_order_details] orderURL incompleta (não contém '{order_id}'). "
                  f"Usando fallback: {url}")
        else:
            print(f"[Keeta][get_order_details] orderURL não informada. Usando fallback: {url}")

    print(f"[Keeta][get_order_details] GET {url}")
    try:
        response = requests.get(url, headers=_build_headers(url), timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][get_order_details] Resposta | status_code={response.status_code}")
        response.raise_for_status()

        json_data = response.json()
        print(f"[Keeta][get_order_details] JSON cru recebido (chaves de topo): {list(json_data.keys())}")

        # A Keeta pode retornar o pedido diretamente, ou encapsulado em:
        #   {code, message, data: {pedido}, extend}
        # Nesse caso, o pedido real está dentro de `data`.
        order_data = json_data.get("data") or json_data
        print(f"[Keeta][get_order_details] Dados do pedido extraídos (chaves): {list(order_data.keys())}")
        _save_log(f"ORDER_{order_id}", order_data)
        print(f"[Keeta][get_order_details] FIM (sucesso) | order_id={order_id}")
        return order_data

    except Exception as e:
        print(f"[Keeta][get_order_details] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][get_order_details] FIM (falha) | order_id={order_id}")
        return None


# =============================================================================
#  4. CHAMADAS DE LOJA (Merchant API)
# =============================================================================

def register_merchant(merchant_id: str, my_local_store_id: str) -> dict | None:
    """
    Faz o onboarding da loja usando o mesmo identificador nos dois campos.

    `merchantId` na query string e `keetaMerchantId` no body representam o
    mesmo identificador interno fornecido pelo nosso sistema. O mesmo valor
    também é usado no path de `merchantUpdate/{merchantId}`. O ID real da
    loja na Keeta não deve ser usado nesse path.

    Endpoint: PUT /v1/merchantOnboarding?merchantId={merchant_id}
    """
    merchant_id = str(merchant_id).strip()
    local_store_id = str(my_local_store_id).strip()
    print(
        f"\n[Keeta][register_merchant] INÍCIO | merchant_id={merchant_id} | "
        f"my_local_store_id={local_store_id}"
    )

    if not merchant_id:
        print("[Keeta][register_merchant] FALHA: merchant_id não pode ser vazio.")
        return None
    if not local_store_id:
        print("[Keeta][register_merchant] FALHA: my_local_store_id não pode ser vazio.")
        return None

    url = f"{BASE_URL}/v1/merchantOnboarding"
    query_params = {"merchantId": merchant_id}
    try:
        merchant_id_number = int(merchant_id)
    except (TypeError, ValueError):
        print(f"[Keeta][register_merchant] FALHA: merchant_id='{merchant_id}' precisa ser numérico.")
        return None

    payload = {
        "getMerchantURL": {
            "baseURL": f"{MY_PUBLIC_URL}/menu?storeId={local_store_id}",
            "apiKey": MERCHANT_MENU_API_KEY,
        },
        "ordersWebhookURL": f"{MY_PUBLIC_URL}/orders",
        "keetaMerchantId": merchant_id_number,
    }
    body = canonical_json(payload)
    print(
        f"[Keeta][register_merchant] Payload montado | "
        f"merchantId(query)={merchant_id} | keetaMerchantId(body)={merchant_id} | "
        f"body_sha256={hashlib.sha256(body.encode('utf-8')).hexdigest()}"
    )

    full_url_with_params = f"{url}?merchantId={merchant_id}"
    print(f"[Keeta][register_merchant] PUT {full_url_with_params}")
    try:
        response = requests.put(
            full_url_with_params,
            headers=_build_headers(url, query_params=query_params, body=body),
            data=body,
            timeout=REQUEST_TIMEOUT,
        )
        print(
            f"[Keeta][register_merchant] Resposta | status_code={response.status_code} | "
            f"body={response.text[:500]}"
        )
        if response.status_code not in (200, 201, 204):
            print(f"[Keeta][register_merchant] FALHA HTTP | status_code={response.status_code}")
            return None
        resultado = response.json() if response.content else {}
        print(f"[Keeta][register_merchant] FIM (sucesso) | merchant_id={merchant_id}")
        return resultado
    except Exception as error:
        print(f"[Keeta][register_merchant] ERRO: {type(error).__name__}: {error}")
        print(f"[Keeta][register_merchant] FIM (falha) | merchant_id={merchant_id}")
        return None


def _is_uuid(value) -> bool:
    """Retorna True apenas para UUIDs textuais válidos."""
    if not isinstance(value, str):
        return False
    try:
        import uuid
        uuid.UUID(value)
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _validate_merchant_update(entity_type: str, updated_objects: list) -> str | None:
    """Valida um único request de merchantUpdate antes do envio."""
    if entity_type not in MERCHANT_UPDATE_ENTITY_TYPES:
        return f"entityType inválido: {entity_type!r}"
    if not isinstance(updated_objects, list) or not updated_objects:
        return "updatedObjects não pode ser vazio quando entityType está presente"

    required_fields = {
        # A Keeta documenta MERCHANT como atualização completa: todos os
        # campos obrigatórios do objeto Merchant precisam estar em um único
        # updatedObjects[0].
        "MERCHANT": {
            "id", "status", "basicInfo", "services", "items", "menus",
            "categories", "itemOffers",
        },
        # BASIC_INFO é um envelope: updatedObjects[0].basicInfo nunca pode ser null.
        "BASIC_INFO": {"basicInfo"},
        "SERVICE": {"id", "status", "serviceType", "menuId", "serviceHours"},
        "MENU": {"id", "name", "description", "externalCode", "categoryId"},
        "CATEGORY": {"id", "index", "name", "status", "itemOfferId"},
        "ITEM": {"id", "name", "externalCode", "status"},
        "ITEM_OFFER": {"id", "itemId", "index", "status", "price", "optionGroupsId"},
        "OPTION_GROUP": {
            "id", "index", "name", "description", "externalCode", "status",
            "minPermitted", "maxPermitted", "priceMethod",
        },
        "OPTION": {"id", "itemId", "index", "status", "price"},
        "AVAILABILITY": {"id", "hours"},
    }

    for index, entity in enumerate(updated_objects):
        if not isinstance(entity, dict):
            return f"updatedObjects[{index}] precisa ser um objeto completo"
        missing_fields = sorted(required_fields[entity_type] - entity.keys())
        if missing_fields:
            return (
                f"updatedObjects[{index}] ({entity_type}) está incompleto; "
                f"campos ausentes: {', '.join(missing_fields)}"
            )
        if entity_type != "BASIC_INFO" and (not isinstance(entity.get("id"), str) or not entity["id"].strip()):
            return f"updatedObjects[{index}].id é obrigatório"

        if entity_type == "MERCHANT":
            merchant_id = entity.get("id")
            if not isinstance(merchant_id, str) or not merchant_id.strip():
                return f"updatedObjects[{index}].id do MERCHANT precisa ser o merchantId do onboarding"
            if entity.get("status") not in {"AVAILABLE", "UNAVAILABLE"}:
                return f"updatedObjects[{index}].status precisa ser AVAILABLE ou UNAVAILABLE"
            for collection_name in ("services", "items", "menus", "categories", "itemOffers"):
                if not isinstance(entity.get(collection_name), list) or not entity[collection_name]:
                    return f"updatedObjects[{index}].{collection_name} precisa ser uma lista não vazia"
            if not isinstance(entity.get("basicInfo"), dict):
                return f"updatedObjects[{index}].basicInfo precisa ser um objeto"

        if entity_type == "BASIC_INFO":
            basic_info = entity.get("basicInfo")
            if not isinstance(basic_info, dict):
                return f"updatedObjects[{index}].basicInfo não pode ser null"
            required_basic_info = {
                "name", "document", "merchantType", "address", "contactEmails",
                "contactPhones", "minOrderValue", "averagePreparationTime", "merchantCategories",
            }
            missing_basic_info = sorted(required_basic_info - basic_info.keys())
            if missing_basic_info:
                return f"basicInfo incompleto; campos ausentes: {', '.join(missing_basic_info)}"
            address = basic_info.get("address")
            if not isinstance(address, dict):
                return "basicInfo.address precisa ser um objeto"
            latitude = address.get("latitude", address.get("lat"))
            longitude = address.get("longitude", address.get("lng"))
            if latitude is None or longitude is None:
                return "basicInfo.address precisa conter latitude/longitude ou lat/lng"

        if entity_type == "SERVICE":
            if not _is_uuid(entity.get("id")):
                return f"updatedObjects[{index}].id do SERVICE precisa ser um UUID válido"
            if entity.get("serviceType") != "DELIVERY":
                return f"updatedObjects[{index}].serviceType precisa ser DELIVERY"
            if not _is_uuid(entity.get("menuId")):
                return f"updatedObjects[{index}].menuId precisa ser um UUID válido"
            if not isinstance(entity.get("serviceHours"), dict):
                return f"updatedObjects[{index}].serviceHours precisa ser um objeto"

        if entity_type == "MENU":
            if not _is_uuid(entity.get("id")):
                return f"updatedObjects[{index}].id do MENU precisa ser um UUID válido"
            category_ids = entity.get("categoryId")
            if not isinstance(category_ids, list) or not category_ids:
                return "MENU.categoryId precisa ser uma lista não vazia de UUIDs"
            invalid_category_ids = [category_id for category_id in category_ids if not _is_uuid(category_id)]
            if invalid_category_ids:
                return "MENU.categoryId só pode conter UUIDs válidos, nunca externalCodes"

        if entity_type in {"CATEGORY", "ITEM", "ITEM_OFFER", "OPTION_GROUP", "OPTION"}:
            if not isinstance(entity.get("id"), str) or not entity["id"].strip():
                return f"updatedObjects[{index}].id precisa ser uma string não vazia"

        if entity_type == "ITEM_OFFER":
            # No Open Delivery v1.5.0, `price` é o preço da oferta de
            # delivery. Os aliases deliveryPrice/pickupPrice também são
            # aceitos para compatibilidade, mas não são obrigatórios.
            prices = [entity.get("price"), entity.get("deliveryPrice"), entity.get("pickupPrice")]
            has_delivery_or_pickup_price = any(
                isinstance(price, dict) and price.get("value") is not None
                for price in prices
            )
            if not has_delivery_or_pickup_price:
                return (
                    f"updatedObjects[{index}] (ITEM_OFFER) precisa ter preço de delivery "
                    "ou pickup; preço indoor isolado não é permitido"
                )

        if entity_type == "OPTION_GROUP":
            options = entity.get("options")
            if not isinstance(options, list) or not options:
                return (
                    f"updatedObjects[{index}].options precisa ser uma lista não vazia "
                    "quando o optionGroup é enviado"
                )
            available_count = sum(
                1 for option in options
                if isinstance(option, dict) and option.get("status") == "AVAILABLE"
            )
            min_permitted = entity.get("minPermitted")
            if not isinstance(min_permitted, int) or min_permitted < 0:
                return f"updatedObjects[{index}].minPermitted precisa ser um inteiro não negativo"
            if available_count < min_permitted:
                return (
                    f"updatedObjects[{index}] (OPTION_GROUP) é unfulfillable: "
                    f"minPermitted={min_permitted}, opções AVAILABLE={available_count}"
                )

    return None


def _post_merchant_update_payload(merchant_id: str, payload: dict) -> tuple[bool, str | None]:
    """Envia exatamente um body independente para merchantUpdate."""
    request_id = uuid.uuid4().hex[:12]
    started_at = time.perf_counter()
    if not isinstance(payload, dict):
        return False, "payload precisa ser um objeto JSON"
    has_status = "merchantStatus" in payload
    has_entity = "entityType" in payload or "updatedObjects" in payload
    if has_status and has_entity:
        return False, "merchantStatus não pode ser combinado com entityType/updatedObjects"
    if has_status and payload.get("merchantStatus") not in {"AVAILABLE", "UNAVAILABLE"}:
        return False, "merchantStatus precisa ser AVAILABLE ou UNAVAILABLE"
    if has_entity:
        entity_type = payload.get("entityType")
        updated_objects = payload.get("updatedObjects")
        if entity_type is None or updated_objects is None:
            return False, "entityType e updatedObjects devem ser enviados juntos"
        validation_error = _validate_merchant_update(entity_type, updated_objects)
        if validation_error:
            return False, validation_error

    endpoint_merchant_id = str(merchant_id).strip()
    if not endpoint_merchant_id:
        return False, "merchantId não pode ser vazio"
    url = f"{BASE_URL}/v1/merchantUpdate/{endpoint_merchant_id}"
    body = canonical_json(payload)
    print(
        f"[Keeta][_post_merchant_update_payload] INÍCIO | request_id={request_id} | "
        f"merchant_id={endpoint_merchant_id} | url={url} | payload={payload} | "
        f"body={body!r} | body_len={len(body)} | signature_base_url={SIGNATURE_BASE_URL}"
    )
    try:
        headers = _build_headers(url, body=body)
        print(
            f"[Keeta][_post_merchant_update_payload] Enviando | request_id={request_id} | "
            f"method=POST | content_type={headers.get('Content-Type')} | "
            f"body_sha256={hashlib.sha256(body.encode('utf-8')).hexdigest()}"
        )
        response = requests.post(
            url,
            headers=headers,
            data=body.encode("utf-8"),
            timeout=REQUEST_TIMEOUT,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        response_body = response.text[:500].replace("\n", " ")
        print(
            f"[Keeta][_post_merchant_update_payload] Resposta | request_id={request_id} | "
            f"status_code={response.status_code} | elapsed_ms={elapsed_ms:.1f} | "
            f"content_type={response.headers.get('Content-Type')!r} | "
            f"body={response_body!r}"
        )
        success = response.status_code in (200, 201, 204)
        error = None if success else f"Keeta API retornou {response.status_code}: {response_body}"
        print(
            f"[Keeta][_post_merchant_update_payload] FIM | request_id={request_id} | "
            f"success={success} | error={error!r}"
        )
        return success, error
    except Exception as error:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        error_detail = f"{type(error).__name__}: {error}"
        print(
            f"[Keeta][_post_merchant_update_payload] ERRO | request_id={request_id} | "
            f"elapsed_ms={elapsed_ms:.1f} | detail={error_detail}"
        )
        print(traceback.format_exc())
        return False, error_detail


def notify_merchant_update(
    merchant_id: str,
    *,
    merchant_status: str | None = None,
    entity_type: str | None = None,
    updated_objects: list | None = None,
) -> tuple[bool, str | None]:
    """Executa um, e somente um, dos três formatos documentados."""
    if merchant_status is not None:
        if merchant_status not in {"AVAILABLE", "UNAVAILABLE"}:
            return False, "merchantStatus precisa ser AVAILABLE ou UNAVAILABLE"
        if entity_type is not None or updated_objects is not None:
            return False, "merchantStatus não pode ser combinado com entityType/updatedObjects"
        return _post_merchant_update_payload(merchant_id, {"merchantStatus": merchant_status})

    if entity_type is None and updated_objects is None:
        return _post_merchant_update_payload(merchant_id, {})
    if entity_type is None or updated_objects is None:
        return False, "entityType e updatedObjects devem ser enviados juntos"
    return _post_merchant_update_payload(
        merchant_id,
        {"entityType": entity_type, "updatedObjects": updated_objects},
    )


def sync_menu_entities(merchant_id: str, merchant: dict) -> tuple[bool, str | None]:
    """Envia o cardápio completo pelo fluxo de menu push da Keeta.

    O Merchant recebido é normalizado para o schema estrito do push e enviado
    como `entityType=MERCHANT`, solicitando a atualização completa do menu.
    """
    if not isinstance(merchant, dict):
        return False, "merchant precisa ser um objeto JSON"

    full_merchant = dict(merchant)
    # O path usa o Keeta merchantId, mas o id do objeto Merchant é um
    # identificador do software e precisa ter pelo menos 36 caracteres.
    full_merchant["id"] = merchant_uuid(merchant_id)
    services = merchant.get("services")
    menus = merchant.get("menus")
    categories = merchant.get("categories")
    items = merchant.get("items")
    item_offers = merchant.get("itemOffers")
    option_groups = merchant.get("optionGroups")

    # O GET /merchant tolera aliases usados pelo Open Delivery v1.5.0, mas o
    # merchantUpdate é mais estrito: Item.images usa `URL` (maiúsculo) e
    # ItemOffer deve conter apenas `price`, não os aliases deliveryPrice e
    # pickupPrice enviados no retorno compatível do GET.
    if isinstance(items, list):
        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                normalized_items.append(item)
                continue
            normalized_item = dict(item)
            normalized_item.pop("deliveryPrice", None)
            normalized_item.pop("pickupPrice", None)
            normalized_item.pop("price", None)
            images = normalized_item.get("images")
            if isinstance(images, list):
                normalized_item["images"] = [
                    {
                        "type": image.get("type"),
                        "URL": image.get("URL") or image.get("url"),
                    }
                    for image in images
                    if isinstance(image, dict)
                    and image.get("type") in {"main", "thumb"}
                    and (image.get("URL") or image.get("url"))
                ]
            normalized_items.append(normalized_item)
        items = normalized_items

    if isinstance(item_offers, list):
        normalized_item_offers = []
        for item_offer in item_offers:
            if not isinstance(item_offer, dict):
                normalized_item_offers.append(item_offer)
                continue
            normalized_item_offer = dict(item_offer)
            normalized_item_offer.pop("deliveryPrice", None)
            normalized_item_offer.pop("pickupPrice", None)
            normalized_item_offers.append(normalized_item_offer)
        item_offers = normalized_item_offers
    if isinstance(option_groups, list):
        # Um optionGroup vazio não pode permanecer referenciado por uma oferta.
        valid_option_group_ids = set()
        normalized_option_groups = []
        for option_group in option_groups:
            if not isinstance(option_group, dict):
                continue
            normalized_option_group = dict(option_group)
            options = normalized_option_group.get("options")
            if not isinstance(options, list) or not options:
                continue
            valid_option_group_ids.add(normalized_option_group.get("id"))
            normalized_option_groups.append(normalized_option_group)
        option_groups = normalized_option_groups
        if isinstance(item_offers, list):
            for item_offer in item_offers:
                if isinstance(item_offer, dict) and isinstance(item_offer.get("optionGroupsId"), list):
                    item_offer["optionGroupsId"] = [
                        option_group_id
                        for option_group_id in item_offer["optionGroupsId"]
                        if option_group_id in valid_option_group_ids
                    ]
    basic_info = dict(merchant.get("basicInfo") or {})
    basic_info.setdefault("name", "MANEIRA BURGUER")
    basic_info.setdefault("document", "12345678000199")
    basic_info.setdefault("merchantType", "RESTAURANT")
    basic_info.setdefault("contactEmails", ["contato@minhaloja.com.br"])
    basic_info.setdefault("contactPhones", {"commercialNumber": "5511999999999"})
    basic_info.setdefault("minOrderValue", {"value": 0.0, "currency": "BRL"})
    basic_info.setdefault("averagePreparationTime", 30)
    basic_info.setdefault("merchantCategories", ["RESTAURANT"])
    address = dict(basic_info.get("address") or {})
    latitude = address.get("latitude", address.get("lat", -23.5505))
    longitude = address.get("longitude", address.get("lng", -46.6333))
    address.update({
        "country": address.get("country") or "BR",
        "state": address.get("state") or "SP",
        "city": address.get("city") or "São Paulo",
        "district": address.get("district") or "Centro",
        "street": address.get("street") or "Avenida Paulista",
        "number": str(address.get("number") or "1000"),
        "postalCode": address.get("postalCode") or "01310-100",
        "latitude": latitude,
        "longitude": longitude,
    })
    # `lat` e `lng` não pertencem ao schema oficial; não os propague no POST.
    address.pop("lat", None)
    address.pop("lng", None)
    basic_info["address"] = address
    if not isinstance(services, list) or not services:
        return False, "services não pode ser vazio"

    normalized_services = []
    for service in services:
        if not isinstance(service, dict):
            return False, "services deve conter somente objetos"
        normalized_service = dict(service)
        if normalized_service.get("serviceType") == "DELIVERY" and not isinstance(normalized_service.get("serviceHours"), dict):
            normalized_service["serviceHours"] = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{normalized_service['id']}:service-hours")),
                "weekHours": [{
                    "dayOfWeek": [
                        "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                        "FRIDAY", "SATURDAY", "SUNDAY",
                    ],
                    "timePeriods": {"startTime": "11:00:00.000Z", "endTime": "23:00:00.000Z"},
                }],
            }
        normalized_services.append(normalized_service)

    if not isinstance(basic_info, dict):
        return False, "basicInfo não pode ser null"
    if not isinstance(menus, list) or not menus:
        return False, "menus não pode ser vazio"
    if not isinstance(categories, list) or not categories:
        return False, "categories não pode ser vazio"
    if not isinstance(items, list) or not items:
        return False, "items não pode ser vazio"
    if not isinstance(item_offers, list) or not item_offers:
        return False, "itemOffers não pode ser vazio"

    full_merchant["services"] = normalized_services
    full_merchant["basicInfo"] = basic_info
    full_merchant["items"] = items
    full_merchant["itemOffers"] = item_offers
    full_merchant["optionGroups"] = option_groups or []

    # O body vazio é documentado como pull, mas a API de produção está
    # respondendo 400 para esse formato. O payload completo MERCHANT é o
    # formato de menu push que efetivamente retorna 204 e ainda faz a Keeta
    # atualizar o cardápio inteiro.
    success, error = _post_merchant_update_payload(
        merchant_id,
        {"entityType": "MERCHANT", "updatedObjects": [full_merchant]},
    )
    if not success:
        return False, f"MENU_PUSH: {error}"
    print("[Keeta][sync_menu_entities] Menu push solicitado com sucesso (204/2xx)")
    return True, None


def update_store_status(keeta_merchant_id: str, is_open: bool) -> tuple[bool, str | None]:
    """
    Abre ou fecha a loja na plataforma Keeta.

    Quando usar: no início/fim do expediente, ou quando a loja fica sem
    capacidade de atender (ex: sem entregador).

    Endpoint: POST /v1/merchantUpdate/{merchantId}

    Retorna (sucesso, mensagem_de_erro). Se sucesso=True, mensagem é None.
    """
    print(f"\n[Keeta][update_store_status] INÍCIO | keeta_merchant_id={keeta_merchant_id} | is_open={is_open}")

    status = "AVAILABLE" if is_open else "UNAVAILABLE"

    sucesso, erro = notify_merchant_update(
        keeta_merchant_id,
        merchant_status=status,
    )
    print(f"[Keeta][update_store_status] FIM | keeta_merchant_id={keeta_merchant_id} | sucesso={sucesso}")
    return sucesso, erro


def force_menu_sync(merchant_id: str, merchant: dict | None = None) -> tuple[bool, str | None]:
    """
    Força a Keeta a sincronizar o cardápio completo da loja.

    O menu é enviado como `entityType=MERCHANT` com o Merchant completo. A
    tentativa anterior de usar body `{}` dependia do pull documentado, mas a
    API de produção retorna 400 para esse formato nesta integração.

    `merchant_id` é o identificador persistido no onboarding e usado no path
    de `merchantUpdate`; `merchant` deve ser o payload atual do GET /merchant.
    """
    print(f"\n[Keeta][force_menu_sync] INÍCIO | merchant_id={merchant_id}")

    endpoint_merchant_id = str(merchant_id).strip()
    if not endpoint_merchant_id:
        return False, "merchantId não pode ser vazio"
    if not isinstance(merchant, dict):
        return False, "merchant é obrigatório para o menu push"

    return sync_menu_entities(endpoint_merchant_id, merchant)


# =============================================================================
#  5. VALIDAÇÃO DO WEBHOOK
# =============================================================================

def validate_webhook_signature(body: str, received_signature: str) -> bool:
    """
    Valida se um webhook recebido realmente veio da Keeta.

    Segundo a documentação oficial de assinatura da Keeta, a mesma fórmula
    usada para assinar requisições que ENVIAMOS também é usada pela Keeta
    para assinar as requisições que ela nos ENVIA (webhooks):

        signature_string = URL + "&" + sorted_query_params + "&" + body

    Ou seja, a assinatura do webhook NÃO é calculada apenas sobre o body:
    ela inclui a URL do próprio webhook (a mesma informada como
    `ordersWebhookURL` no onboarding). Por isso, tentamos validar contra
    duas possibilidades, para sermos compatíveis mesmo com pequenas
    variações de URL (com ou sem barra final, etc):

      1. URL + body   (fórmula oficial, URL = ordersWebhookURL)
      2. body isolado (fallback legado, caso a Keeta não inclua a URL)

    Retorna True se a assinatura é válida (é da Keeta), False caso contrário.
    """
    print(f"[Keeta][validate_webhook_signature] INÍCIO | body_len={len(body)} | received_signature_preview={received_signature[:20]}...")

    webhook_url = f"{MY_PUBLIC_URL}/orders"

    candidatos = {
        "url+body":        f"{webhook_url}&{body}" if body and body.strip() else webhook_url,
        "url+body(sem_barra)": (f"{webhook_url.rstrip('/')}&{body}" if body and body.strip() else webhook_url.rstrip("/")),
        "body_apenas":     body,
    }

    for nome, string_to_sign in candidatos.items():
        expected_signature = hmac.new(
            key=CLIENT_SECRET.encode("utf-8"),
            msg=string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_b64 = base64.b64encode(expected_signature).decode("utf-8")
        valida = hmac.compare_digest(expected_b64, received_signature)
        print(f"[Keeta][validate_webhook_signature] Tentativa '{nome}' | string_preview={string_to_sign[:80]}... | esperado(preview)={expected_b64[:20]}... | válida={valida}")

        if valida:
            print(f"[Keeta][validate_webhook_signature] FIM | válida=True (método='{nome}')")
            return True

    print(f"[Keeta][validate_webhook_signature] FIM | válida=False (nenhum método bateu)")
    return False


# =============================================================================
#  6. UTILITÁRIOS
# =============================================================================

def _save_log(prefix: str, data: dict):
    """
    Salva um JSON em disco para facilitar o debug durante o desenvolvimento.
    Os arquivos ficam na pasta `keeta_logs/`.
    """
    print(f"[Keeta][_save_log] INÍCIO | prefix={prefix}")
    try:
        os.makedirs("keeta_logs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"keeta_logs/{timestamp}_{prefix}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[Keeta][_save_log] Log salvo em: {filename}")
    except Exception as e:
        print(f"[Keeta][_save_log] AVISO: não foi possível salvar o log em disco: {type(e).__name__}: {e}")
    print(f"[Keeta][_save_log] FIM | prefix={prefix}")

# =============================================================================
#  menu_platforms.py  —  Um cardápio, ajustes por plataforma (Keeta / iFood)
# =============================================================================
#
#  Com "mesmo cardápio nas duas plataformas" ligado (padrão), tudo vai igual
#  para as duas. Desligado, cada categoria, produto e complemento pode ficar
#  só numa plataforma (on_keeta / on_ifood) e ter preço próprio
#  (keeta_price / ifood_price; vazio = o preço normal).
#
#  O preço próprio substitui o preço e o preço "de" (sem promoção riscada).
# =============================================================================

import hashlib
import json

PLATFORMS = ("KEETA", "IFOOD")


def same_menu(config) -> bool:
    return config is None or config.same_menu_all_platforms is not False


def is_visible(entity, platform: str, same: bool) -> bool:
    if same or entity is None:
        return True
    return getattr(entity, f"on_{platform.lower()}", True) is not False


def item_prices(item, platform: str, same: bool) -> tuple[float, float]:
    """(preço cobrado, preço "de") do produto na plataforma."""
    base = item.price or 0.0
    original = item.original_price if item.original_price is not None else base
    if not same:
        override = getattr(item, f"{platform.lower()}_price", None)
        if override is not None:
            return float(override), float(override)
    return float(base), float(original)


def option_price(option, platform: str, same: bool) -> float:
    base = option.price if option.price is not None else 0.0
    if not same:
        override = getattr(option, f"{platform.lower()}_price", None)
        if override is not None:
            return float(override)
    return float(base or 0.0)


def _strip_status(node):
    if isinstance(node, dict):
        return {k: _strip_status(v) for k, v in node.items() if k != "status"}
    if isinstance(node, list):
        return [_strip_status(v) for v in node]
    return node


def menu_hash(menu_parts: dict) -> str:
    """Impressão digital do cardápio sem os status: pausar/esgotar um item não
    conta como "alteração não publicada" (pausas vão na hora)."""
    data = json.dumps(_strip_status(menu_parts), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

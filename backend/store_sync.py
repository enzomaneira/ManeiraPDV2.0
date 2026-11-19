# =============================================================================
#  store_sync.py  —  Puxa da Keeta o status e o horário da loja
# =============================================================================
#
#  Mantém o PDV em sincronia com o que está valendo na Keeta:
#    - status (aberta/fechada): sempre segue a Keeta, que pode fechar a loja
#      por conta própria (ex.: pedidos não aceitos a tempo);
#    - horário de funcionamento: só é importado enquanto a loja ainda não
#      cadastrou o seu no PDV (nunca sobrescreve o que o restaurante salvou),
#      e nunca importa o horário de exemplo que o próprio PDV envia.
#
#  Endpoint: GET /v1/merchant/{merchantId}/status
# =============================================================================

import json
import time

import keeta_client
from database import db

SYNC_INTERVAL_SECONDS = 300  # no máximo uma consulta a cada 5 min por loja
_last_sync: dict[int, float] = {}


def sync_store_from_keeta(config, force: bool = False) -> dict:
    """Atualiza config (StoreConfig) com o que está na Keeta. Faz commit se mudar algo."""
    result = {"synced": False, "statusChanged": False, "hoursImported": False}
    merchant_id = (config.keeta_merchant_id or "").strip() if config else ""
    if not merchant_id:
        return result
    now = time.monotonic()
    if not force and now - _last_sync.get(config.store_id, -SYNC_INTERVAL_SECONDS) < SYNC_INTERVAL_SECONDS:
        return result
    _last_sync[config.store_id] = now

    remote = keeta_client.get_merchant_status(merchant_id)
    if not remote:
        return result
    result["synced"] = True

    if remote["status"] in ("AVAILABLE", "UNAVAILABLE"):
        is_open = remote["status"] == "AVAILABLE"
        if bool(config.is_store_open) != is_open:
            config.is_store_open = is_open
            result["statusChanged"] = True

    if config.service_hours_json is None and remote["weekHours"] and not keeta_client.is_placeholder_week_hours(remote["weekHours"]):
        periods = keeta_client.week_hours_to_brasilia_periods(remote["weekHours"])
        try:
            periods = keeta_client.parse_service_hours(periods)
        except ValueError:
            periods = []
        if periods:
            config.service_hours_json = json.dumps(periods)
            result["hoursImported"] = True

    if result["statusChanged"] or result["hoursImported"]:
        db.session.commit()
    print(f"[StoreSync] store_id={config.store_id} | merchant={merchant_id} | status_keeta={remote['status']} | "
          f"loja_aberta={config.is_store_open} | status_mudou={result['statusChanged']} | horario_importado={result['hoursImported']}")
    return result

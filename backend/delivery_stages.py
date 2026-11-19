# =============================================================================
#  delivery_stages.py  —  Etapas da entrega e avanço de status dos pedidos
# =============================================================================
#
#  As etapas usam os nomes do /tracking da Keeta (entrega própria). Os eventos
#  do entregador da Keeta (entrega da Keeta) são convertidos para as mesmas
#  etapas, assim o quadro do PDV trata os dois casos igual.
#
#  Eventos e reenvios podem chegar fora de ordem: etapa e status só avançam.
# =============================================================================

import json
from datetime import datetime, timezone

STAGES = (
    "PICKUP_ONGOING",       # entregador a caminho da loja
    "ARRIVED_AT_MERCHANT",  # entregador na loja
    "ORDER_PICKED",         # pedido coletado
    "DELIVERY_ONGOING",     # em rota de entrega
    "ARRIVED_AT_CUSTOMER",  # chegou ao cliente
    "ORDER_DELIVERED",      # entregue
)
STAGE_RANK = {stage: index for index, stage in enumerate(STAGES)}

# Evento do webhook da Keeta -> etapa
KEETA_EVENT_TO_STAGE = {
    "PICKUP_ONGOING":         "PICKUP_ONGOING",
    "RIDER_ARRIVED_AT_STORE": "ARRIVED_AT_MERCHANT",
    "ORDER_COLLECTED":        "ORDER_PICKED",
    "DISPATCHED":             "DELIVERY_ONGOING",
    "DELIVERED":              "ORDER_DELIVERED",
    "CONCLUDED":              "ORDER_DELIVERED",
}

STATUS_RANK = {"PENDING": 0, "NEW": 0, "PREPARING": 1, "READY_FOR_PICKUP": 2, "DELIVERY_IN_PROGRESS": 3, "COMPLETED": 4}
FINAL_STATUSES = ("COMPLETED", "CANCELED")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def advance_stage(order, stage: str, when: str | None = None) -> bool:
    """Grava a etapa se ela vier depois da atual. Retorna True se mudou."""
    if stage not in STAGE_RANK:
        return False
    current = STAGE_RANK.get(order.delivery_stage or "", -1)
    if STAGE_RANK[stage] <= current:
        return False
    order.delivery_stage = stage
    order.delivery_stage_at = when or now_iso()
    return True


def advance_status(order, new_status: str) -> bool:
    """Muda o status só para frente. Cancelamento vale sempre (menos se já
    cancelado); pedido concluído ou cancelado não volta."""
    if not new_status or new_status == order.status:
        return False
    if new_status == "CANCELED":
        order.status = "CANCELED"
        return True
    if order.status in FINAL_STATUSES:
        return False
    if STATUS_RANK.get(new_status, -1) <= STATUS_RANK.get(order.status, -1):
        return False
    order.status = new_status
    return True


def pickup_eta_from_metadata(metadata) -> str | None:
    """metadata do PICKUP_ONGOING é uma string JSON com pickupEtaDatetime
    (a doc também escreve pickupEtaDateTime)."""
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            return None
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("pickupEtaDatetime") or metadata.get("pickupEtaDateTime")
    return value if isinstance(value, str) and value.strip() else None

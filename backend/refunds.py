"""
Reembolsos da Keeta (pedido já entregue em que o cliente pede o dinheiro de volta).

Fluxo (handshake da Keeta):
  USER_REFUND_REQUEST  cliente pediu reembolso (total ou de alguns itens)
      → o restaurante responde no PDV: acceptRefund ou rejectRefund
  REFUNDED             reembolso concluído
  REFUND_FAILED        reembolso recusado/falhou

O pedido de reembolso NÃO cancela o pedido: ele só fica registrado em
Order.refund_json até o restaurante responder. Reembolso total concluído
cancela o pedido (sai do faturamento); reembolso parcial mantém o status.

Estados guardados em refund_json["status"]:
  REQUESTED  esperando o restaurante responder
  ACCEPTED   o restaurante aceitou; esperando a Keeta confirmar (REFUNDED)
  REJECTED   o restaurante recusou (ou a Keeta avisou REFUND_FAILED)
  REFUNDED   reembolso concluído
"""
import json
from datetime import datetime, timezone

REFUND_EVENTS = {"USER_REFUND_REQUEST", "REFUNDED", "REFUND_FAILED"}
REJECT_CODES = {
    "DISH_ALREADY_DONE": "O prato já tinha sido preparado",
    "OUT_FOR_DELIVERY": "O pedido já tinha saído para entrega",
    "OTHER": "Outro motivo",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _metadata(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _cents(value) -> float | None:
    try:
        return round(float(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def _pictures(raw) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = [raw] if raw.startswith("http") else []
    return [p for p in raw if isinstance(p, str) and p.startswith("http")][:6] if isinstance(raw, list) else []


def _products(raw) -> list[dict]:
    items = []
    for product in raw if isinstance(raw, list) else []:
        if not isinstance(product, dict):
            continue
        name = product.get("name") or (product.get("nameI18n") or {}).get("default") or "Item"
        count = product.get("refundCount") or product.get("count") or 1
        price = (product.get("priceWithGroup") or {}).get("amount", product.get("price"))
        items.append({"name": str(name).strip(), "count": count, "price": _cents(price)})
    return items


def _iso_from_ms(value) -> str | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def load(order) -> dict | None:
    try:
        data = json.loads(order.refund_json) if order.refund_json else None
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def save(order, data: dict) -> None:
    order.refund_json = json.dumps(data, ensure_ascii=False)


def apply_event(order, event_type: str, event: dict) -> bool:
    """Aplica um evento de reembolso da Keeta no pedido. Retorna True se mudou algo.
    O mesmo evento (eventId) é aplicado uma vez só."""
    if event_type not in REFUND_EVENTS or order is None:
        return False
    data = load(order) or {}
    event_id = str(event.get("eventId") or "")
    seen = data.get("events") or []
    if event_id and event_id in seen:
        return False
    meta = _metadata(event.get("metadata"))

    if event_type == "USER_REFUND_REQUEST":
        after_sale = str(meta.get("afterSaleOrderId") or "")
        if after_sale and after_sale != data.get("afterSaleOrderId"):
            seen = []  # novo pedido de reembolso para o mesmo pedido: começa de novo
            data = {}
        data.update({
            "status": "REQUESTED",
            "afterSaleOrderId": after_sale or data.get("afterSaleOrderId"),
            "amount": _cents(meta.get("money")) if meta.get("money") is not None else data.get("amount"),
            "currency": meta.get("currency") or data.get("currency") or "BRL",
            "reason": (meta.get("applyReason") or "").strip() or data.get("reason"),
            "partial": bool(meta.get("partRefund")),  # 0 = pedido inteiro, 1 = só alguns itens
            "items": _products(meta.get("refundProducts")) or data.get("items") or [],
            "pictures": _pictures(meta.get("pictures")) or data.get("pictures") or [],
            "appeal": bool(meta.get("isAppeal")),
            "requestedAt": _iso_from_ms(meta.get("opTime")) or event.get("createdAt") or _now(),
            "decision": None,
        })
    elif event_type == "REFUNDED":
        data["status"] = "REFUNDED"
        data["finishedAt"] = event.get("createdAt") or _now()
        if meta.get("money") is not None:
            data["amount"] = _cents(meta.get("money"))
        if "partial" not in data:
            data["partial"] = bool(meta.get("partRefund"))
        if not data.get("partial"):
            order.status = "CANCELED"  # reembolso total: o pedido sai do faturamento
    else:  # REFUND_FAILED
        data["status"] = "REJECTED"
        data["finishedAt"] = event.get("createdAt") or _now()
        reason = (meta.get("handleReason") or "").strip()
        if reason and not (data.get("decision") or {}).get("reason"):
            data["decision"] = {**(data.get("decision") or {}), "reason": reason}

    if event_id:
        seen.append(event_id)
    data["events"] = seen[-20:]
    save(order, data)
    return True


def mark_decision(order, action: str, code: str | None = None, reason: str | None = None) -> dict:
    """O restaurante respondeu pelo PDV (a Keeta confirma depois com REFUNDED/REFUND_FAILED)."""
    data = load(order) or {}
    data["status"] = "ACCEPTED" if action == "ACCEPT" else "REJECTED"
    data["decision"] = {"action": action, "code": code, "reason": reason, "at": _now()}
    save(order, data)
    return data

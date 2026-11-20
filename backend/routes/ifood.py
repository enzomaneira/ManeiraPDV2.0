# =============================================================================
#  routes/ifood.py  —  Integração com o iFood
# =============================================================================
#
#  Pedidos chegam por dois caminhos (os dois podem estar ligados):
#    - Webhook: POST /api/ifood/webhook (URL cadastrada no Portal do Desenvolvedor),
#      validado pela assinatura X-IFood-Signature;
#    - Polling: o PDV aberto chama POST /api/ifood/poll a cada ~30s, que busca
#      os eventos das lojas da conta e confirma o recebimento (acknowledgment).
#
#  Cada restaurante (marca) da conta liga a sua loja do iFood pelo merchantId
#  (StoreConfig.ifood_merchant_id). Pedidos viram Order com platform="IFOOD".
# =============================================================================

import json
import threading
import time
from datetime import datetime

from flask import Blueprint, request, jsonify, g
from sqlalchemy.exc import IntegrityError

import delivery_stages
import ifood_client
from auth_utils import login_required, rate_limited
from database import db
from models import MenuItem, Order, OrderItem, StoreConfig

ifood_bp = Blueprint("ifood", __name__)

# Evento do iFood (code ou fullCode) -> (status do PDV, etapa da entrega)
EVENT_MAP = {
    "CFM": ("PREPARING", None), "CONFIRMED": ("PREPARING", None),
    "RTP": ("READY_FOR_PICKUP", None), "READY_TO_PICKUP": ("READY_FOR_PICKUP", None),
    "DSP": ("DELIVERY_IN_PROGRESS", "DELIVERY_ONGOING"), "DISPATCHED": ("DELIVERY_IN_PROGRESS", "DELIVERY_ONGOING"),
    "CON": ("COMPLETED", "ORDER_DELIVERED"), "CONCLUDED": ("COMPLETED", "ORDER_DELIVERED"),
    "CAN": ("CANCELED", None), "CANCELLED": ("CANCELED", None),
    # Entregador do iFood
    "ADR": (None, "PICKUP_ONGOING"), "ASSIGN_DRIVER": (None, "PICKUP_ONGOING"),
    "GTO": (None, "PICKUP_ONGOING"), "GOING_TO_ORIGIN": (None, "PICKUP_ONGOING"),
    "AAO": (None, "ARRIVED_AT_MERCHANT"), "ARRIVED_AT_ORIGIN": (None, "ARRIVED_AT_MERCHANT"),
    "CLT": ("DELIVERY_IN_PROGRESS", "ORDER_PICKED"), "COLLECTED": ("DELIVERY_IN_PROGRESS", "ORDER_PICKED"),
    "AAD": (None, "ARRIVED_AT_CUSTOMER"), "ARRIVED_AT_DESTINATION": (None, "ARRIVED_AT_CUSTOMER"),
}
PLACED_CODES = {"PLC", "PLACED"}
IGNORED_CODES = {"KEEPALIVE", "KPA"}
PAYMENT_METHODS = {"CREDIT", "DEBIT", "MEAL_VOUCHER", "FOOD_VOUCHER", "DIGITAL_WALLET", "PIX", "CASH", "CREDIT_DEBIT", "COUPON", "REDEEM", "OTHER"}

_processing_lock = threading.Lock()
_last_poll: dict[int, float] = {}
POLL_INTERVAL_SECONDS = 25


def _money(value) -> float:
    """Valores do iFood podem vir como número ou como {"value": n}."""
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


# -----------------------------------------------------------------------------
#  Pedido do iFood -> Order do PDV
# -----------------------------------------------------------------------------

def save_order_from_ifood(data: dict, store_id: int) -> Order | None:
    from routes.orders import option_labels  # mesmo formato de complementos da Keeta

    order_id = data.get("id")
    if not order_id:
        return None
    order = Order.query.filter_by(external_id=order_id).first() or Order(external_id=order_id)
    is_new = order.id is None
    order.store_id = store_id
    order.platform = "IFOOD"
    order.display_id = str(data.get("displayId") or order_id[:8])
    order.created_at = data.get("createdAt") or order.created_at or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if is_new and not order.status:
        config = StoreConfig.query.get(store_id)
        if config and config.auto_accept:
            order.status = "PREPARING"
            threading.Thread(target=ifood_client.confirm_order, args=(order_id,), daemon=True).start()
        else:
            order.status = "PENDING"

    # Cliente
    customer = data.get("customer") or {}
    phone = customer.get("phone") or {}
    order.customer_name = _text(customer.get("name")) or "Cliente"
    order.customer_json = json.dumps({
        "name": _text(customer.get("name")),
        # O iFood manda um número intermediado + código "localizador" (como um ramal)
        "phone": _text(phone.get("number")),
        "phoneExtension": _text(phone.get("localizer")),
        "documentNumber": _text(customer.get("documentNumber")),
        "ordersCount": customer.get("ordersCountOnMerchant"),
    }, ensure_ascii=False)

    # Entrega
    delivery = data.get("delivery") or {}
    address = delivery.get("deliveryAddress") or {}
    delivered_by = str(delivery.get("deliveredBy") or "").upper()
    order_type = str(data.get("orderType") or "").upper()
    order.delivery_json = json.dumps({
        "deliveredBy": "MERCHANT" if delivered_by == "MERCHANT" else "MARKETPLACE" if delivered_by == "IFOOD" else None,
        "orderType": order_type or None,
        "street": _text(address.get("streetName")), "number": _text(address.get("streetNumber")),
        "complement": _text(address.get("complement")), "district": _text(address.get("neighborhood")),
        "city": _text(address.get("city")), "state": _text(address.get("state")),
        "postalCode": _text(address.get("postalCode")), "reference": _text(address.get("reference")),
        "formattedAddress": _text(address.get("formattedAddress")),
        "estimatedDeliveryDateTime": _text(delivery.get("deliveryDateTime")),
    }, ensure_ascii=False)
    if order_type == "TAKEOUT":
        order.delivery_address = "Retirada no balcão"
    else:
        order.delivery_address = _text(address.get("formattedAddress")) or " - ".join(
            p for p in (" ".join(x for x in (_text(address.get("streetName")), _text(address.get("streetNumber"))) if x),
                        _text(address.get("neighborhood")), _text(address.get("city"))) if p) or None
    coords = address.get("coordinates") or {}
    if isinstance(coords.get("latitude"), (int, float)) and isinstance(coords.get("longitude"), (int, float)):
        order.latitude, order.longitude = coords["latitude"], coords["longitude"]
    order.pickup_code = _text(str(delivery.get("pickupCode") or "")) or _text((data.get("takeout") or {}).get("takeoutCode") if isinstance(data.get("takeout"), dict) else None) or order.display_id

    # Valores
    total = data.get("total") or {}
    order.items_price = _money(total.get("subTotal"))
    delivery_fee = _money(total.get("deliveryFee"))
    additional = _money(total.get("additionalFees"))
    order.other_fees_total = round(delivery_fee + additional, 2)
    order.discount = _money(total.get("benefits"))
    order.total_price = _money(total.get("orderAmount"))
    fees = []
    if delivery_fee:
        fees.append({"type": "DELIVERY_FEE", "price": {"value": delivery_fee}})
    if additional:
        fees.append({"type": "SERVICE_FEE", "price": {"value": additional}})
    order.fees_json = json.dumps(fees)
    discounts = []
    for benefit in data.get("benefits") or []:
        if not isinstance(benefit, dict):
            continue
        sponsors = [{"name": "MARKETPLACE" if str(s.get("name", "")).upper() == "IFOOD" else str(s.get("name", "")).upper(),
                     "amount": {"value": _money(s.get("value"))}} for s in benefit.get("sponsorshipValues") or [] if isinstance(s, dict)]
        discounts.append({"amount": {"value": _money(benefit.get("value"))}, "target": benefit.get("target"), "sponsorshipValues": sponsors})
    order.discounts_json = json.dumps(discounts)

    # Pagamento
    payments = data.get("payments") or {}
    methods = []
    for m in payments.get("methods") or []:
        if not isinstance(m, dict):
            continue
        method = str(m.get("method") or "OTHER").upper()
        entry = {"method": method if method in PAYMENT_METHODS else "OTHER",
                 "type": "PREPAID" if str(m.get("type", "")).upper() == "ONLINE" else "PENDING",
                 "value": _money(m.get("value"))}
        brand = (m.get("card") or {}).get("brand") if isinstance(m.get("card"), dict) else None
        if brand:
            entry["brand"] = str(brand).upper()
        change_for = (m.get("cash") or {}).get("changeFor") if isinstance(m.get("cash"), dict) else None
        if change_for:
            entry["changeFor"] = _money(change_for)
        methods.append(entry)
    order.payments_json = json.dumps({"prepaid": _money(payments.get("prepaid")), "pending": _money(payments.get("pending")), "methods": methods})
    order.payment_type = "ONLINE" if _money(payments.get("prepaid")) > 0 and not _money(payments.get("pending")) else "NA_ENTREGA"

    # Itens. O nome vem do cardápio do PDV pelo externalCode (o código que o PDV
    # enviou ao publicar no iFood): nos pedidos de teste o iFood troca o "name"
    # do item por "PEDIDO DE TESTE - NÃO ENTREGAR". Sem produto com o código,
    # usa o "name" do iFood.
    codes = {str(i.get("externalCode")).strip() for i in data.get("items") or [] if isinstance(i, dict) and _text(str(i.get("externalCode") or ""))}
    pdv_names = {m.external_code: m.name for m in MenuItem.query.filter(MenuItem.store_id == store_id, MenuItem.external_code.in_(codes)).all()} if codes else {}
    order.items.clear()
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        options = [{"name": o.get("name"), "quantity": o.get("quantity") or 1, "price": _money(o.get("unitPrice")),
                    "externalCode": o.get("externalCode")} for o in item.get("options") or [] if isinstance(o, dict) and o.get("name")]
        name = pdv_names.get(str(item.get("externalCode") or "").strip()) or _text(item.get("name")) or "Item"
        if options:
            name += f" ({', '.join(option_labels(options))})"
        if _text(item.get("observations")):
            name += f" [Obs: {item['observations'].strip()}]"
        quantity = item.get("quantity") or 1
        unit = _money(item.get("unitPrice"))
        line_total = _money(item.get("totalPrice")) or round(quantity * (unit + _money(item.get("optionsPrice"))), 2)
        order.items.append(OrderItem(menu_item_id=0, menu_item_name=name, quantity=int(quantity) if float(quantity).is_integer() else quantity,
                                     unit_price=unit, original_price=unit, subtotal=line_total, total=line_total,
                                     options_json=json.dumps(options, ensure_ascii=False)))

    db.session.add(order)
    try:
        db.session.commit()
    except IntegrityError:
        # Dois caminhos (webhook e polling) salvaram o mesmo pedido ao mesmo tempo
        db.session.rollback()
        return Order.query.filter_by(external_id=order_id).first()
    print(f"[iFood][save_order] pedido={order_id} | store_id={store_id} | novo={is_new} | status={order.status} | itens={len(order.items)}")
    return order


def _store_for_merchant(merchant_id) -> int | None:
    if not merchant_id:
        return None
    config = StoreConfig.query.filter_by(ifood_merchant_id=str(merchant_id)).first()
    return config.store_id if config else None


def process_event(event: dict) -> str:
    """Aplica um evento do iFood. Retorna o que foi feito (para log/teste)."""
    code = str(event.get("code") or "").upper()
    full_code = str(event.get("fullCode") or "").upper()
    if code in IGNORED_CODES or full_code in IGNORED_CODES:
        return "ignorado"
    order_id = event.get("orderId")
    if not order_id:
        return "sem pedido"
    with _processing_lock:
        order = Order.query.filter_by(external_id=order_id).first()
        if order is None or code in PLACED_CODES or full_code in PLACED_CODES:
            store_id = order.store_id if order else _store_for_merchant(event.get("merchantId"))
            if store_id is None:
                print(f"[iFood][evento] loja do iFood {event.get('merchantId')} não está ligada a nenhum restaurante do PDV")
                return "loja não vinculada"
            details = ifood_client.get_order(order_id)
            if not details:
                return "detalhes indisponíveis"
            order = save_order_from_ifood(details, store_id)
            if order is None:
                return "erro ao salvar"
        status, stage = EVENT_MAP.get(code) or EVENT_MAP.get(full_code) or (None, None)
        changed = False
        if status:
            changed |= delivery_stages.advance_status(order, status)
        if stage:
            changed |= delivery_stages.advance_stage(order, stage)
        if changed:
            db.session.commit()
        return f"{full_code or code}: status={order.status} etapa={order.delivery_stage}"


# -----------------------------------------------------------------------------
#  Webhook
# -----------------------------------------------------------------------------

@ifood_bp.post("/webhook")
def webhook():
    raw = request.get_data()
    if not ifood_client.validate_webhook_signature(raw, request.headers.get("X-IFood-Signature")):
        print("[iFood][webhook] REJEITADO (401): assinatura inválida")
        return jsonify({"error": "Invalid signature"}), 401
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return jsonify({"error": "Invalid JSON"}), 400
    events = payload if isinstance(payload, list) else [payload]
    for event in events:
        if isinstance(event, dict):
            try:
                print(f"[iFood][webhook] {process_event(event)}")
            except Exception as e:
                db.session.rollback()
                print(f"[iFood][webhook] ERRO ao processar evento: {type(e).__name__}: {e}")
    return "", 202


# -----------------------------------------------------------------------------
#  Polling (chamado pelo PDV aberto) e vínculo da loja
# -----------------------------------------------------------------------------

def _account_merchants() -> dict[str, int]:
    merchants = {}
    for store in g.current_user.stores:
        config = StoreConfig.query.get(store.id)
        if config and config.ifood_merchant_id:
            merchants[config.ifood_merchant_id] = store.id
    return merchants


@ifood_bp.post("/poll")
@login_required
def poll():
    if not ifood_client.is_configured():
        return jsonify({"configured": False, "events": 0})
    merchants = _account_merchants()
    if not merchants:
        return jsonify({"configured": True, "linked": False, "events": 0})
    now = time.monotonic()
    if now - _last_poll.get(g.current_user.id, -POLL_INTERVAL_SECONDS) < POLL_INTERVAL_SECONDS:
        return jsonify({"configured": True, "linked": True, "events": 0, "skipped": True})
    _last_poll[g.current_user.id] = now

    events = ifood_client.poll_events(list(merchants))
    done, results = [], []
    for event in events:
        if str(event.get("merchantId")) not in merchants:
            continue  # evento de loja de outra conta: não confirmamos por ela
        try:
            results.append(process_event(event))
            done.append(event.get("id"))
        except Exception as e:
            db.session.rollback()
            print(f"[iFood][poll] ERRO no evento {event.get('id')}: {type(e).__name__}: {e}")
    ifood_client.acknowledge_events([i for i in done if i])
    if events:
        print(f"[iFood][poll] user_id={g.current_user.id} | eventos={len(events)} | processados={len(done)} | {results}")
    return jsonify({"configured": True, "linked": True, "events": len(done)})


@ifood_bp.get("/status")
@login_required
def status():
    config = StoreConfig.query.get(g.current_user.store.id) if g.current_user.store else None
    return jsonify({"configured": ifood_client.is_configured(),
                    "merchantId": config.ifood_merchant_id if config else None})


@ifood_bp.get("/merchants")
@login_required
def merchants():
    """Lojas do iFood que autorizaram o app (no teste: a loja de teste)."""
    if not ifood_client.is_configured():
        return jsonify({"error": "Credenciais do iFood ainda não configuradas no servidor."}), 400
    if rate_limited(f"ifood-merchants:{g.current_user.id}", limit=20, window_seconds=600):
        return jsonify({"error": "Muitas consultas seguidas. Tente de novo em alguns minutos."}), 429
    return jsonify([{"id": m.get("id"), "name": m.get("name") or m.get("corporateName")} for m in ifood_client.list_merchants() if isinstance(m, dict)])


@ifood_bp.put("/merchant")
@login_required
def link_merchant():
    """Liga (ou desliga, com vazio) a loja do iFood ao restaurante selecionado."""
    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    config = StoreConfig.query.get(store.id)
    merchant_id = str((request.get_json(silent=True) or {}).get("merchantId") or "").strip()
    if not merchant_id:
        config.ifood_merchant_id = None
        db.session.commit()
        return jsonify({"merchantId": None})
    if not ifood_client.is_configured():
        return jsonify({"error": "Credenciais do iFood ainda não configuradas no servidor."}), 400
    owner = StoreConfig.query.filter_by(ifood_merchant_id=merchant_id).first()
    if owner and owner.store_id != store.id:
        return jsonify({"error": "Esta loja do iFood já está ligada a outro restaurante."}), 409
    merchant = ifood_client.get_merchant(merchant_id)
    if not merchant:
        return jsonify({"error": "O iFood não liberou o acesso a esta loja. Confira o ID ou a autorização do app."}), 400
    config.ifood_merchant_id = merchant_id
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Esta loja do iFood já está ligada a outro restaurante."}), 409
    return jsonify({"merchantId": merchant_id, "name": merchant.get("name") or merchant.get("corporateName")})


@ifood_bp.post("/publish-menu")
@login_required
def publish_menu():
    """"Publicar no iFood": envia o cardápio do restaurante selecionado."""
    import menu_publish
    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    if rate_limited(f"ifood-publish:{store.id}", limit=6, window_seconds=600):
        return jsonify({"error": "Muitas publicações seguidas. Aguarde alguns minutos."}), 429
    result = menu_publish.publish_ifood(store.id)
    if result.get("error"):
        return jsonify(result), 400
    result["status"] = menu_publish.ifood_status(store.id)
    return jsonify(result), 200 if result["ok"] else 207

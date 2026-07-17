# =============================================================================
#  routes/orders.py  —  Endpoints de Pedidos
# =============================================================================
#
#  Gerencia os pedidos do PDV: listar, criar manualmente, atualizar status.
#  Quando o status muda, notificamos a Keeta automaticamente.
# =============================================================================

import random
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import db
from models import Order, OrderItem, StoreConfig
import keeta_client
import threading

orders_bp = Blueprint("orders", __name__)


# -----------------------------------------------------------------------------
#  GET /api/orders/store/<store_id>
#  Lista todos os pedidos de uma loja específica
# -----------------------------------------------------------------------------
@orders_bp.get("/store/<int:store_id>")
def list_orders(store_id):
    orders = Order.query.filter_by(store_id=store_id).all()
    return jsonify([o.to_dict() for o in orders])


# -----------------------------------------------------------------------------
#  GET /api/orders/<id>
#  Retorna um pedido específico pelo ID interno
# -----------------------------------------------------------------------------
@orders_bp.get("/<int:order_id>")
def get_order(order_id):
    order = Order.query.get_or_404(order_id)
    return jsonify(order.to_dict())


# -----------------------------------------------------------------------------
#  GET /api/orders/active-store
#  Descobre qual é a loja ativa olhando o último pedido criado
# -----------------------------------------------------------------------------
@orders_bp.get("/active-store")
def get_active_store():
    last_order = Order.query.order_by(Order.id.desc()).first()
    store_id = last_order.store_id if last_order else 1
    return jsonify({"storeId": store_id})


# -----------------------------------------------------------------------------
#  POST /api/orders
#  Cria um pedido manual (pedido de balcão, sem integração Keeta)
# -----------------------------------------------------------------------------
@orders_bp.post("/")
def create_order():
    data = request.get_json()

    order = Order(
        store_id=data.get("storeId", 1),
        status="NEW",
        customer_name="Cliente Balcão",
        payment_type="BALCAO",
        display_id=str(random.randint(1000, 9999)),
        delivery_address="Retirada",
        created_at=datetime.now().isoformat(),
        total_price=0.0,
        discount=0.0,
    )

    total = 0.0
    for item_data in data.get("items", []):
        item = OrderItem(
            menu_item_id=item_data.get("menuItemId"),
            menu_item_name=f"Item #{item_data.get('menuItemId')}",
            quantity=item_data.get("quantity", 1),
            unit_price=10.0,
            original_price=10.0,
            subtotal=10.0 * item_data.get("quantity", 1),
            total=10.0 * item_data.get("quantity", 1),
        )
        order.items.append(item)
        total += item.total

    order.total_price = total

    db.session.add(order)
    db.session.commit()

    return jsonify(order.to_dict()), 201


# -----------------------------------------------------------------------------
#  PATCH /api/orders/<id>/status
#  Atualiza o status de um pedido e notifica a Keeta na mesma operação
# -----------------------------------------------------------------------------
@orders_bp.patch("/<int:order_id>/status")
def update_status(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    new_status = data.get("status")

    old_status = order.status

    # --- Notificações para a Keeta (em thread separada para não bloquear a resposta) ---
    # A ideia é: o operador muda o status no PDV → o PDV avisa a Keeta

    if order.external_id:
        def notify_keeta():
            if old_status == "NEW" and new_status == "PREPARING":
                # Operador aceitou manualmente → confirmar na Keeta
                keeta_client.confirm_order(order.external_id)

            elif new_status == "READY_FOR_PICKUP":
                # Pedido ficou pronto → avisar Keeta para despachar motoboy
                keeta_client.notify_ready_for_pickup(order.external_id)

            elif new_status == "DELIVERY_IN_PROGRESS":
                # Motoboy saiu → avisar Keeta
                keeta_client.notify_dispatched(order.external_id)

            elif new_status == "CANCELED":
                # Pedido cancelado → solicitar cancelamento na Keeta
                keeta_client.request_cancellation(order.external_id)

        threading.Thread(target=notify_keeta, daemon=True).start()

    order.status = new_status
    db.session.commit()

    return jsonify(order.to_dict())


# =============================================================================
#  FUNÇÃO DE SERVIÇO (usada pelo webhook)
# =============================================================================

def save_order_from_keeta(order_json: dict, local_merchant_id: str):
    """
    Recebe o JSON completo de um pedido da Keeta e salva/atualiza no banco.

    Esta função é o coração da integração: ela faz o "de/para" entre
    os campos da Keeta e os campos do nosso banco de dados.

    Chamada pelo webhook quando chega um evento de novo pedido.
    """
    keeta_id = order_json.get("id")
    if not keeta_id:
        print("[Orders] JSON de pedido sem ID, ignorando.")
        return

    # Busca pedido existente ou cria um novo
    order = Order.query.filter_by(external_id=keeta_id).first() or Order()

    if not order.id:
        order.external_id = keeta_id

    # --- Define a loja local ---
    try:
        order.store_id = int(local_merchant_id)
    except Exception:
        order.store_id = order.store_id or 1

    # --- Status inicial ---
    # Se o pedido ainda não tem status, verificamos se o auto-aceite está ativo
    if not order.status:
        config = StoreConfig.query.get(1) or StoreConfig(id=1, auto_accept=True)

        if config.auto_accept:
            order.status = "PREPARING"
            # Confirma na Keeta em background sem bloquear a resposta do webhook
            threading.Thread(
                target=keeta_client.confirm_order,
                args=(keeta_id,),
                daemon=True,
            ).start()
        else:
            order.status = "NEW"

    # --- Dados de identificação ---
    delivery = order_json.get("delivery", {})
    pickup_code = delivery.get("pickupCode") or order_json.get("displayId")
    order.pickup_code = pickup_code
    order.display_id  = order_json.get("displayId")
    order.created_at  = order_json.get("createdAt")

    # --- Cliente ---
    customer = order_json.get("customer", {})
    order.customer_name = customer.get("name", "Cliente")

    # --- Valores financeiros ---
    total_node = order_json.get("total", {})
    order_amount = total_node.get("orderAmount", {})
    if "value" in order_amount:
        order.total_price = order_amount["value"]

    discount_node = total_node.get("discount", {})
    if "value" in discount_node:
        order.discount = discount_node["value"]

    # --- Tipo de pagamento ---
    payments = order_json.get("payments", {})
    if payments.get("prepaid", 0) > 0:
        order.payment_type = "ONLINE"
    else:
        order.payment_type = "NA_ENTREGA"

    # --- Endereço de entrega ---
    delivery_address = delivery.get("deliveryAddress", {})
    order.delivery_address = delivery_address.get("formattedAddress", "Retirada / Não informado")
    coords = delivery_address.get("coordinates", {})
    if "latitude" in coords:
        order.latitude  = coords["latitude"]
        order.longitude = coords["longitude"]

    # --- JSONs brutos para auditoria ---
    import json
    order.fees_json      = json.dumps(order_json.get("otherFees", []))
    order.discounts_json = json.dumps(order_json.get("discounts", []))

    # --- Itens do pedido ---
    if order.items:
        order.items.clear()

    for item_node in order_json.get("items", []):
        # Monta o nome completo: nome base + opções + observações
        base_name = item_node.get("name", "Item")
        full_name = base_name

        options = item_node.get("options", [])
        if options:
            opt_names = [o.get("name", "") for o in options]
            full_name += f" ({', '.join(opt_names)})"

        instructions = item_node.get("specialInstructions", "")
        if instructions:
            clean = instructions.replace("~_", "")
            full_name += f" [Obs: {clean}]"

        unit_price = item_node.get("unitPrice", {}).get("value", 0.0)
        total_price = item_node.get("totalPrice", {}).get("value", 0.0)
        original_price = item_node.get("originalPrice", {}).get("value", unit_price)

        order_item = OrderItem(
            menu_item_id=0,
            menu_item_name=full_name,
            quantity=item_node.get("quantity", 1),
            unit_price=unit_price,
            original_price=original_price,
            subtotal=total_price,
            total=total_price,
        )
        order.items.append(order_item)

    db.session.add(order)
    db.session.commit()
    print(f"[Orders] Pedido {keeta_id} salvo/atualizado no banco.")

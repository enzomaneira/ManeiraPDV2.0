# =============================================================================
#  routes/orders.py  —  Endpoints de Pedidos
# =============================================================================
#
#  Gerencia os pedidos do PDV: listar, criar manualmente, atualizar status.
#  Quando o status muda, notificamos a Keeta automaticamente.
#
#  Todas as rotas usam o usuário logado (g.current_user) para descobrir
#  qual é a loja (store_id) que deve ser consultada/alterada.
# =============================================================================

import random
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from database import db
from models import Order, OrderItem, StoreConfig
from auth_utils import login_required
import keeta_client
import threading

orders_bp = Blueprint("orders", __name__)


# -----------------------------------------------------------------------------
#  GET /api/orders
#  Lista todos os pedidos da loja do usuário logado
# -----------------------------------------------------------------------------
@orders_bp.get("/")
@login_required
def list_orders():
    print(f"\n[Orders][list_orders] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    if not store:
        print(f"[Orders][list_orders] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    print(f"[Orders][list_orders] Buscando pedidos para store_id={store.id}...")
    orders = Order.query.filter_by(store_id=store.id).all()
    print(f"[Orders][list_orders] {len(orders)} pedido(s) encontrado(s) | status={[o.status for o in orders]}")

    result = [o.to_dict() for o in orders]
    print(f"[Orders][list_orders] FIM (sucesso) | store_id={store.id} | total={len(result)}")
    return jsonify(result)


# -----------------------------------------------------------------------------
#  GET /api/orders/<id>
#  Retorna um pedido específico pelo ID interno (somente se for da sua loja)
# -----------------------------------------------------------------------------
@orders_bp.get("/<int:order_id>")
@login_required
def get_order(order_id):
    print(f"\n[Orders][get_order] INÍCIO | user_id={g.current_user.id} | order_id={order_id}")

    store = g.current_user.store
    order = Order.query.get_or_404(order_id)
    print(f"[Orders][get_order] Pedido encontrado no banco: id={order.id} | store_id={order.store_id} | status={order.status}")

    if not store or order.store_id != store.id:
        print(f"[Orders][get_order] FALHA (404): pedido não pertence ao usuário | order.store_id={order.store_id} | user.store_id={store.id if store else None}")
        return jsonify({"error": "Pedido não encontrado."}), 404

    print(f"[Orders][get_order] FIM (sucesso) | order_id={order_id}")
    return jsonify(order.to_dict())


# -----------------------------------------------------------------------------
#  POST /api/orders
#  Cria um pedido manual (pedido de balcão, sem integração Keeta)
# -----------------------------------------------------------------------------
@orders_bp.post("/")
@login_required
def create_order():
    print(f"\n[Orders][create_order] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    if not store:
        print(f"[Orders][create_order] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Orders][create_order] Body recebido: {data}")

    order = Order(
        store_id=store.id,
        status="NEW",
        customer_name="Cliente Balcão",
        payment_type="BALCAO",
        display_id=str(random.randint(1000, 9999)),
        delivery_address="Retirada",
        created_at=datetime.now().isoformat(),
        total_price=0.0,
        discount=0.0,
    )
    print(f"[Orders][create_order] Objeto Order montado: display_id={order.display_id} | store_id={store.id}")

    total = 0.0
    items_data = data.get("items", [])
    print(f"[Orders][create_order] Processando {len(items_data)} item(ns)...")

    for item_data in items_data:
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
        print(f"[Orders][create_order] Item adicionado: menu_item_id={item.menu_item_id} | quantity={item.quantity} | total={item.total}")

    order.total_price = total
    print(f"[Orders][create_order] Total calculado do pedido: {total}")

    try:
        db.session.add(order)
        db.session.commit()
        print(f"[Orders][create_order] Commit realizado com sucesso | order_id={order.id}")
    except Exception as e:
        db.session.rollback()
        print(f"[Orders][create_order] ERRO ao salvar pedido. Rollback executado. Detalhes: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao criar pedido."}), 500

    print(f"[Orders][create_order] FIM (sucesso) | order_id={order.id} | store_id={store.id}")
    return jsonify(order.to_dict()), 201


# -----------------------------------------------------------------------------
#  PATCH /api/orders/<id>/status
#  Atualiza o status de um pedido e notifica a Keeta na mesma operação
# -----------------------------------------------------------------------------
@orders_bp.patch("/<int:order_id>/status")
@login_required
def update_status(order_id):
    print(f"\n[Orders][update_status] INÍCIO | user_id={g.current_user.id} | order_id={order_id}")

    store = g.current_user.store
    order = Order.query.get_or_404(order_id)
    print(f"[Orders][update_status] Pedido encontrado: id={order.id} | store_id={order.store_id} | status_atual={order.status} | external_id={order.external_id}")

    if not store or order.store_id != store.id:
        print(f"[Orders][update_status] FALHA (404): pedido não pertence ao usuário | order.store_id={order.store_id} | user.store_id={store.id if store else None}")
        return jsonify({"error": "Pedido não encontrado."}), 404

    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    print(f"[Orders][update_status] Body recebido: {data} | novo_status='{new_status}'")

    old_status = order.status
    print(f"[Orders][update_status] Transição de status: '{old_status}' → '{new_status}'")

    # --- Notificações para a Keeta (em thread separada para não bloquear a resposta) ---
    # A ideia é: o operador muda o status no PDV → o PDV avisa a Keeta

    if order.external_id:
        print(f"[Orders][update_status] Pedido possui external_id={order.external_id}. Disparando notificação assíncrona para a Keeta...")

        def notify_keeta():
            print(f"[Orders][update_status][thread] INÍCIO notificação Keeta | external_id={order.external_id} | old_status={old_status} | new_status={new_status}")
            try:
                if old_status == "NEW" and new_status == "PREPARING":
                    print(f"[Orders][update_status][thread] Chamando keeta_client.confirm_order({order.external_id})")
                    resultado = keeta_client.confirm_order(order.external_id)
                    print(f"[Orders][update_status][thread] Resultado confirm_order: {resultado}")

                elif new_status == "READY_FOR_PICKUP":
                    print(f"[Orders][update_status][thread] Chamando keeta_client.notify_ready_for_pickup({order.external_id})")
                    resultado = keeta_client.notify_ready_for_pickup(order.external_id)
                    print(f"[Orders][update_status][thread] Resultado notify_ready_for_pickup: {resultado}")

                elif new_status == "DELIVERY_IN_PROGRESS":
                    print(f"[Orders][update_status][thread] Chamando keeta_client.notify_dispatched({order.external_id})")
                    resultado = keeta_client.notify_dispatched(order.external_id)
                    print(f"[Orders][update_status][thread] Resultado notify_dispatched: {resultado}")

                elif new_status == "CANCELED":
                    print(f"[Orders][update_status][thread] Chamando keeta_client.request_cancellation({order.external_id})")
                    resultado = keeta_client.request_cancellation(order.external_id)
                    print(f"[Orders][update_status][thread] Resultado request_cancellation: {resultado}")
                else:
                    print(f"[Orders][update_status][thread] Nenhuma ação de notificação necessária para essa transição.")
            except Exception as e:
                print(f"[Orders][update_status][thread] ERRO ao notificar Keeta: {type(e).__name__}: {e}")
            print(f"[Orders][update_status][thread] FIM notificação Keeta | external_id={order.external_id}")

        threading.Thread(target=notify_keeta, daemon=True).start()
    else:
        print(f"[Orders][update_status] Pedido sem external_id (pedido manual). Nenhuma notificação à Keeta será enviada.")

    order.status = new_status
    db.session.commit()
    print(f"[Orders][update_status] Commit realizado | order_id={order.id} | status_final={order.status}")

    print(f"[Orders][update_status] FIM (sucesso) | order_id={order_id}")
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
    `local_merchant_id` é o store_id (da nossa base) da loja dona do pedido.
    """
    print(f"\n[Orders][save_order_from_keeta] INÍCIO | local_merchant_id={local_merchant_id}")
    print(f"[Orders][save_order_from_keeta] JSON recebido (chaves de topo): {list(order_json.keys())}")

    # A Keeta pode encapsular a resposta em {code, message, data, extend}.
    # Nesse caso, o pedido real está dentro do campo `data`.
    if "data" in order_json and "code" in order_json:
        order_json = order_json["data"]
        print(f"[Orders][save_order_from_keeta] JSON desencapsulado de 'data'. Novas chaves: {list(order_json.keys())}")

    keeta_id = order_json.get("id")
    print(f"[Orders][save_order_from_keeta] keeta_id extraído: {keeta_id}")

    if not keeta_id:
        print("[Orders][save_order_from_keeta] FIM (ignorado): JSON de pedido sem ID.")
        return

    # Busca pedido existente ou cria um novo
    print(f"[Orders][save_order_from_keeta] Buscando pedido existente com external_id={keeta_id}...")
    order = Order.query.filter_by(external_id=keeta_id).first() or Order()
    is_new = not order.id
    print(f"[Orders][save_order_from_keeta] Pedido {'NOVO (será criado)' if is_new else f'EXISTENTE (id={order.id}, será atualizado)'}")

    if not order.id:
        order.external_id = keeta_id

    # --- Define a loja local ---
    try:
        order.store_id = int(local_merchant_id)
        print(f"[Orders][save_order_from_keeta] store_id definido: {order.store_id}")
    except Exception as e:
        order.store_id = order.store_id or 1
        print(f"[Orders][save_order_from_keeta] ERRO ao converter local_merchant_id='{local_merchant_id}' para int: {e}. Usando fallback store_id={order.store_id}")

    # --- Status inicial ---
    # Se o pedido ainda não tem status, verificamos se o auto-aceite está ativo
    if not order.status:
        print(f"[Orders][save_order_from_keeta] Pedido sem status definido. Verificando auto_accept para store_id={order.store_id}...")
        config = StoreConfig.query.get(order.store_id)
        auto_accept = config.auto_accept if config else True
        print(f"[Orders][save_order_from_keeta] Config encontrada: {config.to_dict() if config else None} | auto_accept={auto_accept}")

        if auto_accept:
            order.status = "PREPARING"
            print(f"[Orders][save_order_from_keeta] Auto-aceite ATIVO. Status definido como PREPARING. Disparando confirm_order em background...")
            # Confirma na Keeta em background sem bloquear a resposta do webhook
            threading.Thread(
                target=keeta_client.confirm_order,
                args=(keeta_id,),
                daemon=True,
            ).start()
        else:
            order.status = "NEW"
            print(f"[Orders][save_order_from_keeta] Auto-aceite INATIVO. Status definido como NEW (aguardando aprovação manual).")

    # --- Dados de identificação ---
    delivery = order_json.get("delivery", {})
    pickup_code = delivery.get("pickupCode") or order_json.get("displayId")
    order.pickup_code = pickup_code
    order.display_id  = order_json.get("displayId")
    order.created_at  = order_json.get("createdAt")
    print(f"[Orders][save_order_from_keeta] Identificação: pickup_code={pickup_code} | display_id={order.display_id} | created_at={order.created_at}")

    # --- Cliente ---
    customer = order_json.get("customer", {})
    order.customer_name = customer.get("name", "Cliente")
    print(f"[Orders][save_order_from_keeta] Cliente: {order.customer_name}")

    # --- Valores financeiros ---
    total_node = order_json.get("total", {})
    order_amount = total_node.get("orderAmount", {})
    if "value" in order_amount:
        order.total_price = order_amount["value"]

    discount_node = total_node.get("discount", {})
    if "value" in discount_node:
        order.discount = discount_node["value"]

    print(f"[Orders][save_order_from_keeta] Financeiro: total_price={order.total_price} | discount={order.discount}")

    # --- Tipo de pagamento ---
    payments = order_json.get("payments", {})
    if payments.get("prepaid", 0) > 0:
        order.payment_type = "ONLINE"
    else:
        order.payment_type = "NA_ENTREGA"
    print(f"[Orders][save_order_from_keeta] payment_type={order.payment_type}")

    # --- Endereço de entrega ---
    delivery_address = delivery.get("deliveryAddress", {})
    order.delivery_address = delivery_address.get("formattedAddress", "Retirada / Não informado")
    coords = delivery_address.get("coordinates", {})
    if "latitude" in coords:
        order.latitude  = coords["latitude"]
        order.longitude = coords["longitude"]
    print(f"[Orders][save_order_from_keeta] Endereço: {order.delivery_address} | lat={order.latitude} | lng={order.longitude}")

    # --- JSONs brutos para auditoria ---
    import json
    order.fees_json      = json.dumps(order_json.get("otherFees", []))
    order.discounts_json = json.dumps(order_json.get("discounts", []))

    # --- Itens do pedido ---
    if order.items:
        print(f"[Orders][save_order_from_keeta] Limpando {len(order.items)} item(ns) antigo(s) antes de recriar...")
        order.items.clear()

    items_raw = order_json.get("items", [])
    print(f"[Orders][save_order_from_keeta] Processando {len(items_raw)} item(ns) do pedido...")

    for item_node in items_raw:
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
        print(f"[Orders][save_order_from_keeta] Item processado: '{full_name}' | qty={order_item.quantity} | total={total_price}")

    try:
        db.session.add(order)
        db.session.commit()
        print(f"[Orders][save_order_from_keeta] COMMIT bem-sucedido | order_id={order.id} | keeta_id={keeta_id} | status={order.status}")
    except Exception as e:
        db.session.rollback()
        print(f"[Orders][save_order_from_keeta] ERRO ao salvar pedido. Rollback executado. Detalhes: {type(e).__name__}: {e}")

    print(f"[Orders][save_order_from_keeta] FIM | keeta_id={keeta_id}")

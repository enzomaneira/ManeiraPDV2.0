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

import json
import random
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from database import db
from models import Order, OrderItem, StoreConfig
from auth_utils import login_required, rate_limited
import keeta_client
import ifood_client
import delivery_stages
import refunds
import threading

orders_bp = Blueprint("orders", __name__)


def option_labels(options) -> list[str]:
    """Rótulos dos complementos de um item, juntando repetidos e mostrando a
    quantidade: [Bacon (1), Bacon (1), Cheddar] -> ["2x Bacon", "Cheddar"].
    A Keeta pode mandar o mesmo complemento com quantity 2 ou repetido na lista."""
    totals: dict[str, float] = {}
    for option in options or []:
        if not isinstance(option, dict):
            continue
        name = str(option.get("name") or "").strip()
        if not name:
            continue
        quantity = option.get("quantity")
        quantity = quantity if isinstance(quantity, (int, float)) and quantity > 0 else 1
        totals[name] = totals.get(name, 0) + quantity
    labels = []
    for name, quantity in totals.items():
        quantity = int(quantity) if float(quantity).is_integer() else quantity
        labels.append(f"{quantity}x {name}" if quantity != 1 else name)
    return labels


def _account_store_ids() -> list[int]:
    """Restaurantes (marcas) da conta logada. O quadro de pedidos é da cozinha:
    mostra e deixa agir nos pedidos de todas as marcas, não só da selecionada."""
    return [store.id for store in g.current_user.stores]


def _account_order(order_id):
    """Pedido de qualquer restaurante da conta, ou None (vira 404)."""
    order = Order.query.get(order_id)
    return order if order and order.store_id in _account_store_ids() else None


# -----------------------------------------------------------------------------
#  GET /api/orders
#  Lista todos os pedidos da loja do usuário logado
# -----------------------------------------------------------------------------
@orders_bp.get("/")
@login_required
def list_orders():
    print(f"\n[Orders][list_orders] INÍCIO | user_id={g.current_user.id}")

    store_ids = _account_store_ids()
    if not store_ids:
        print(f"[Orders][list_orders] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    orders = Order.query.filter(Order.store_id.in_(store_ids)).all()
    names = {store.id: store.name for store in g.current_user.stores}
    result = []
    for order in orders:
        data = order.to_dict()
        data["storeName"] = names.get(order.store_id)
        result.append(data)
    print(f"[Orders][list_orders] FIM (sucesso) | store_ids={store_ids} | total={len(result)}")
    return jsonify(result)


# -----------------------------------------------------------------------------
#  GET /api/orders/<id>
#  Retorna um pedido específico pelo ID interno (somente se for da sua loja)
# -----------------------------------------------------------------------------
@orders_bp.get("/<int:order_id>")
@login_required
def get_order(order_id):
    print(f"\n[Orders][get_order] INÍCIO | user_id={g.current_user.id} | order_id={order_id}")

    order = _account_order(order_id)
    if not order:
        print(f"[Orders][get_order] FALHA (404): pedido não encontrado nas lojas da conta | order_id={order_id}")
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
        platform="BALCAO",
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

    order = _account_order(order_id)
    if not order:
        print(f"[Orders][update_status] FALHA (404): pedido não encontrado nas lojas da conta | order_id={order_id}")
        return jsonify({"error": "Pedido não encontrado."}), 404
    print(f"[Orders][update_status] Pedido encontrado: id={order.id} | store_id={order.store_id} | status_atual={order.status} | external_id={order.external_id}")

    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    print(f"[Orders][update_status] Body recebido: {data} | novo_status='{new_status}'")

    old_status = order.status
    print(f"[Orders][update_status] Transição de status: '{old_status}' → '{new_status}'")

    # --- Notificações para a Keeta (em thread separada para não bloquear a resposta) ---
    # A ideia é: o operador muda o status no PDV → o PDV avisa a Keeta

    # Valores lidos antes da thread: depois do commit o objeto expira e não
    # pode ser recarregado fora do contexto da requisição.
    external_id = order.external_id
    delivery = _delivery_info(order)
    own_delivery = delivery.get("deliveredBy") != "MARKETPLACE"
    is_ifood = order.platform == "IFOOD"

    if external_id and is_ifood:
        def notify_ifood():
            try:
                if old_status in ("PENDING", "NEW") and new_status == "PREPARING":
                    ifood_client.confirm_order(external_id)
                elif new_status == "READY_FOR_PICKUP":
                    # Retirada no balcão ou entregador do iFood: avisa que está pronto
                    if not own_delivery or delivery.get("orderType") == "TAKEOUT":
                        ifood_client.ready_to_pickup(external_id)
                elif new_status == "DELIVERY_IN_PROGRESS" and own_delivery:
                    ifood_client.dispatch_order(external_id)
                elif new_status == "CANCELED":
                    ifood_client.request_cancellation(external_id)
                # COMPLETED: o iFood conclui o pedido sozinho
            except Exception as e:
                print(f"[Orders][update_status][iFood] ERRO ao notificar: {type(e).__name__}: {e}")
        threading.Thread(target=notify_ifood, daemon=True).start()
    elif external_id:
        print(f"[Orders][update_status] Pedido possui external_id={external_id}. Disparando notificação assíncrona para a Keeta...")

        def notify_keeta():
            print(f"[Orders][update_status][thread] INÍCIO notificação Keeta | external_id={external_id} | old_status={old_status} | new_status={new_status}")
            try:
                # Confirmar: de PENDING ou NEW para PREPARING → confirma na Keeta
                if old_status in ("PENDING", "NEW") and new_status == "PREPARING":
                    resultado = keeta_client.confirm_order(external_id)
                    print(f"[Orders][update_status][thread] Resultado confirm_order: {resultado}")

                elif new_status == "READY_FOR_PICKUP":
                    resultado = keeta_client.notify_ready_for_pickup(external_id)
                    print(f"[Orders][update_status][thread] Resultado notify_ready_for_pickup: {resultado}")

                # Despacho e entrega só existem na entrega própria; na entrega da
                # Keeta quem informa é o entregador dela.
                elif new_status == "DELIVERY_IN_PROGRESS" and own_delivery:
                    resultado = keeta_client.dispatch_own_delivery(external_id)
                    print(f"[Orders][update_status][thread] Resultado dispatch: {resultado}")

                elif new_status == "COMPLETED" and own_delivery:
                    resultado = keeta_client.notify_delivered(external_id)
                    print(f"[Orders][update_status][thread] Resultado delivered: {resultado}")

                # Cancelar/Recusar: de qualquer status para CANCELED → cancela na Keeta
                elif new_status == "CANCELED":
                    resultado = keeta_client.request_cancellation(external_id)
                    print(f"[Orders][update_status][thread] Resultado request_cancellation: {resultado}")
                else:
                    print(f"[Orders][update_status][thread] Nenhuma ação de notificação necessária para essa transição.")
            except Exception as e:
                print(f"[Orders][update_status][thread] ERRO ao notificar Keeta: {type(e).__name__}: {e}")
            print(f"[Orders][update_status][thread] FIM notificação Keeta | external_id={external_id}")

        threading.Thread(target=notify_keeta, daemon=True).start()
    else:
        print(f"[Orders][update_status] Pedido sem external_id (pedido manual). Nenhuma notificação à Keeta será enviada.")

    # A etapa da entrega acompanha o despacho e a conclusão feitos pelo botão simples
    if new_status == "DELIVERY_IN_PROGRESS" and own_delivery:
        delivery_stages.advance_stage(order, "DELIVERY_ONGOING")
    elif new_status == "COMPLETED" and own_delivery:
        delivery_stages.advance_stage(order, "ORDER_DELIVERED")

    order.status = new_status
    db.session.commit()
    print(f"[Orders][update_status] Commit realizado | order_id={order.id} | status_final={order.status}")

    print(f"[Orders][update_status] FIM (sucesso) | order_id={order_id}")
    return jsonify(order.to_dict())


# =============================================================================
#  FUNÇÃO DE SERVIÇO (usada pelo webhook)
# =============================================================================

# -----------------------------------------------------------------------------
#  POST /api/orders/<id>/decrypt
#  Busca de novo o pedido na Keeta e tenta descriptografar telefone/endereço
#  (botão "Tentar novamente" nos detalhes, quando os dados ficaram protegidos)
# -----------------------------------------------------------------------------
@orders_bp.post("/<int:order_id>/decrypt")
@login_required
def retry_decrypt(order_id):
    order = _account_order(order_id)
    if not order:
        return jsonify({"error": "Pedido não encontrado."}), 404
    if not order.external_id:
        return jsonify({"error": "Este pedido não veio da Keeta."}), 400
    if rate_limited(f"decrypt:{order.id}", limit=10, window_seconds=600):
        return jsonify({"error": "Muitas tentativas. Aguarde alguns minutos e tente de novo."}), 429

    if order.platform == "IFOOD":
        from routes.ifood import save_order_from_ifood
        details = ifood_client.get_order(order.external_id)
        if not details:
            return jsonify({"error": "Não foi possível buscar o pedido no iFood. Tente de novo em instantes."}), 502
        save_order_from_ifood(details, order.store_id)
        db.session.refresh(order)
        return jsonify(order.to_dict())
    order_data = keeta_client.get_order_details(order.external_id)
    if not order_data:
        return jsonify({"error": "Não foi possível buscar o pedido na Keeta. Tente de novo em instantes."}), 502
    save_order_from_keeta(order_data, order.store_id)
    db.session.refresh(order)
    result = order.to_dict()
    print(f"[Orders][retry_decrypt] order_id={order.id} | ainda_protegido={result['dataProtected']}")
    return jsonify(result)


def _delivery_info(order) -> dict:
    try:
        info = json.loads(order.delivery_json) if order.delivery_json else {}
    except (TypeError, ValueError):
        info = {}
    return info if isinstance(info, dict) else {}


# Etapas que o restaurante pode marcar na entrega própria, e o status que cada
# uma exige antes (o motoboy pode chegar enquanto ainda está no preparo, mas
# só coleta/sai com o pedido pronto).
OWN_STAGE_MIN_STATUS = {
    "PICKUP_ONGOING":      "PREPARING",
    "ARRIVED_AT_MERCHANT": "PREPARING",
    "ORDER_PICKED":        "READY_FOR_PICKUP",
    "DELIVERY_ONGOING":    "READY_FOR_PICKUP",
    "ARRIVED_AT_CUSTOMER": "READY_FOR_PICKUP",
    "ORDER_DELIVERED":     "READY_FOR_PICKUP",
}


# -----------------------------------------------------------------------------
#  PATCH /api/orders/<id>/delivery-stage   body: {"stage": "ARRIVED_AT_MERCHANT"}
#  Entrega própria: o restaurante avança a etapa e o PDV avisa a Keeta
#  (/tracking; DELIVERY_ONGOING usa /dispatch e ORDER_DELIVERED também /delivered).
# -----------------------------------------------------------------------------
@orders_bp.patch("/<int:order_id>/delivery-stage")
@login_required
def update_delivery_stage(order_id):
    order = _account_order(order_id)
    if not order:
        return jsonify({"error": "Pedido não encontrado."}), 404

    stage = (request.get_json(silent=True) or {}).get("stage")
    if stage not in OWN_STAGE_MIN_STATUS:
        return jsonify({"error": "Etapa de entrega inválida."}), 400
    delivery = _delivery_info(order)
    if delivery.get("deliveredBy") == "MARKETPLACE":
        return jsonify({"error": "Este pedido é entregue pela Keeta: as etapas vêm do entregador dela."}), 400
    if order.status in delivery_stages.FINAL_STATUSES:
        return jsonify({"error": "O pedido já foi concluído ou cancelado."}), 400
    if delivery_stages.STATUS_RANK.get(order.status, 0) < delivery_stages.STATUS_RANK[OWN_STAGE_MIN_STATUS[stage]]:
        needed = "aceito" if OWN_STAGE_MIN_STATUS[stage] == "PREPARING" else "pronto"
        return jsonify({"error": f"Marque o pedido como {needed} antes desta etapa."}), 400
    if not delivery_stages.advance_stage(order, stage):
        return jsonify({"error": "O pedido já passou desta etapa."}), 409

    if stage in ("ORDER_PICKED", "DELIVERY_ONGOING", "ARRIVED_AT_CUSTOMER"):
        delivery_stages.advance_status(order, "DELIVERY_IN_PROGRESS")
    elif stage == "ORDER_DELIVERED":
        delivery_stages.advance_status(order, "COMPLETED")
    external_id = order.external_id
    db.session.commit()  # grava antes de chamar a Keeta: falha lá não desfaz aqui

    keeta = {"sent": None, "warning": None}
    if external_id and order.platform == "IFOOD":
        # No iFood a entrega própria só tem "saiu para entrega"; as demais etapas ficam no PDV
        if stage == "DELIVERY_ONGOING":
            ok, _ = ifood_client.dispatch_order(external_id)
            keeta["sent"] = ok
            if not ok:
                keeta["warning"] = "A etapa foi salva no PDV, mas o iFood não confirmou o recebimento."
    elif external_id:
        # Na entrega própria as etapas vão sempre para a Keeta. Os campos
        # sendTracking/sendDelivered do pedido só dizem se a Keeta *espera* a
        # chamada; mesmo com false ela aceita (e o restaurante quer informar).
        calls = []
        if stage == "DELIVERY_ONGOING":
            calls.append(keeta_client.dispatch_own_delivery)
        else:
            calls.append(lambda oid: keeta_client.send_delivery_tracking(oid, stage))
            if stage == "ORDER_DELIVERED":
                calls.append(keeta_client.notify_delivered)
        results = [call(external_id) for call in calls]
        keeta["sent"] = all(ok for ok, _ in results) if results else None
        failed = [code for ok, code in results if not ok]
        if failed:
            keeta["warning"] = ("A Keeta já tinha recebido esta etapa." if all(code == 422 for code in failed)
                                else "A etapa foi salva no PDV, mas a Keeta não confirmou o recebimento.")
    print(f"[Orders][update_delivery_stage] order_id={order.id} | etapa={stage} | status={order.status} | keeta={keeta} | "
          f"sendTracking={delivery.get('sendTracking')} | sendDelivered={delivery.get('sendDelivered')}")
    return jsonify({"order": order.to_dict(), "keeta": keeta})


def _collect_encrypted(node, found: list):
    """Junta todas as strings ENC_... de um nó do pedido (qualquer profundidade)."""
    if isinstance(node, dict):
        for value in node.values():
            _collect_encrypted(value, found)
    elif isinstance(node, list):
        for value in node:
            _collect_encrypted(value, found)
    elif keeta_client.is_encrypted(node):
        found.append(node)
    return found


def _replace_encrypted(node, plain: dict):
    if isinstance(node, dict):
        return {k: _replace_encrypted(v, plain) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_encrypted(v, plain) for v in node]
    if keeta_client.is_encrypted(node):
        return plain.get(node, node)
    return node


def _decrypt_contact_data(customer: dict, delivery: dict):
    """Descriptografa os campos ENC_ de customer/delivery. Retorna as cópias
    descriptografadas e (quantos estavam criptografados, quantos abriram)."""
    ciphers = list(dict.fromkeys(_collect_encrypted(customer, []) + _collect_encrypted(delivery, [])))
    if not ciphers:
        return customer, delivery, (0, 0)
    if delivery.get("deliveredBy") == "MARKETPLACE":
        # Entrega feita pela Keeta: os dados do cliente nunca são liberados
        # (LGPD), então nem tentamos.
        return customer, delivery, (len(ciphers), 0)
    plain = keeta_client.batch_decrypt(ciphers)
    return _replace_encrypted(customer, plain), _replace_encrypted(delivery, plain), (len(ciphers), len(plain))


def _is_plain(value) -> bool:
    return isinstance(value, str) and value.strip() != "" and not keeta_client.is_encrypted(value)


def _text(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _merge_keep_plain(new: dict, old_raw: str | None) -> dict:
    """Se um campo continua criptografado agora (ex.: a Keeta recusou a
    descriptografia depois do fim do pedido) mas já tínhamos o valor em texto,
    mantém o valor antigo. Assim um reenvio do webhook não apaga o que já foi
    descriptografado."""
    try:
        old = json.loads(old_raw) if old_raw else {}
    except Exception:
        old = {}
    if not isinstance(old, dict):
        old = {}
    merged = dict(new)
    for key, value in new.items():
        if (value is None or keeta_client.is_encrypted(value)) and _is_plain(old.get(key)):
            merged[key] = old[key]
    return merged


def _format_address(info: dict) -> str | None:
    """Endereço em uma linha. Usa o formattedAddress da Keeta quando está em
    texto; senão monta a partir das partes (só com partes já descriptografadas)."""
    if _is_plain(info.get("formattedAddress")):
        return info["formattedAddress"].strip()
    keys = ("street", "number", "complement", "district", "city", "state", "postalCode")
    if any(keeta_client.is_encrypted(info.get(k)) for k in keys):
        return None  # endereço pela metade (ex.: sem o número) confunde mais do que ajuda
    parts = {k: info.get(k) if _is_plain(info.get(k)) else None for k in keys}
    if not parts["street"]:
        return None
    line = parts["street"] + (f", {parts['number']}" if parts["number"] else "")
    if parts["complement"]:
        line += f" - {parts['complement']}"
    place = ", ".join(p for p in (parts["district"], parts["city"]) if p)
    state = (parts["state"] or "").replace("BR-", "")
    if place or state:
        line += " - " + place + (f"/{state}" if state else "")
    if parts["postalCode"]:
        line += f" - CEP {parts['postalCode']}"
    return line


def _apply_contact_data(order: "Order", customer: dict, delivery: dict, payments: dict, flags: dict | None = None):
    """Grava nome, telefone, endereço e pagamento no pedido (já descriptografados)."""
    phone = customer.get("phone") if isinstance(customer.get("phone"), dict) else {}
    customer_info = _merge_keep_plain({
        "name":           _text(customer.get("name")),
        "phone":          _text(phone.get("number")),
        "phoneExtension": _text(phone.get("extension")),
        "documentNumber": _text(customer.get("documentNumber")),
        "email":          _text(customer.get("email")),
        "ordersCount":    customer.get("ordersCountOnMerchant"),
    }, order.customer_json)

    address = delivery.get("deliveryAddress") if isinstance(delivery.get("deliveryAddress"), dict) else {}
    delivery_info = _merge_keep_plain({
        "deliveredBy":       _text(delivery.get("deliveredBy")),
        "street":            _text(address.get("street")),
        "number":            _text(address.get("number")),
        "complement":        _text(address.get("complement")),
        "district":          _text(address.get("district")),
        "city":              _text(address.get("city")),
        "state":             _text(address.get("state")),
        "postalCode":        _text(address.get("postalCode")),
        "reference":         _text(address.get("reference")),
        "formattedAddress":  _text(address.get("formattedAddress")),
        "estimatedDeliveryDateTime": _text(delivery.get("estimatedDeliveryDateTime")),
    }, order.delivery_json)
    # Se a Keeta espera /tracking e /delivered (só faz sentido em entrega própria)
    for key in ("sendTracking", "sendDelivered"):
        if isinstance((flags or {}).get(key), bool):
            delivery_info[key] = flags[key]

    order.customer_json = json.dumps(customer_info, ensure_ascii=False)
    order.delivery_json = json.dumps(delivery_info, ensure_ascii=False)

    name = customer_info.get("name")
    if _is_plain(name):
        order.customer_name = name
    elif not _is_plain(order.customer_name):
        order.customer_name = "Cliente"

    formatted = _format_address(delivery_info)
    if formatted:
        order.delivery_address = formatted
    elif not _is_plain(order.delivery_address):
        # Sem endereço legível (retirada, ou ainda criptografado): nunca gravar ENC_.
        order.delivery_address = None if address else "Retirada / Não informado"

    methods = []
    for method in payments.get("methods") or []:
        if isinstance(method, dict):
            methods.append({k: method.get(k) for k in ("method", "type", "value", "brand", "methodInfo", "changeFor")
                            if method.get(k) is not None})
    order.payments_json = json.dumps({"prepaid": payments.get("prepaid"), "pending": payments.get("pending"),
                                      "methods": methods}, ensure_ascii=False)


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
    order.platform = "KEETA"
    is_new = not order.id
    print(f"[Orders][save_order_from_keeta] Pedido {'NOVO (será criado)' if is_new else f'EXISTENTE (id={order.id}, será atualizado)'}")

    if not order.id:
        order.external_id = keeta_id

    # --- Define a loja local ---
    try:
        order.store_id = int(local_merchant_id)
        print(f"[Orders][save_order_from_keeta] store_id definido: {order.store_id}")
    except Exception as e:
        # Nunca direcionar silenciosamente um pedido de uma loja desconhecida
        # para a loja 1. O webhook deve resolver o vínculo antes de chamar este
        # serviço; se não resolver, o pedido precisa ser rejeitado/logado.
        print(
            f"[Orders][save_order_from_keeta] PEDIDO NÃO SALVO: "
            f"local_merchant_id inválido='{local_merchant_id}': {e}"
        )
        return

    # --- Status inicial ---
    # Se o pedido ainda não tem status, verificamos se o auto-aceite está ativo.
    # ATENÇÃO: se a StoreConfig não existir, NÃO assumimos auto-aceite como True.
    # O default seguro é False (aguardar ação manual do operador).
    if not order.status:
        print(f"[Orders][save_order_from_keeta] Pedido sem status definido. Verificando auto_accept para store_id={order.store_id}...")
        config = StoreConfig.query.get(order.store_id)
        auto_accept = config.auto_accept if config else False
        print(f"[Orders][save_order_from_keeta] Config encontrada: {config.to_dict() if config else 'NENHUMA'} | auto_accept={auto_accept}")

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
            order.status = "PENDING"
            print(f"[Orders][save_order_from_keeta] Auto-aceite INATIVO. Status definido como PENDING (aguardando ação manual).")

    # --- Dados de identificação ---
    delivery = order_json.get("delivery", {})
    pickup_code = delivery.get("pickupCode") or order_json.get("displayId")
    order.pickup_code = pickup_code
    order.display_id  = order_json.get("displayId")
    order.created_at  = order_json.get("createdAt")
    print(f"[Orders][save_order_from_keeta] Identificação: pickup_code={pickup_code} | display_id={order.display_id} | created_at={order.created_at}")

    # --- Cliente, entrega e pagamento (com descriptografia) ---
    # Em entrega própria/3PL a Keeta manda telefone e endereço criptografados
    # (ENC_...). Descriptografamos pelo batchDecrypt e guardamos já em texto.
    # Nunca registrar esses dados nos logs.
    customer = order_json.get("customer") or {}
    delivery = order_json.get("delivery") or {}
    customer, delivery, decrypt_stats = _decrypt_contact_data(customer, delivery)
    _apply_contact_data(order, customer, delivery, order_json.get("payments") or {}, order_json)
    print(f"[Orders][save_order_from_keeta] Cliente/entrega gravados | criptografados={decrypt_stats[0]} | "
          f"descriptografados={decrypt_stats[1]} | entrega_por={delivery.get('deliveredBy')}")

    total_node = order_json.get("total", {})
    order_amount = total_node.get("orderAmount", {})
    if "value" in order_amount:
        order.total_price = order_amount["value"] 
    items_price_node = total_node.get("itemsPrice", {})
    if "value" in items_price_node:
        order.items_price = items_price_node["value"]

    other_fees_node = total_node.get("otherFees", {})
    if "value" in other_fees_node:
        order.other_fees_total = other_fees_node["value"]

    discount_node = total_node.get("discount", {})
    if "value" in discount_node:
        order.discount = discount_node["value"]

    print(f"[Orders][save_order_from_keeta] Financeiro: total={order.total_price} | items={order.items_price} | fees={order.other_fees_total} | discount={order.discount}")

    # --- Tipo de pagamento ---
    payments = order_json.get("payments", {})
    if payments.get("prepaid", 0) > 0:
        order.payment_type = "ONLINE"
    else:
        order.payment_type = "NA_ENTREGA"
    print(f"[Orders][save_order_from_keeta] payment_type={order.payment_type}")

    # --- Coordenadas da entrega (o endereço em texto é tratado em _apply_contact_data) ---
    coords = (delivery.get("deliveryAddress") or {}).get("coordinates") or {}
    if isinstance(coords.get("latitude"), (int, float)) and isinstance(coords.get("longitude"), (int, float)):
        order.latitude  = coords["latitude"]
        order.longitude = coords["longitude"]
    print(f"[Orders][save_order_from_keeta] Endereço gravado | tem_coordenadas={order.latitude is not None}")

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
            # Mesmo complemento escolhido mais de uma vez: "2x Bacon Extra"
            full_name += f" ({', '.join(option_labels(options))})"

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
            options_json=json.dumps(options),  # salva as opções para o frontend
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


# -----------------------------------------------------------------------------
#  Reembolso pedido pelo cliente (Keeta): aceitar ou recusar
# -----------------------------------------------------------------------------

def _refund_order_or_error(order_id):
    order = _account_order(order_id)
    if not order:
        return None, (jsonify({"error": "Pedido não encontrado."}), 404)
    if (order.platform or "KEETA") != "KEETA" or not order.external_id:
        return None, (jsonify({"error": "Só pedidos da Keeta têm reembolso pelo PDV."}), 400)
    refund = refunds.load(order)
    if not refund or refund.get("status") != "REQUESTED":
        return None, (jsonify({"error": "Este pedido não tem reembolso esperando resposta."}), 409)
    return order, None


def _keeta_refund_error(status_code, body):
    if status_code == 422:
        return "A Keeta diz que este reembolso já foi respondido ou não pode mais ser respondido."
    if status_code is None:
        return "A Keeta não respondeu. Tente de novo em instantes."
    return f"A Keeta não aceitou a resposta (código {status_code})."


@orders_bp.post("/<int:order_id>/refund/accept")
@login_required
def accept_refund(order_id):
    order, error = _refund_order_or_error(order_id)
    if error:
        return error
    ok, status_code, body = keeta_client.accept_refund(order.external_id)
    if not ok:
        return jsonify({"error": _keeta_refund_error(status_code, body)}), 502
    refunds.mark_decision(order, "ACCEPT")
    db.session.commit()
    print(f"[Orders][refund] aceito | order_id={order.id} | keeta={order.external_id}")
    return jsonify({"message": "Reembolso aceito. A Keeta confirma em instantes.", "order": order.to_dict()})


@orders_bp.post("/<int:order_id>/refund/reject")
@login_required
def reject_refund(order_id):
    data = request.get_json(silent=True) or {}
    code = data.get("code") or "OTHER"
    reason = str(data.get("reason") or "").strip()
    if code not in refunds.REJECT_CODES:
        return jsonify({"error": "Motivo de recusa inválido."}), 400
    if not reason:
        reason = refunds.REJECT_CODES[code]
    if len(reason) > 300:
        return jsonify({"error": "O motivo pode ter no máximo 300 caracteres."}), 400
    order, error = _refund_order_or_error(order_id)
    if error:
        return error
    ok, status_code, body = keeta_client.reject_refund(order.external_id, reason, code)
    if not ok:
        return jsonify({"error": _keeta_refund_error(status_code, body)}), 502
    refunds.mark_decision(order, "REJECT", code, reason)
    db.session.commit()
    print(f"[Orders][refund] recusado | order_id={order.id} | keeta={order.external_id} | code={code}")
    return jsonify({"message": "Reembolso recusado. A Keeta avisa o cliente.", "order": order.to_dict()})

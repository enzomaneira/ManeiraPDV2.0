# =============================================================================
#  routes/keeta_webhook.py  —  Endpoints de Integração com a Keeta
# =============================================================================
#
#  Este arquivo tem duas responsabilidades:
#
#  1. RECEBER eventos da Keeta (webhook):
#     A Keeta faz POST /api/keeta/orders quando algo acontece com um pedido.
#     Ex: pedido criado, confirmado, cancelado, entregue...
#
#  2. RESPONDER ao GET /menu:
#     A Keeta faz GET /api/keeta/menu para buscar o cardápio da loja.
#
#  3. AUXILIARES:
#     Callbacks OAuth, geração de URL de auth, controle de status da loja.
#
#  Como várias lojas (uma por usuário) compartilham o mesmo app Keeta,
#  usamos o "local ID" (nosso store_id) para saber de qual loja é cada
#  requisição. Esse ID trafega:
#    - No onboarding: como merchantId
#    - No webhook de pedidos: no header X-App-MerchantId
#    - No fluxo OAuth: embutido na própria redirectUri (?storeId=...)
# =============================================================================

from flask import Blueprint, request, jsonify, g
import keeta_client
from models import Order, MenuItem, StoreConfig
from database import db
from routes.orders import save_order_from_keeta
from auth_utils import login_required

keeta_bp = Blueprint("keeta", __name__)


# =============================================================================
#  WEBHOOK PRINCIPAL — A Keeta chama este endpoint para enviar eventos
# =============================================================================

@keeta_bp.post("/orders")
def receive_order_event():
    """
    Recebe eventos de pedido da Keeta via webhook.

    A Keeta faz POST aqui sempre que algo acontece:
      - Pedido criado (CREATED)
      - Pedido confirmado externamente (CONFIRMED)
      - Pedido pronto para retirada (READY_FOR_PICKUP)
      - Pedido despachado (DISPATCHED)
      - Pedido entregue/concluído (DELIVERED, CONCLUDED)
      - Pedido cancelado ou reembolsado (CANCELLED, REFUNDED, ...)

    Segurança:
      - Todo webhook vem com o header X-App-Signature
      - Validamos essa assinatura antes de processar qualquer coisa
    """
    print("\n[Webhook] Evento recebido da Keeta!")

    # --- 1. Lê o body bruto (necessário para validar a assinatura) ---
    body_bytes = request.get_data()
    body_str   = body_bytes.decode("utf-8")

    # --- 2. Valida a assinatura ---
    received_signature = request.headers.get("X-App-Signature", "")
    if not keeta_client.validate_webhook_signature(body_str, received_signature):
        print("[Webhook] ERRO: Assinatura inválida! Requisição rejeitada.")
        return jsonify({"error": "Invalid signature"}), 403

    # --- 3. Extrai os dados do evento ---
    import json
    event = json.loads(body_str)

    event_type  = event.get("eventType")   # Tipo do evento: CREATED, CONFIRMED, etc.
    order_id    = event.get("orderId")      # ID do pedido na Keeta
    merchant_id = request.headers.get("X-App-MerchantId", "1")  # store_id local da loja

    print(f"[Webhook] Evento: {event_type} | Pedido Keeta: {order_id}")

    if not order_id:
        return jsonify({"message": "No orderId, ignoring."}), 200

    # --- 4. Para qualquer evento com orderId, busca os detalhes completos na Keeta ---
    # Isso garante que sempre temos os dados mais atualizados
    order_data = keeta_client.get_order_details(order_id)
    if order_data:
        save_order_from_keeta(order_data, merchant_id)

    # --- 5. Atualiza o status no banco de acordo com o tipo do evento ---
    _handle_event(event_type, order_id)

    # A Keeta espera um HTTP 200 para confirmar que recebemos o evento
    return jsonify({"message": "ok"}), 200


def _handle_event(event_type: str, order_id: str):
    """
    Mapeia os tipos de evento da Keeta para os status internos do PDV.

    Tabela de mapeamento:
      CREATED          → não muda status (já foi salvo em save_order_from_keeta)
      CONFIRMED        → PREPARING   (alguém confirmou pelo portal da Keeta)
      READY_FOR_PICKUP → READY_FOR_PICKUP
      DISPATCHED       → DELIVERY_IN_PROGRESS
      DELIVERED        → COMPLETED
      CONCLUDED        → COMPLETED
      CANCELLED        → CANCELED
      REFUNDED         → CANCELED
    """
    status_map = {
        "CONFIRMED":        "PREPARING",
        "READY_FOR_PICKUP": "READY_FOR_PICKUP",
        "DISPATCHED":       "DELIVERY_IN_PROGRESS",
        "DELIVERED":        "COMPLETED",
        "CONCLUDED":        "COMPLETED",
        "CANCELLED":        "CANCELED",
        "CANCELLATION_REQUESTED": "CANCELED",
        "USER_REFUND_REQUEST": "CANCELED",
        "REFUNDED":         "CANCELED",
        "REFUND_FAILED":    "CANCELED",
    }

    new_status = status_map.get(event_type)

    if new_status:
        order = Order.query.filter_by(external_id=order_id).first()
        if order:
            order.status = new_status
            db.session.commit()
            print(f"[Webhook] Pedido {order_id} → status atualizado para {new_status}")
    else:
        print(f"[Webhook] Evento informativo (sem mudança de status): {event_type}")


# =============================================================================
#  ENDPOINT DO CARDÁPIO — A Keeta chama este endpoint para buscar o menu
# =============================================================================

@keeta_bp.get("/menu")
def get_merchant_menu():
    """
    A Keeta chama este endpoint (GET /merchant) para buscar o cardápio da loja.

    Isso acontece quando:
      - A Keeta quer sincronizar o menu após uma notificação de atualização
      - Durante o processo de onboarding

    A URL deste endpoint é informada no registro do merchant (onboarding),
    incluindo o storeId como query param.

    Documentação: https://api-docs.mykeeta.com/apis/opendelivery/merchantendpoints
    """
    store_id = request.args.get("storeId", 1, type=int)
    items = MenuItem.query.filter_by(store_id=store_id).all()

    # Formata o cardápio no padrão Open Delivery esperado pela Keeta
    menu_items_formatted = []
    for item in items:
        menu_items_formatted.append({
            "id":          str(item.id),
            "name":        item.name,
            "description": "",
            "externalCode": str(item.id),
            "price": {
                "value":        item.price,
                "currency":     "BRL",
                "originalValue": item.price,
            },
            "status": "AVAILABLE",
        })

    return jsonify({
        "id":   str(store_id),
        "menu": [
            {
                "id":          "cat-1",
                "name":        "Cardápio",
                "externalCode": "cat-1",
                "status":      "AVAILABLE",
                "items":       menu_items_formatted,
            }
        ],
        "services": [],
    })


# =============================================================================
#  CONTROLE DE STATUS DA LOJA
# =============================================================================

@keeta_bp.post("/store-status")
@login_required
def update_store_status():
    """
    Abre ou fecha a loja do usuário logado na Keeta.
    Chamado pelo frontend quando o operador clica no botão "LOJA ABERTA/FECHADA".
    """
    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    config = StoreConfig.query.get(store.id)
    if not config or not config.keeta_merchant_id:
        return jsonify({"error": "Loja ainda não está conectada à Keeta."}), 400

    data    = request.get_json(silent=True) or {}
    is_open = data.get("isOpen", True)

    success = keeta_client.update_store_status(config.keeta_merchant_id, is_open)

    if success:
        config.is_store_open = is_open
        db.session.commit()
        status_text = "ABERTA" if is_open else "FECHADA"
        return jsonify({"message": f"Loja agora está {status_text} na Keeta."})
    else:
        return jsonify({"error": "Falha ao atualizar status na Keeta."}), 500


# =============================================================================
#  FLUXO DE AUTORIZAÇÃO OAUTH (Onboarding de comerciantes)
# =============================================================================

@keeta_bp.get("/generate-auth-url")
@login_required
def generate_auth_url():
    """
    Gera a URL que o comerciante abre para autorizar seu sistema na Keeta.

    Fluxo completo:
      1. Frontend chama este endpoint (autenticado) → recebe a URL
      2. O comerciante abre a URL e faz login na Keeta
      3. Após autorizar, a Keeta redireciona para /api/keeta/callback com authId
         (a URL de callback já leva o storeId do usuário logado embutido)
      4. /callback usa o authId para buscar dados e fazer o onboarding
         daquela loja específica
    """
    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    # Embute o storeId na própria URL de callback, para sabermos depois
    # de qual loja/usuário é essa autorização.
    my_callback_url = f"{request.host_url.rstrip('/')}/api/keeta/callback?storeId={store.id}"
    auth_url = keeta_client.get_authorization_url(my_callback_url)

    if auth_url:
        return jsonify(auth_url)  # pode ser string ou dict dependendo da Keeta
    else:
        return jsonify({"error": "Não foi possível gerar a URL"}), 500


@keeta_bp.get("/callback")
def keeta_callback():
    """
    Recebe o retorno após o comerciante autorizar o sistema na Keeta.

    Parâmetros que a Keeta envia na URL:
      - authId:           ID da autorização (sempre presente)
      - keetaMerchantId: ID da loja na Keeta (às vezes não vem)
      - error:           Mensagem de erro (se algo deu errado)
      - storeId:         Nosso ID local da loja (embutido por nós ao gerar a URL)

    O que fazemos aqui:
      1. Se não vier keetaMerchantId, usamos o authId para buscar os dados da loja
      2. Fazemos o onboarding: registramos a loja + URL do webhook na Keeta,
         vinculando ao storeId correto
    """
    auth_id  = request.args.get("authId")
    keeta_id = request.args.get("keetaMerchantId")
    error    = request.args.get("error")
    store_id = request.args.get("storeId", "1")

    print(f"\n[Callback] authId={auth_id} | keetaMerchantId={keeta_id} | storeId={store_id}")

    if error:
        return f"Erro na Keeta: {error}", 400

    if not auth_id:
        return "Erro: authId não recebido no callback.", 400

    # Se o keetaMerchantId não veio na URL, busca via API
    if not keeta_id:
        print("[Callback] keetaMerchantId não recebido. Buscando via merchantInfo...")
        merchant_info = keeta_client.get_merchant_info(auth_id)

        if not merchant_info:
            return "Erro: Não foi possível buscar info da loja.", 500

        authorized_shops = merchant_info.get("authorizedShops", [])
        if not authorized_shops:
            return "Erro: Nenhuma loja autorizada encontrada.", 400

        keeta_id = str(authorized_shops[0]["id"])
        print(f"[Callback] keetaMerchantId descoberto: {keeta_id}")

    # Faz o onboarding — registra o mapeamento e as URLs na Keeta
    result = keeta_client.register_merchant(keeta_id, my_local_store_id=store_id)

    # Salva o keetaMerchantId na configuração da loja correspondente
    config = StoreConfig.query.get(int(store_id))
    if not config:
        config = StoreConfig(store_id=int(store_id))
        db.session.add(config)
    config.keeta_merchant_id = keeta_id
    db.session.commit()

    return f"""
    <h1>✅ Integração Keeta Concluída!</h1>
    <p><b>ID da Loja na Keeta:</b> {keeta_id}</p>
    <p><b>Resposta do Onboarding:</b> {result}</p>
    <p><a href="/">← Voltar ao PDV</a></p>
    """, 200

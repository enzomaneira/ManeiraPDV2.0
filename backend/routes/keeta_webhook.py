# =============================================================================
#  routes/keeta_webhook.py  —  Endpoints de Integração com a Keeta
# =============================================================================
#
#  Este arquivo tem várias responsabilidades:
#
#  1. RECEBER eventos de PEDIDO da Keeta (webhook):
#     A Keeta faz POST /api/keeta/orders quando algo acontece com um pedido.
#     Ex: pedido criado, confirmado, cancelado, entregue...
#
#  2. RECEBER eventos de AUTORIZAÇÃO da Keeta (webhook):
#     A Keeta faz POST /api/keeta/authorization quando um lojista autoriza
#     (evento 1301) ou revoga a autorização (evento 1302) do nosso app.
#     Essa URL precisa ser configurada manualmente no Dev Portal da Keeta.
#
#  3. RESPONDER ao GET /menu:
#     A Keeta faz GET /api/keeta/menu para buscar o cardápio da loja.
#
#  4. AUXILIARES:
#     Onboarding direto, controle de status da loja.
#
#  Como várias lojas (uma por usuário) compartilham o mesmo app Keeta,
#  usamos o "local ID" (nosso store_id) para saber de qual loja é cada
#  requisição. Esse ID trafega:
#    - No onboarding: como merchantId
#    - No webhook de pedidos: no header X-App-MerchantId
#    - No webhook de autorização: via shopId (= keeta_merchant_id salvo na StoreConfig)
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
    print("\n" + "#" * 70)
    print("[Webhook][receive_order_event] INÍCIO | Evento recebido da Keeta!")
    print(f"[Webhook][receive_order_event] Headers recebidos: {dict(request.headers)}")

    # --- 1. Lê o body bruto (necessário para validar a assinatura) ---
    body_bytes = request.get_data()
    body_str   = body_bytes.decode("utf-8")
    print(f"[Webhook][receive_order_event] Body bruto recebido ({len(body_str)} bytes): {body_str[:500]}")

    # --- 2. Valida a assinatura ---
    received_signature = request.headers.get("X-App-Signature", "")
    print(f"[Webhook][receive_order_event] Assinatura recebida: {received_signature[:30]}...")

    assinatura_valida = keeta_client.validate_webhook_signature(body_str, received_signature)
    print(f"[Webhook][receive_order_event] Assinatura válida? {assinatura_valida}")

    if not assinatura_valida:
        print("[Webhook][receive_order_event] REJEITADO (403): Assinatura inválida!")
        print("#" * 70 + "\n")
        return jsonify({"error": "Invalid signature"}), 403

    # --- 3. Extrai os dados do evento ---
    import json
    event = json.loads(body_str)
    print(f"[Webhook][receive_order_event] Evento decodificado (chaves): {list(event.keys())}")

    event_type  = event.get("eventType")   # Tipo do evento: CREATED, CONFIRMED, etc.
    order_id    = event.get("orderId")      # ID do pedido na Keeta
    order_url   = event.get("orderURL")     # URL pronta (enviada pela Keeta) para buscar os detalhes do pedido
    merchant_id = request.headers.get("X-App-MerchantId", "1")  # store_id local da loja

    print(f"[Webhook][receive_order_event] event_type={event_type} | order_id={order_id} | order_url={order_url} | merchant_id(local store_id)={merchant_id}")

    if not order_id:
        print("[Webhook][receive_order_event] FIM (ignorado): sem orderId no evento.")
        print("#" * 70 + "\n")
        return jsonify({"message": "No orderId, ignoring."}), 200

    # --- 4. Para qualquer evento com orderId, busca os detalhes completos na Keeta ---
    # Isso garante que sempre temos os dados mais atualizados.
    # Damos preferência ao campo `orderURL` enviado pela própria Keeta no evento
    # (conforme documentação oficial de Polling/Webhook), em vez de montar a
    # URL manualmente — isso evita chamar o endpoint errado.
    #
    # IMPORTANTE: todo o processamento abaixo está protegido por try/except.
    # A Keeta considera o webhook "Failed" se a conexão cair ou demorar demais
    # (sintoma visto como "Unknown Protocol" nos logs), e nesse caso ela
    # REENVIA o mesmo evento em loop a cada poucos segundos. Por isso é
    # fundamental que, aconteça o que acontecer no processamento, sempre
    # respondamos 200 rapidamente — erros são apenas logados, nunca deixados
    # propagar e derrubar a resposta HTTP.
    try:
        print(f"[Webhook][receive_order_event] Buscando detalhes completos do pedido {order_id} na Keeta (orderURL={order_url})...")
        order_data = keeta_client.get_order_details(order_id, order_url=order_url)

        if order_data:
            print(f"[Webhook][receive_order_event] Detalhes obtidos com sucesso. Salvando no banco (store_id={merchant_id})...")
            save_order_from_keeta(order_data, merchant_id)
        else:
            print(f"[Webhook][receive_order_event] AVISO: não foi possível obter detalhes do pedido {order_id} na Keeta (timeout ou erro na chamada).")

        # --- 5. Atualiza o status no banco de acordo com o tipo do evento ---
        print(f"[Webhook][receive_order_event] Processando mapeamento de status para event_type={event_type}...")
        _handle_event(event_type, order_id)
    except Exception as e:
        # Nunca deixamos uma exceção aqui impedir a resposta 200 à Keeta.
        # Se algo falhar, o pior caso é o pedido ficar desatualizado — o que
        # é bem melhor do que entrar em loop infinito de reenvios.
        print(f"[Webhook][receive_order_event] ERRO durante o processamento do evento (será ignorado para não travar a resposta): {type(e).__name__}: {e}")

    print(f"[Webhook][receive_order_event] FIM (sucesso) | order_id={order_id} | event_type={event_type}")
    print("#" * 70 + "\n")

    # A Keeta espera um HTTP 200 para confirmar que recebemos o evento.
    # Respondemos 200 mesmo que o processamento interno tenha falhado, para
    # evitar que a Keeta entre em loop de reenvio do mesmo evento.
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
    print(f"[Webhook][_handle_event] INÍCIO | event_type={event_type} | order_id={order_id}")

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
    print(f"[Webhook][_handle_event] Status mapeado: '{event_type}' → '{new_status}'")

    if new_status:
        order = Order.query.filter_by(external_id=order_id).first()
        if order:
            status_anterior = order.status
            order.status = new_status
            db.session.commit()
            print(f"[Webhook][_handle_event] Pedido {order_id} atualizado: '{status_anterior}' → '{new_status}' (order_id interno={order.id})")
        else:
            print(f"[Webhook][_handle_event] AVISO: pedido com external_id={order_id} não encontrado no banco.")
    else:
        print(f"[Webhook][_handle_event] Evento informativo (sem mudança de status): {event_type}")

    print(f"[Webhook][_handle_event] FIM | event_type={event_type} | order_id={order_id}")


# =============================================================================
#  WEBHOOK DE AUTORIZAÇÃO — eventos 1301 (nova autorização) e 1302 (cancelamento)
# =============================================================================
#
#  Este é um webhook DIFERENTE do de pedidos (/orders). Ele não trata de
#  CREATED/CONFIRMED/DELIVERED etc; trata exclusivamente de quando um
#  lojista AUTORIZA ou REVOGA a autorização do nosso app na Keeta.
#
#  A URL deste endpoint precisa ser configurada MANUALMENTE no Dev Portal
#  da Keeta (Application Management → Webhook), nos eventos:
#    1301 → nova autorização
#    1302 → cancelamento de autorização
#
#  Documentação: https://api-docs.mykeeta.com/apis/opendelivery/authentication/receiveauthorizationwebhook
#
#  Payload (application/json):
#    {
#      "clientId":   2816859805,          // appId da Keeta
#      "authId":     "41008",             // ID único da sessão de autorização
#      "opType":     1,                   // 1 = nova autorização | 2 = cancelamento
#      "shopId":     159649625,           // ID da loja na Keeta (= keeta_merchant_id)
#      "shopName":   "Loja Exemplo",
#      "createTime": 1753151456973        // timestamp em milissegundos
#    }
# =============================================================================

@keeta_bp.post("/authorization")
def receive_authorization_event():
    """
    Recebe notificações de autorização/desautorização de merchant.

    opType == 1 → merchant autorizou o app (nova autorização)
    opType == 2 → merchant cancelou a autorização

    A Keeta espera resposta em até 5s, com HTTP 200 e um JSON contendo
    os campos `status` e `title` (idêntico ao padrão usado no restante da
    integração, por consistência com os outros endpoints).
    """
    print("\n" + "#" * 70)
    print("[Webhook][receive_authorization_event] INÍCIO | Evento de autorização recebido da Keeta!")
    print(f"[Webhook][receive_authorization_event] Headers recebidos: {dict(request.headers)}")

    # --- 1. Lê o body bruto e valida a assinatura (mesmo esquema HMAC-SHA256) ---
    body_bytes = request.get_data()
    body_str   = body_bytes.decode("utf-8")
    print(f"[Webhook][receive_authorization_event] Body bruto recebido ({len(body_str)} bytes): {body_str[:500]}")

    received_signature = request.headers.get("X-App-Signature", "")
    assinatura_valida = keeta_client.validate_webhook_signature(body_str, received_signature)
    print(f"[Webhook][receive_authorization_event] Assinatura válida? {assinatura_valida}")

    if not assinatura_valida:
        print("[Webhook][receive_authorization_event] REJEITADO (403): Assinatura inválida!")
        print("#" * 70 + "\n")
        return jsonify({"status": 401, "title": "Invalid signature"}), 403

    # --- 2. Faz o parse do payload, protegido contra erros ---
    try:
        import json
        event = json.loads(body_str)
        print(f"[Webhook][receive_authorization_event] Evento decodificado: {event}")

        auth_id   = event.get("authId")
        op_type   = event.get("opType")     # 1 = nova autorização | 2 = cancelamento
        shop_id   = event.get("shopId")     # ID da loja na Keeta (keeta_merchant_id)
        shop_name = event.get("shopName")

        print(f"[Webhook][receive_authorization_event] authId={auth_id} | opType={op_type} | shopId={shop_id} | shopName={shop_name}")

        if shop_id is None:
            print("[Webhook][receive_authorization_event] AVISO: evento sem shopId, nada a fazer.")
        else:
            # Localiza a StoreConfig cujo keeta_merchant_id bate com o shopId recebido
            config = StoreConfig.query.filter_by(keeta_merchant_id=str(shop_id)).first()

            if not config:
                print(f"[Webhook][receive_authorization_event] AVISO: nenhuma StoreConfig encontrada para shopId={shop_id}. "
                      f"Isso é esperado se a loja ainda não tiver feito o onboarding local.")
            else:
                if op_type == 1:
                    config.keeta_authorized = True
                    config.keeta_auth_id = str(auth_id) if auth_id is not None else config.keeta_auth_id
                    print(f"[Webhook][receive_authorization_event] Loja store_id={config.store_id} AUTORIZADA (opType=1) | authId={auth_id}")
                elif op_type == 2:
                    config.keeta_authorized = False
                    print(f"[Webhook][receive_authorization_event] Loja store_id={config.store_id} teve a autorização CANCELADA (opType=2)")
                else:
                    print(f"[Webhook][receive_authorization_event] AVISO: opType desconhecido ({op_type}), nenhuma alteração feita.")

                db.session.commit()
                print(f"[Webhook][receive_authorization_event] Config atualizada: {config.to_dict()}")
    except Exception as e:
        # Assim como no webhook de pedidos: nunca deixamos uma exceção impedir
        # a resposta 200, para evitar reenvios em loop pela Keeta.
        print(f"[Webhook][receive_authorization_event] ERRO durante o processamento (ignorado para não travar a resposta): {type(e).__name__}: {e}")

    print("[Webhook][receive_authorization_event] FIM (sucesso)")
    print("#" * 70 + "\n")

    # Formato de resposta sugerido pela documentação: {status, title}, status=0 é sucesso.
    return jsonify({"status": 0, "title": "success"}), 200


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
    print(f"\n[Webhook][get_merchant_menu] INÍCIO | storeId (query param)={store_id}")

    items = MenuItem.query.filter_by(store_id=store_id).all()
    print(f"[Webhook][get_merchant_menu] {len(items)} item(ns) de menu encontrado(s) para store_id={store_id}")

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

    response = {
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
    }
    print(f"[Webhook][get_merchant_menu] FIM (sucesso) | store_id={store_id} | total_itens={len(menu_items_formatted)}")
    return jsonify(response)


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
    print(f"\n[Webhook][update_store_status] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    if not store:
        print(f"[Webhook][update_store_status] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    print(f"[Webhook][update_store_status] Buscando StoreConfig para store_id={store.id}...")
    config = StoreConfig.query.get(store.id)

    if not config or not config.keeta_merchant_id:
        print(f"[Webhook][update_store_status] FALHA (400): loja não conectada à Keeta | config={config.to_dict() if config else None}")
        return jsonify({"error": "Loja ainda não está conectada à Keeta."}), 400

    data    = request.get_json(silent=True) or {}
    is_open = data.get("isOpen", True)
    print(f"[Webhook][update_store_status] Body recebido: {data} | is_open={is_open} | keeta_merchant_id={config.keeta_merchant_id}")

    print(f"[Webhook][update_store_status] Chamando keeta_client.update_store_status({config.keeta_merchant_id}, {is_open})...")
    success, error_detail = keeta_client.update_store_status(config.keeta_merchant_id, is_open)
    print(f"[Webhook][update_store_status] Resultado da chamada à Keeta: success={success} | error={error_detail}")

    if success:
        config.is_store_open = is_open
        db.session.commit()
        status_text = "ABERTA" if is_open else "FECHADA"
        print(f"[Webhook][update_store_status] FIM (sucesso) | store_id={store.id} | status={status_text}")
        return jsonify({"message": f"Loja agora está {status_text} na Keeta."})
    else:
        print(f"[Webhook][update_store_status] FIM (falha - 500) | store_id={store.id} | erro={error_detail}")
        return jsonify({"error": f"Falha ao atualizar status na Keeta: {error_detail}"}), 500


# =============================================================================
#  ONBOARDING DIRETO (sem fluxo OAuth de authURL)
# =============================================================================

@keeta_bp.put("/onboard")
@login_required
def onboard_merchant():
    """
    Ativa/conecta a integração da loja do usuário logado diretamente na Keeta,
    chamando o endpoint de onboarding (PUT /v1/merchantOnboarding).

    Não depende mais do fluxo OAuth (authURL/callback). O usuário simplesmente
    digita o ID da loja na Keeta no campo de configuração e clica em
    "Ativar Integração / Autenticar", que dispara esta rota.

    Body esperado:
      {
        "keetaStoreId": "285076...",   // ID da loja dentro da Keeta
        "storeId": "285076..."         // mesmo valor, usado como identificador local
      }
    """
    print(f"\n[Webhook][onboard_merchant] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    if not store:
        print(f"[Webhook][onboard_merchant] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Webhook][onboard_merchant] Body recebido: {data}")

    keeta_store_id = (data.get("keetaStoreId") or "").strip()

    print(f"[Webhook][onboard_merchant] Parâmetros normalizados: keetaStoreId='{keeta_store_id}'")

    if not keeta_store_id:
        print(f"[Webhook][onboard_merchant] FALHA (400): keetaStoreId não informado.")
        return jsonify({"error": "Informe o ID da loja na Keeta antes de ativar a integração."}), 400

    # O merchantId (query param) é o NOSSO ID LOCAL da loja (store.id),
    # enquanto o keetaMerchantId (body) é o ID da loja dentro da Keeta.
    # A documentação oficial é clara: são identificadores diferentes.
    # Enviar o mesmo valor nos dois pode fazer o mapeamento falhar.
    our_local_store_id = str(store.id)
    print(f"[Webhook][onboard_merchant] Nosso store.id local: {our_local_store_id} | keetaStoreId: {keeta_store_id}")

    # Faz o onboarding — registra o mapeamento e as URLs (webhook/menu) na Keeta
    print(f"[Webhook][onboard_merchant] Chamando keeta_client.register_merchant(keeta_store_id={keeta_store_id}, my_local_store_id={our_local_store_id})...")
    result = keeta_client.register_merchant(keeta_store_id, my_local_store_id=our_local_store_id)
    print(f"[Webhook][onboard_merchant] Resultado do onboarding: {result}")

    # Salva o keetaMerchantId na configuração da loja do usuário logado
    print(f"[Webhook][onboard_merchant] Salvando keeta_merchant_id na StoreConfig | store_id={store.id}")
    config = StoreConfig.query.get(store.id)
    if not config:
        print(f"[Webhook][onboard_merchant] Nenhuma config existente para store_id={store.id}. Criando nova...")
        config = StoreConfig(store_id=store.id)
        db.session.add(config)

    config.keeta_merchant_id = keeta_store_id
    db.session.commit()
    print(f"[Webhook][onboard_merchant] Config salva: {config.to_dict()}")

    print(f"[Webhook][onboard_merchant] FIM (sucesso) | store_id={store.id} | keeta_store_id={keeta_store_id}")
    return jsonify({
        "message": "Integração com a Keeta ativada com sucesso!",
        "keetaMerchantId": keeta_store_id,
        "onboardingResult": result,
        "config": config.to_dict(),
    }), 200

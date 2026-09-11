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
from flask_cors import cross_origin
import copy
import json
import os
from pathlib import Path
import uuid
import keeta_client
from models import Order, MenuItem, MenuCategory, MenuOptionGroup, MenuAvailability, Store, StoreConfig
from models import menu_item_option_groups, menu_item_availabilities, menu_category_availabilities
from database import db
from routes.orders import save_order_from_keeta
from auth_utils import login_required

keeta_bp = Blueprint("keeta", __name__)


MANEIRA_KEETA_MERCHANT_ID = "159633716"
_REFERENCE_MENU_KEYS = ("TTL", "basicInfo", "services", "menus", "categories", "itemOffers", "items", "optionGroups")
_REFERENCE_MENU_FILE = Path(
    os.getenv(
        "KEETA_MENU_REFERENCE_FILE",
        str(Path(__file__).resolve().parents[2] / "maneiraburguer_merchant_endpoint.json"),
    )
)


def _reference_uuid(value: str) -> str:
    """Gera IDs UUID estáveis para o fallback quando o JSON de referência não está montado."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"maneira-burguer:{value}"))


def _fallback_maneira_menu() -> dict:
    """Cardápio mínimo completo do Maneira Burguer usado sem o arquivo de referência."""
    menu_id = _reference_uuid("menu")
    service_id = _reference_uuid("service-delivery")
    category_names = ("Porções", "Hamburguers", "Bebidas")
    category_ids = {name: _reference_uuid(f"category:{name}") for name in category_names}
    group_names = ("Molhos", "Cheddar e Bacon", "Complemento", "Bebida", "Sucos", "Refrigerantes")
    group_ids = {name: _reference_uuid(f"option-group:{name}") for name in group_names}
    item_data = (
        ("Onion Rings", "118743587", 21.50, "Porções", ("Molhos",)),
        ("Batatas Maneiras", "118743586", 25.00, "Porções", ("Molhos", "Cheddar e Bacon")),
        ("Burguer Bacon Maneiro", "118825405", 35.00, "Hamburguers", ("Molhos", "Complemento", "Bebida")),
        ("Mushroom & Truffle Burguer", "118702187", 40.00, "Hamburguers", ("Bebida", "Complemento", "Molhos")),
        ("Spicy Jalapeño Maneirito", "118866665", 40.00, "Hamburguers", ("Bebida", "Complemento", "Molhos")),
        ("BBQ Bacon Stack", "119000512", 37.00, "Hamburguers", ("Bebida", "Complemento", "Molhos")),
        ("Clássico Maneiro Cheeseburger", "118793629", 32.00, "Hamburguers", ("Complemento", "Molhos", "Bebida")),
        ("Sucos naturais", "118712564", 14.00, "Bebidas", ("Sucos",)),
        ("Refrigerantes", "118968811", 8.00, "Bebidas", ("Refrigerantes",)),
    )
    items = []
    offers = []
    category_offers = {category_id: [] for category_id in category_ids.values()}
    for index, (name, external_code, price, category, groups) in enumerate(item_data):
        item_id = _reference_uuid(f"item:{external_code}")
        offer_id = _reference_uuid(f"item-offer:{external_code}")
        items.append({
            "id": item_id,
            "name": name,
            "description": name,
            "externalCode": external_code,
            "status": "AVAILABLE",
            "serving": 0,
            "unit": "UN",
            "nutritionalInfo": {"isAlcoholic": False},
        })
        offers.append({
            "id": offer_id,
            "itemId": item_id,
            "index": index,
            "status": "AVAILABLE",
            "price": {"value": price, "originalValue": price, "currency": "BRL"},
            "optionGroupsId": [group_ids[group] for group in groups],
        })
        category_offers[category_ids[category]].append(offer_id)

    categories = [
        {
            "id": category_ids[name],
            "index": index,
            "name": name,
            "status": "AVAILABLE",
            "itemOfferId": category_offers[category_ids[name]],
        }
        for index, name in enumerate(category_names)
    ]
    option_groups = [
        {
            "id": group_ids[name],
            "index": index,
            "name": name,
            "description": name,
            "externalCode": f"OG-{index + 1}",
            "status": "AVAILABLE",
            "minPermitted": 0,
            "maxPermitted": 1,
            "priceMethod": "SUM",
        }
        for index, name in enumerate(group_names)
    ]
    return {
        "TTL": 0,
        "basicInfo": {
            "name": "MANEIRA BURGUER",
            "document": "12345678000199",
            "merchantType": "RESTAURANT",
            "address": {
                "latitude": -23.5505,
                "longitude": -46.6333,
                "lat": -23.5505,
                "lng": -46.6333,
            },
            "contactEmails": ["contato@maneiraburguer.com.br"],
            "contactPhones": {"commercialNumber": "5511999999999"},
            "minOrderValue": {"value": 0.0, "currency": "BRL"},
            "averagePreparationTime": 30,
            "merchantCategories": ["RESTAURANT"],
        },
        "services": [{
            "id": service_id,
            "status": "AVAILABLE",
            "serviceType": "DELIVERY",
            "menuId": menu_id,
            "serviceHours": {
                "id": "103912b3-0daf-536f-8aa8-96d7f58d8723",
                "weekHours": [{
                    "dayOfWeek": [
                        "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                        "FRIDAY", "SATURDAY", "SUNDAY",
                    ],
                    "timePeriods": {
                        "startTime": "11:00:00.000Z",
                        "endTime": "23:00:00.000Z",
                    },
                }],
            },
        }],
        "menus": [{
            "id": menu_id,
            "name": "MANEIRA BURGUER",
            "description": "MANEIRA BURGUER",
            "externalCode": MANEIRA_KEETA_MERCHANT_ID,
            "categoryId": [category_ids[name] for name in category_names],
        }],
        "categories": categories,
        "itemOffers": offers,
        "items": items,
        "optionGroups": option_groups,
    }


def _load_maneira_menu_reference() -> dict:
    """Lê o JSON gerado do cardápio e mantém o fallback executável em ambientes sem o arquivo."""
    if _REFERENCE_MENU_FILE.is_file():
        try:
            with _REFERENCE_MENU_FILE.open("r", encoding="utf-8") as reference_file:
                menu = json.load(reference_file)
            if isinstance(menu, dict) and all(key in menu for key in _REFERENCE_MENU_KEYS):
                # O contrato do GET é deliberadamente restrito a este envelope;
                # não propague metadados extras que possam existir no arquivo.
                return {key: menu[key] for key in _REFERENCE_MENU_KEYS}
            print(f"[Menu] AVISO: {_REFERENCE_MENU_FILE} não possui o envelope esperado; usando fallback.")
        except (OSError, json.JSONDecodeError) as error:
            print(f"[Menu] AVISO: falha ao ler {_REFERENCE_MENU_FILE}: {type(error).__name__}: {error}")
    else:
        print(f"[Menu] AVISO: arquivo de referência não encontrado em {_REFERENCE_MENU_FILE}; usando fallback.")
    return _fallback_maneira_menu()


# =============================================================================
#  FUNÇÃO AUXILIAR — Monta o JSON completo do cardápio no formato Open Delivery
# =============================================================================

def _build_menu_response(store_id: int):
    """
    Constrói o JSON do cardápio completo (Open Delivery format) a partir do
    banco de dados. Inclui: basicInfo, services, menus, categories, items,
    itemOffers, optionGroups e availabilities.
    """
    print(f"\n[_build_menu_response] INÍCIO | store_id={store_id}")

    # O Maneira Burguer possui um cardápio versionado pelo arquivo gerado para
    # a integração. Retornamos uma cópia para nunca permitir que uma chamada
    # modifique o objeto mantido em memória pelo processo.
    if str(store_id) == "1" or str(store_id) == MANEIRA_KEETA_MERCHANT_ID:
        menu = _load_maneira_menu_reference()
        print(f"[_build_menu_response] FIM (referência Maneira Burguer) | keys={list(menu)}")
        return copy.deepcopy(menu)

    # --- Busca a loja no banco para preencher o basicInfo ---
    store = Store.query.get(store_id)
    store_name = store.name if store else "Minha Loja"
    print(f"[_build_menu_response] Loja: nome='{store_name}'")

    # --- Busca os itens do cardápio no banco ---
    items = MenuItem.query.filter_by(store_id=store_id).all()
    categories_db = MenuCategory.query.filter_by(store_id=store_id).order_by(MenuCategory.index).all()
    print(f"[_build_menu_response] {len(items)} item(ns), {len(categories_db)} categoria(s)")

    menu_id    = f"menu-{store_id}"
    service_id = f"svc-delivery-{store_id}"
    hours_id   = f"hours-{store_id}"

    # --- 1. ITEMS + ITEM OFFERS ---
    items_list = []
    item_offers = []
    cat_offer_map = {}
    uncategorized_id = f"cat-uncat-{store_id}"

    for idx, item in enumerate(items):
        item_id_str = str(item.id)
        offer_id = f"offer-{item.id}"

        items_list.append({
            "id":           item_id_str,
            "name":         item.name,
            "description":  item.description or item.name,
            "externalCode": item.external_code or item_id_str,
            "status":       item.status or "AVAILABLE",
            "images":       [{"type": None, "URL": item.image_url, "CRC-32": None}] if item.image_url else [],
            "serving":      0,
            "unit":         "UN",
        })

        item_offers.append({
            "id":     offer_id,
            "itemId": item_id_str,
            "index":  item.index if item.index is not None else idx,
            # `status` é required pelo schema — nunca pode ir None. O modelo
            # já tem default="AVAILABLE", mas aplicamos o mesmo fallback aqui
            # por segurança (defesa em profundidade).
            "status": item.status or "AVAILABLE",
            "price": {
                "originalValue": item.price,
                "currency":      "BRL",
                "value":         item.price,
            },
        })

        cat_key = item.category_id if item.category_id else uncategorized_id
        if cat_key not in cat_offer_map:
            cat_offer_map[cat_key] = []
        cat_offer_map[cat_key].append(offer_id)

    # --- 2. CATEGORIES ---
    categories = []
    category_menu_ids = []

    for cat in categories_db:
        cat_id = str(cat.id)
        category_menu_ids.append(cat_id)
        categories.append({
            "id":             cat_id,
            "index":          cat.index if cat.index is not None else 0,
            "name":           cat.name,
            "description":    cat.description or None,
            "externalCode":   cat.external_code or cat_id,
            "status":         cat.status or "AVAILABLE",
            "itemOfferId":    cat_offer_map.get(cat.id, []),
        })

    if uncategorized_id in cat_offer_map and cat_offer_map[uncategorized_id]:
        category_menu_ids.append(uncategorized_id)
        categories.append({
            "id":             uncategorized_id,
            "index":          len(categories_db),
            "name":           "Sem Categoria",
            "description":    None,
            "externalCode":   f"uncat-{store_id}",
            "status":         "AVAILABLE",
            "itemOfferId":    cat_offer_map[uncategorized_id],
        })

    # --- 3. MENUS ---
    # IMPORTANTE: só criamos o Menu que está de fato referenciado por um
    # Service (via menuId). Um Menu "órfão" (sem nenhum Service apontando
    # para ele via menuId) nunca é alcançado pela Keeta, que navega
    # Service → menuId → Menu → categoryId → Category → itemOfferId.
    # Chegamos a criar um segundo menu "Retirar no local" sem um Service
    # correspondente — isso não quebra o schema, mas é inútil e confuso.
    menus = [
        {
            "id":           menu_id,
            "name":         "Delivery",
            "description":  None,
            "externalCode": f"menu-delivery-{store_id}",
            "categoryId":   category_menu_ids,
        },
    ]

    # --- 4. SERVICES ---
    services = [{
        "id":          service_id,
        "status":      "AVAILABLE",
        "serviceType": "DELIVERY",
        "menuId":      menu_id,
        "serviceHours": {
            "id": hours_id,
            "weekHours": [
                {
                    "dayOfWeek": [
                        "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                        "FRIDAY", "SATURDAY", "SUNDAY",
                    ],
                    "timePeriods": {
                        "startTime": "11:00:00.000Z",
                        "endTime":   "23:00:00.000Z",
                    },
                },
            ],
        },
    }]

    # --- 5. OPTION GROUPS ---
    option_groups_db = MenuOptionGroup.query.filter_by(store_id=store_id).order_by(MenuOptionGroup.index).all()
    option_groups = []
    option_group_ids_map = {}

    for og in option_groups_db:
        og_id = str(og.id)
        option_group_ids_map[og.id] = og_id
        options_list = []
        available_options_count = 0
        for opt_idx, opt in enumerate(og.options):
            opt_status = opt.status or "AVAILABLE"
            if opt_status == "AVAILABLE":
                available_options_count += 1
            options_list.append({
                "id":           str(opt.id),
                "itemId":       f"sub-item-{opt.id}",
                "index":        opt_idx,
                "status":       opt_status,
                "price":        {"originalValue": opt.price or 0.0, "currency": "BRL", "value": opt.price or 0.0},
                "maxPermitted": opt.max_permitted,
            })

        min_permitted = og.min_permitted if og.min_permitted is not None else 0
        max_permitted = og.max_permitted if og.max_permitted is not None else 1

        # PROTEÇÃO CRÍTICA: se `minPermitted` for maior que o número de opções
        # com status AVAILABLE, a Keeta esconde TODOS os itens vinculados a
        # este optionGroup no app (é impossível para o cliente atingir o
        # mínimo exigido). Isso normalmente acontece quando o lojista exclui/
        # desativa opções e esquece de ajustar o mínimo do grupo.
        #
        # Em vez de deixar o item sumir silenciosamente, rebaixamos o
        # minPermitted enviado à Keeta para o mínimo seguro (nunca mais que
        # as opções disponíveis) e avisamos no log para o lojista corrigir
        # a configuração na origem.
        if min_permitted > available_options_count:
            print(f"[_build_menu_response] AVISO: optionGroup '{og.name}' (id={og_id}) tem "
                  f"minPermitted={min_permitted} mas só {available_options_count} opção(ões) "
                  f"disponível(eis) de {len(options_list)} total. Isso esconderia todos os itens "
                  f"vinculados na Keeta! Ajustando minPermitted={available_options_count} apenas "
                  f"para esta resposta — corrija o grupo no cardápio para resolver definitivamente.")
            min_permitted = available_options_count

        option_group_payload = {
            "id":           og_id,
            "index":        og.index if og.index is not None else 0,
            "name":         og.name,
            "description":  og.description or None,
            "externalCode": og.external_code or og_id,
            "status":       og.status or "AVAILABLE",
            "minPermitted": min_permitted,
            "maxPermitted": max_permitted,
        }
        if options_list:
            option_group_payload["options"] = options_list
        option_groups.append(option_group_payload)

    # --- 6. AVAILABILITIES ---
    availabilities_db = MenuAvailability.query.filter_by(store_id=store_id).all()
    availabilities = []
    availability_ids_map = {}

    for av in availabilities_db:
        av_id = str(av.id)
        availability_ids_map[av.id] = av_id
        hours_list = []
        for h in av.hours:
            hours_list.append({
                "dayOfWeek":  [h.day_of_week],
                "timePeriods": {
                    "startTime": h.start_time,
                    "endTime":   h.end_time,
                },
            })
        availabilities.append({
            "id":        av_id,
            "startDate": av.start_date,
            "endDate":   av.end_date,
            "hours":     hours_list,
        })

    # --- 7. Preenche relacionamentos nos itemOffers ---
    for offer in item_offers:
        offer["optionGroupsId"] = []
        offer["availabilityId"] = []

    for item in items:
        # item.id já é int (SQLAlchemy Integer column)
        item_db_id = item.id
        og_ids = db.session.query(menu_item_option_groups.c.option_group_id).filter(
            menu_item_option_groups.c.menu_item_id == item_db_id
        ).all()
        offer_id = f"offer-{item_db_id}"
        for of in item_offers:
            if of["id"] == offer_id:
                of["optionGroupsId"] = [option_group_ids_map[og_id] for (og_id,) in og_ids if og_id in option_group_ids_map]
                break

        av_ids = db.session.query(menu_item_availabilities.c.availability_id).filter(
            menu_item_availabilities.c.menu_item_id == item_db_id
        ).all()
        for of in item_offers:
            if of["id"] == offer_id:
                of["availabilityId"] = [availability_ids_map[av_id] for (av_id,) in av_ids if av_id in availability_ids_map]
                break

    for cat in categories_db:
        cat_av_ids = [availability_ids_map[av_id] for (av_id,) in
                      db.session.query(menu_category_availabilities.c.availability_id).filter(
                          menu_category_availabilities.c.category_id == cat.id
                      ).all() if av_id in availability_ids_map]
        for c in categories:
            if c["id"] == str(cat.id):
                c["availabilityId"] = cat_av_ids
                break

    response = {
        # O schema oficial exige um `id` de 36 a 100 caracteres (ver
        # keeta_client.merchant_uuid). Usar apenas str(store_id) (ex: "1")
        # viola o minLength do schema.
        "id":     keeta_client.merchant_uuid(store_id),
        "status": "AVAILABLE",
            "basicInfo": {
                "name":                    store_name,
                "document":                "12345678000199",
                "corporateName":           f"{store_name} Ltda",
                "description":             "Os melhores produtos da região!",
                "merchantType":             "RESTAURANT",
                "address": {
                    "latitude":              -23.5505,
                    "longitude":             -46.6333,
                    "lat":                   -23.5505,
                    "lng":                   -46.6333,
                },
                "contactEmails":           ["contato@maneiraburguer.com.br"],
                "contactPhones": {
                    "commercialNumber":      "5511999999999",
                },
                "minOrderValue":            {"value": 0.0, "currency": "BRL"},
                "averagePreparationTime":  30,
                "merchantCategories":      ["RESTAURANT"],
            },

        "services":       services,
        "menus":          menus,
        "categories":     categories,
        "itemOffers":     item_offers,
        "items":          items_list,
        "optionGroups":   option_groups,
        "availabilities": availabilities,
    }

    print(f"[_build_menu_response] FIM | items={len(items_list)} offers={len(item_offers)} "
          f"categories={len(categories)} optionGroups={len(option_groups)} availabilities={len(availabilities)}")
    return response


# =============================================================================
#  ROOT — Atalho de conveniência para inspecionar o cardápio manualmente
# =============================================================================

@keeta_bp.get("/")
def keeta_root():
    """
    Retorna o cardápio completo no formato Open Delivery.

    ATENÇÃO: esta rota é só um atalho para inspeção manual (ex: abrir no
    navegador para debugar o JSON). A Keeta NUNCA chama esta rota — o
    endpoint oficial registrado no onboarding (getMerchantURL.baseURL) é
    GET /api/keeta/menu, que exige o header X-API-KEY (ver get_merchant_menu
    abaixo). Por isso esta rota não tem — e não precisa ter — validação de
    X-API-KEY.

    Usa store_id=1 como padrão.
    """
    store_id = request.args.get("storeId", 1, type=int)
    print(f"[keeta_root] GET /api/keeta | storeId={store_id}")
    return jsonify(_build_menu_response(store_id))


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

    # Header X-App-MerchantId pode trazer o store_id LOCAL (nosso), mas a Keeta
    # nem sempre envia esse header. Em vez de cair num fallback cego "1" (que
    # faria TODO pedido cair na mesma loja), deixamos como None aqui e
    # resolvemos o store_id local correto abaixo, a partir do keeta_merchant_id
    # que vem dentro do JSON do pedido.
    merchant_id_header = request.headers.get("X-App-MerchantId")
    print(f"[Webhook][receive_order_event] event_type={event_type} | order_id={order_id} | order_url={order_url} | merchant_id_header={merchant_id_header!r}")

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
            # --- Resolve o store_id LOCAL correto para este pedido ---
            # O pedido pertence a uma loja da Keeta cujo ID (keeta_merchant_id)
            # vem dentro do JSON do pedido. Precisamos achar a StoreConfig local
            # cujo keeta_merchant_id bata, para descobrir o nosso store_id.
            # Prioridade:
            #   1) Header X-App-MerchantId (se a Keeta enviar)
            #   2) Busca inversa por keeta_merchant_id no JSON do pedido
            #   3) Fallback "1" só em último caso (evita crash, mas loga aviso)
            local_store_id = merchant_id_header

            if not local_store_id:
                # Keeta pode enviar o id da loja em diferentes campos, dependendo
                # da versão/schema. Tentamos os mais comuns.
                keeta_store_id_from_order = (
                    order_data.get("merchantId")
                    or order_data.get("storeId")
                    or (order_data.get("store") or {}).get("id")
                    if isinstance(order_data.get("store"), dict)
                    else order_data.get("store")
                )

                print(f"[Webhook][receive_order_event] Header sem merchant_id. Procurando keeta_merchant_id no pedido: {keeta_store_id_from_order!r}")

                if keeta_store_id_from_order is not None:
                    config = StoreConfig.query.filter_by(keeta_merchant_id=str(keeta_store_id_from_order)).first()
                    if config:
                        local_store_id = str(config.store_id)
                        print(f"[Webhook][receive_order_event] StoreConfig encontrada: keeta_merchant_id={keeta_store_id_from_order} -> store_id local={local_store_id}")
                    else:
                        print(f"[Webhook][receive_order_event] AVISO: nenhuma StoreConfig com keeta_merchant_id={keeta_store_id_from_order}. Usando fallback '1'.")

            if not local_store_id:
                print(f"[Webhook][receive_order_event] AVISO: não foi possível resolver o store_id local do pedido {order_id}. Usando fallback '1' — todo pedido cairá na mesma loja se isso persistir.")
                local_store_id = "1"

            print(f"[Webhook][receive_order_event] Detalhes obtidos com sucesso. Salvando no banco (store_id local={local_store_id})...")
            save_order_from_keeta(order_data, local_store_id)
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
#  SINCRONIZAÇÃO DO CARDÁPIO — força a Keeta a puxar o menu atualizado
# =============================================================================

@keeta_bp.post("/sync-menu")
@cross_origin()
@login_required
def force_sync_menu():
    """
    Força a Keeta a re-sincronizar o cardápio completo da loja do usuário logado.

    Faz POST /v1/merchantUpdate/{merchantId} com body vazio. A Keeta então
    chama nosso GET /merchant para buscar o cardápio completo.
    """
    print(f"\n[Webhook][force_sync_menu] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    if not store:
        print(f"[Webhook][force_sync_menu] FALHA (404): usuário sem restaurante vinculado")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    # O refresh completo usa o modo documentado com body `{}`. A Keeta fará
    # novamente o GET /v1/merchant, que é a fonte completa do cardápio.
    config = StoreConfig.query.get(store.id)
    if not config or not config.keeta_merchant_id:
        print(f"[Webhook][force_sync_menu] FALHA (400): loja sem merchant_id registrado | store_id={store.id}")
        return jsonify({"error": "Loja ainda não está conectada à Keeta."}), 400

    # O path usa o merchant_id interno persistido no onboarding desta loja.
    merchant_id = str(config.keeta_merchant_id).strip()
    print(f"[Webhook][force_sync_menu] Solicitando refresh completo | store_id={store.id} | merchant_id={merchant_id}...")
    success, error_detail = keeta_client.force_menu_sync(merchant_id)
    print(f"[Webhook][force_sync_menu] Resultado: success={success} | error={error_detail}")

    if success:
        print(f"[Webhook][force_sync_menu] FIM (sucesso) | store_id={store.id}")
        return jsonify({"message": "Cardápio enviado para a Keeta! A sincronização pode levar alguns minutos."})
    else:
        print(f"[Webhook][force_sync_menu] FIM (falha) | store_id={store.id}")
        return jsonify({"error": f"Falha ao sincronizar com a Keeta: {error_detail}"}), 500


# =============================================================================
#  ENDPOINT DO CARDÁPIO — A Keeta chama este endpoint para buscar o menu
# =============================================================================
#
#  Formato Open Delivery (GET /v1/merchant) exigido pela Keeta:
#    - https://api-docs.mykeeta.com/apis/opendelivery/merchantendpoints/getmerchant
#
#  Estrutura esperada pela Keeta:
#    {
#      id, status, basicInfo (com contactPhones e contactEmails),
#      services (com serviceHours em UTC-0),
#      menus, categories, itemOffers, items,
#      optionGroups (opcional), availabilities (opcional)
#    }
#
#  IMPORTANTE: externalCode em cada entidade é o ID do produto no SISTEMA LOCAL
#  (nosso banco). A Keeta usa esse código para referenciar itens nos pedidos.
#
#  Horário mock: Seg-Dom 08:00-20:00 (BRT = UTC-3) → 11:00-23:00 UTC
# =============================================================================

@keeta_bp.get("/menu")
def get_merchant_menu():
    """
    A Keeta chama este endpoint (GET /merchant) para buscar o cardápio da loja.
    Para o Maneira Burguer, o retorno é carregado de
    `maneiraburguer_merchant_endpoint.json` (ou do fallback versionado quando o
    arquivo não estiver presente no ambiente).

    Isso acontece quando:
      - A Keeta quer sincronizar o menu após uma notificação de atualização
      - Durante o processo de onboarding

    A URL deste endpoint é informada no registro do merchant (onboarding),
    incluindo o storeId como query param.

    A Keeta acessa esta URL diretamente para obter o objeto Merchant completo.
    O retorno deste GET é o objeto Merchant puro; o envelope
    `entityType`/`updatedObjects` pertence ao payload de notificações push e
    não deve ser usado na resposta desta rota.

    Documentação: https://api-docs.mykeeta.com/apis/opendelivery/merchantendpoints
    """
    store_id = request.args.get("storeId", 1, type=int)
    print(f"\n[Webhook][get_merchant_menu] INÍCIO | storeId={store_id} | endpoint_publico=True")

    # Para GET /merchant, a Keeta espera o Merchant diretamente. Não envolver
    # este retorno em entityType/updatedObjects, pois esses campos são usados
    # somente em uma notificação de atualização enviada via POST.
    merchant = _build_menu_response(store_id)

    print(
        f"[Webhook][get_merchant_menu] FIM (sucesso) | store_id={store_id} | "
        f"merchant_id={merchant.get('id')}"
    )
    return jsonify(merchant), 200, {"Content-Type": "application/json"}


# =============================================================================
#  CONTROLE DE STATUS DA LOJA
# =============================================================================

@keeta_bp.post("/store-status")
@cross_origin()
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
        print(f"[Webhook][update_store_status] FALHA (400): loja sem merchant_id registrado | config={config.to_dict() if config else None}")
        return jsonify({"error": "Loja ainda não está conectada à Keeta."}), 400

    data    = request.get_json(silent=True) or {}
    is_open = data.get("isOpen", True)
    print(f"[Webhook][update_store_status] Body recebido: {data} | is_open={is_open} | keeta_merchant_id={config.keeta_merchant_id} | local_store_id={store.id}")

    # O path usa o merchant_id interno persistido no onboarding desta loja.
    merchant_id = str(config.keeta_merchant_id).strip()
    print(f"[Webhook][update_store_status] Chamando merchantUpdate/{merchant_id} | store_id={store.id} | is_open={is_open}...")
    success, error_detail = keeta_client.update_store_status(merchant_id, is_open)
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
@cross_origin()
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
        "merchantId": "159584113"
      }

    `keetaStoreId` também é aceito por compatibilidade. O valor informado é
    usado nos dois campos do onboarding e salvo para os próximos updates.
    """
    print(f"\n[Webhook][onboard_merchant] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    if not store:
        print(f"[Webhook][onboard_merchant] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Webhook][onboard_merchant] Body recebido: {data}")

    merchant_id = str(data.get("merchantId") or data.get("keetaStoreId") or "").strip()
    if not merchant_id:
        print("[Webhook][onboard_merchant] FALHA (400): merchantId não informado.")
        return jsonify({"error": "Informe o merchant ID da loja antes de ativar a integração."}), 400
    if not merchant_id.isdigit():
        print(f"[Webhook][onboard_merchant] FALHA (400): merchantId inválido='{merchant_id}'.")
        return jsonify({"error": "O merchant ID deve conter apenas números."}), 400

    print(f"[Webhook][onboard_merchant] merchant_id informado={merchant_id} | store_id local={store.id}")

    # Faz o onboarding com o mesmo valor em merchantId e keetaMerchantId.
    print(f"[Webhook][onboard_merchant] Chamando register_merchant(merchant_id={merchant_id}, my_local_store_id={store.id})...")
    result = keeta_client.register_merchant(merchant_id, my_local_store_id=str(store.id))
    print(f"[Webhook][onboard_merchant] Resultado do onboarding: {result}")
    if result is None:
        print("[Webhook][onboard_merchant] FALHA (502): onboarding não foi confirmado pela Keeta.")
        return jsonify({"error": "A Keeta não confirmou o onboarding da loja."}), 502

    # Salva o merchant_id informado para esta loja e os próximos updates.
    print(f"[Webhook][onboard_merchant] Salvando merchant_id na StoreConfig | store_id={store.id}")
    config = StoreConfig.query.get(store.id)
    if not config:
        print(f"[Webhook][onboard_merchant] Nenhuma config existente para store_id={store.id}. Criando nova...")
        config = StoreConfig(store_id=store.id)
        db.session.add(config)

    config.keeta_merchant_id = merchant_id
    db.session.commit()
    print(f"[Webhook][onboard_merchant] Config salva: {config.to_dict()}")

    print(f"[Webhook][onboard_merchant] FIM (sucesso) | store_id={store.id} | merchant_id={merchant_id}")
    return jsonify({
        "message": "Integração com a Keeta ativada com sucesso!",
        "merchantId": merchant_id,
        "keetaMerchantId": merchant_id,
        "onboardingResult": result,
        "config": config.to_dict(),
    }), 200

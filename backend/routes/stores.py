# =============================================================================
#  routes/stores.py  —  Gerenciamento de Lojas, Categorias e Cardápio
# =============================================================================
#
#  Cada usuário só pode ver/editar a SUA PRÓPRIA loja e o cardápio dela.
#
#  Endpoints:
#    GET    /api/stores/me                  → dados da loja
#    GET    /api/stores/me/categories       → listar categorias
#    POST   /api/stores/me/categories       → criar categoria
#    PUT    /api/stores/me/categories/<id>  → editar categoria
#    DELETE /api/stores/me/categories/<id>  → deletar categoria
#    GET    /api/stores/me/menu             → listar itens (com filtro ?categoryId=)
#    POST   /api/stores/me/menu             → criar item
#    PUT    /api/stores/me/menu/<id>        → editar item
#    DELETE /api/stores/me/menu/<id>        → deletar item
# =============================================================================

from flask import Blueprint, request, jsonify, g
from database import db
from models import MenuItem, MenuCategory, MenuOptionGroup, MenuOption, MenuAvailability, AvailabilityHour
from auth_utils import login_required

stores_bp = Blueprint("stores", __name__)


# --- Loja do usuário logado ---

@stores_bp.get("/me")
@login_required
def get_my_store():
    """Retorna a loja vinculada ao usuário logado."""
    print(f"\n[Stores][get_my_store] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    if not store:
        print(f"[Stores][get_my_store] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    print(f"[Stores][get_my_store] Loja encontrada: {store.to_dict()}")
    print(f"[Stores][get_my_store] FIM (sucesso) | store_id={store.id}")
    return jsonify(store.to_dict())


# --- Helper ---

def _get_store_or_404():
    store = g.current_user.store
    print(f"[Stores][_get_store_or_404] user_id={g.current_user.id} | store={store.to_dict() if store else None}")
    if not store:
        return None
    return store


# =============================================================================
#  CATEGORIAS DO CARDÁPIO
# =============================================================================

@stores_bp.get("/me/categories")
@login_required
def list_my_categories():
    """Lista as categorias do cardápio da loja do usuário logado, com seus itens."""
    print(f"\n[Stores][list_my_categories] INÍCIO | user_id={g.current_user.id}")

    store = _get_store_or_404()
    if not store:
        print(f"[Stores][list_my_categories] FALHA (404): usuário sem restaurante vinculado")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    categories = MenuCategory.query.filter_by(store_id=store.id).order_by(MenuCategory.index).all()
    print(f"[Stores][list_my_categories] {len(categories)} categoria(s) encontrada(s) para store_id={store.id}")

    result = [c.to_dict() for c in categories]
    print(f"[Stores][list_my_categories] FIM (sucesso) | store_id={store.id}")
    return jsonify(result)


@stores_bp.post("/me/categories")
@login_required
def create_my_category():
    """Cria uma nova categoria no cardápio da loja."""
    print(f"\n[Stores][create_my_category] INÍCIO | user_id={g.current_user.id}")

    store = _get_store_or_404()
    if not store:
        print(f"[Stores][create_my_category] FALHA (404): usuário sem restaurante vinculado")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Stores][create_my_category] Body recebido: {data}")

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nome da categoria é obrigatório."}), 400

    description = (data.get("description") or "").strip()
    external_code = (data.get("externalCode") or data.get("external_code") or "").strip()
    if not external_code:
        external_code = f"cat-{len(name)}"  # fallback

    # Calcula o próximo index
    max_index = db.session.query(db.func.max(MenuCategory.index)).filter_by(store_id=store.id).scalar() or -1

    try:
        category = MenuCategory(
            store_id=store.id,
            name=name,
            description=description,
            external_code=external_code,
            index=max_index + 1,
            status="AVAILABLE",
        )
        print(f"[Stores][create_my_category] Objeto criado: name='{category.name}' | external_code={category.external_code}")

        db.session.add(category)
        db.session.commit()
        print(f"[Stores][create_my_category] Commit realizado | category_id={category.id}")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][create_my_category] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao criar categoria."}), 500

    print(f"[Stores][create_my_category] FIM (sucesso) | category_id={category.id}")
    return jsonify(category.to_dict()), 201


@stores_bp.put("/me/categories/<int:category_id>")
@login_required
def update_my_category(category_id):
    """Atualiza uma categoria existente."""
    print(f"\n[Stores][update_my_category] INÍCIO | user_id={g.current_user.id} | category_id={category_id}")

    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    category = MenuCategory.query.filter_by(id=category_id, store_id=store.id).first()
    if not category:
        return jsonify({"error": "Categoria não encontrada."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Stores][update_my_category] Body: {data}")

    if "name" in data:
        category.name = (data["name"] or "").strip()
    if "description" in data:
        category.description = (data["description"] or "").strip()
    if "externalCode" in data:
        category.external_code = str(data["externalCode"]).strip()
    if "index" in data:
        category.index = int(data["index"])
    if "status" in data:
        category.status = data["status"]

    try:
        db.session.commit()
        print(f"[Stores][update_my_category] Atualizado: name='{category.name}' | status={category.status}")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][update_my_category] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao atualizar categoria."}), 500

    return jsonify(category.to_dict())


@stores_bp.delete("/me/categories/<int:category_id>")
@login_required
def delete_my_category(category_id):
    """Remove uma categoria e todos os seus itens (cascade)."""
    print(f"\n[Stores][delete_my_category] INÍCIO | user_id={g.current_user.id} | category_id={category_id}")

    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    category = MenuCategory.query.filter_by(id=category_id, store_id=store.id).first()
    if not category:
        return jsonify({"error": "Categoria não encontrada."}), 404

    cat_name = category.name
    try:
        db.session.delete(category)
        db.session.commit()
        print(f"[Stores][delete_my_category] Categoria '{cat_name}' (id={category_id}) removida.")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][delete_my_category] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao remover categoria."}), 500

    return jsonify({"message": f"Categoria '{cat_name}' removida."}), 200


# =============================================================================
#  ITENS DO CARDÁPIO
# =============================================================================

@stores_bp.get("/me/menu")
@login_required
def list_my_menu():
    """Lista itens do cardápio. Filtro opcional ?categoryId=X."""
    print(f"\n[Stores][list_my_menu] INÍCIO | user_id={g.current_user.id}")

    store = _get_store_or_404()
    if not store:
        print(f"[Stores][list_my_menu] FALHA (404)")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    category_id = request.args.get("categoryId", type=int)
    print(f"[Stores][list_my_menu] Buscando itens | store_id={store.id} | categoryId={category_id}")

    query = MenuItem.query.filter_by(store_id=store.id).order_by(MenuItem.index)
    if category_id:
        query = query.filter_by(category_id=category_id)

    items = query.all()
    print(f"[Stores][list_my_menu] {len(items)} item(ns) encontrado(s)")

    result = [i.to_dict() for i in items]
    print(f"[Stores][list_my_menu] FIM (sucesso) | store_id={store.id}")
    return jsonify(result)


@stores_bp.post("/me/menu")
@login_required
def create_my_menu_item():
    """Cria um novo item no cardápio."""
    print(f"\n[Stores][create_my_menu_item] INÍCIO | user_id={g.current_user.id}")

    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Stores][create_my_menu_item] Body recebido: {data}")

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nome do item é obrigatório."}), 400

    price = data.get("price")
    if price is None or float(price) < 0:
        return jsonify({"error": "Preço inválido."}), 400

    description = (data.get("description") or "").strip()
    external_code = (data.get("externalCode") or data.get("external_code") or "").strip()
    if not external_code:
        external_code = str(int(db.session.query(db.func.max(MenuItem.id)).scalar() or 0) + 1)

    category_id = data.get("categoryId")
    original_price = data.get("originalPrice", price)
    status = data.get("status", "AVAILABLE")
    image_url = data.get("imageUrl", "")

    # Calcula o próximo index dentro da categoria
    max_index = db.session.query(db.func.max(MenuItem.index)).filter_by(
        store_id=store.id, category_id=category_id
    ).scalar() or -1

    try:
        item = MenuItem(
            store_id=store.id,
            category_id=category_id,
            name=name,
            description=description,
            external_code=external_code,
            price=float(price),
            original_price=float(original_price),
            status=status,
            image_url=image_url,
            index=max_index + 1,
        )
        print(f"[Stores][create_my_menu_item] Item: name='{item.name}' | price={item.price} | extCode={item.external_code} | catId={category_id}")

        db.session.add(item)
        db.session.commit()
        print(f"[Stores][create_my_menu_item] Commit | item_id={item.id}")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][create_my_menu_item] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao criar item."}), 500

    return jsonify(item.to_dict()), 201


@stores_bp.put("/me/menu/<int:item_id>")
@login_required
def update_my_menu_item(item_id):
    """Atualiza um item existente."""
    print(f"\n[Stores][update_my_menu_item] INÍCIO | user_id={g.current_user.id} | item_id={item_id}")

    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    item = MenuItem.query.filter_by(id=item_id, store_id=store.id).first()
    if not item:
        return jsonify({"error": "Item não encontrado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Stores][update_my_menu_item] Body: {data}")

    if "name" in data:
        item.name = (data["name"] or "").strip()
    if "description" in data:
        item.description = (data["description"] or "").strip()
    if "externalCode" in data:
        item.external_code = str(data["externalCode"]).strip()
    if "price" in data and data["price"] is not None:
        item.price = float(data["price"])
    if "originalPrice" in data and data["originalPrice"] is not None:
        item.original_price = float(data["originalPrice"])
    if "categoryId" in data:
        item.category_id = data["categoryId"] if data["categoryId"] else None
    if "status" in data:
        item.status = data["status"]
    if "imageUrl" in data:
        item.image_url = data["imageUrl"]
    if "index" in data:
        item.index = int(data["index"])

    try:
        db.session.commit()
        print(f"[Stores][update_my_menu_item] Atualizado: name='{item.name}' | price={item.price}")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][update_my_menu_item] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao atualizar item."}), 500

    return jsonify(item.to_dict())


@stores_bp.delete("/me/menu/<int:item_id>")
@login_required
def delete_my_menu_item(item_id):
    """Remove um item do cardápio."""
    print(f"\n[Stores][delete_my_menu_item] INÍCIO | user_id={g.current_user.id} | item_id={item_id}")

    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    item = MenuItem.query.filter_by(id=item_id, store_id=store.id).first()
    if not item:
        return jsonify({"error": "Item não encontrado."}), 404

    item_name = item.name
    try:
        db.session.delete(item)
        db.session.commit()
        print(f"[Stores][delete_my_menu_item] Item '{item_name}' (id={item_id}) removido.")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][delete_my_menu_item] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao remover item."}), 500

    return jsonify({"message": f"Item '{item_name}' removido."}), 200


# =============================================================================
#  OPTION GROUPS (grupos de opções / complementos)
# =============================================================================

@stores_bp.get("/me/option-groups")
@login_required
def list_my_option_groups():
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    groups = MenuOptionGroup.query.filter_by(store_id=store.id).order_by(MenuOptionGroup.index).all()
    return jsonify([g.to_dict() for g in groups])


@stores_bp.post("/me/option-groups")
@login_required
def create_my_option_group():
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nome é obrigatório."}), 400
    try:
        g = MenuOptionGroup(
            store_id=store.id, name=name,
            description=(data.get("description") or "").strip(),
            external_code=(data.get("externalCode") or f"og-{name}").strip(),
            min_permitted=int(data.get("minPermitted", 0)),
            max_permitted=int(data.get("maxPermitted", 1)),
            price_method=data.get("priceMethod", "SUM"),
        )
        db.session.add(g)
        db.session.commit()
        return jsonify(g.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@stores_bp.put("/me/option-groups/<int:group_id>")
@login_required
def update_my_option_group(group_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    g = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not g:
        return jsonify({"error": "Grupo não encontrado."}), 404
    data = request.get_json(silent=True) or {}
    for f in ["name","description","externalCode","status","priceMethod"]:
        if f in data: setattr(g, f if f != "externalCode" else "external_code", data[f])
    if "minPermitted" in data: g.min_permitted = int(data["minPermitted"])
    if "maxPermitted" in data: g.max_permitted = int(data["maxPermitted"])
    db.session.commit()
    return jsonify(g.to_dict())


@stores_bp.delete("/me/option-groups/<int:group_id>")
@login_required
def delete_my_option_group(group_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    g = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not g:
        return jsonify({"error": "Grupo não encontrado."}), 404
    db.session.delete(g)
    db.session.commit()
    return jsonify({"message": "Removido."}), 200


# --- Options dentro de um OptionGroup ---

@stores_bp.post("/me/option-groups/<int:group_id>/options")
@login_required
def create_option(group_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    g = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not g:
        return jsonify({"error": "Grupo não encontrado."}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nome é obrigatório."}), 400
    try:
        o = MenuOption(
            option_group_id=g.id, name=name,
            description=(data.get("description") or "").strip(),
            external_code=(data.get("externalCode") or f"opt-{name}").strip(),
            price=float(data.get("price", 0)),
            max_permitted=data.get("maxPermitted"),
        )
        db.session.add(o)
        db.session.commit()
        return jsonify(o.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@stores_bp.put("/me/option-groups/<int:group_id>/options/<int:option_id>")
@login_required
def update_option(group_id, option_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    o = MenuOption.query.filter_by(id=option_id, option_group_id=group_id).first()
    if not o:
        return jsonify({"error": "Opção não encontrada."}), 404
    data = request.get_json(silent=True) or {}
    for f in ["name","description","externalCode","status"]:
        if f in data: setattr(o, f if f != "externalCode" else "external_code", data[f])
    if "price" in data and data["price"] is not None: o.price = float(data["price"])
    if "maxPermitted" in data: o.max_permitted = data["maxPermitted"]
    db.session.commit()
    return jsonify(o.to_dict())


@stores_bp.delete("/me/option-groups/<int:group_id>/options/<int:option_id>")
@login_required
def delete_option(group_id, option_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    o = MenuOption.query.filter_by(id=option_id, option_group_id=group_id).first()
    if not o:
        return jsonify({"error": "Opção não encontrada."}), 404
    db.session.delete(o)
    db.session.commit()
    return jsonify({"message": "Removida."}), 200


# --- Vincula/desvincula OptionGroups a MenuItems ---

@stores_bp.post("/me/menu/<int:item_id>/option-groups")
@login_required
def link_option_group(item_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    item = MenuItem.query.filter_by(id=item_id, store_id=store.id).first()
    if not item:
        return jsonify({"error": "Item não encontrado."}), 404
    data = request.get_json(silent=True) or {}
    group_id = data.get("optionGroupId")
    g = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not g:
        return jsonify({"error": "Grupo não encontrado."}), 404
    item.option_groups.append(g)
    db.session.commit()
    return jsonify({"message": "Vinculado."}), 200


@stores_bp.delete("/me/menu/<int:item_id>/option-groups/<int:group_id>")
@login_required
def unlink_option_group(item_id, group_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    item = MenuItem.query.filter_by(id=item_id, store_id=store.id).first()
    if not item:
        return jsonify({"error": "Item não encontrado."}), 404
    g = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not g:
        return jsonify({"error": "Grupo não encontrado."}), 404
    item.option_groups.remove(g)
    db.session.commit()
    return jsonify({"message": "Desvinculado."}), 200


# =============================================================================
#  AVAILABILITIES (disponibilidade por data/horário)
# =============================================================================

@stores_bp.get("/me/availabilities")
@login_required
def list_my_availabilities():
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    avails = MenuAvailability.query.filter_by(store_id=store.id).all()
    return jsonify([a.to_dict() for a in avails])


@stores_bp.post("/me/availabilities")
@login_required
def create_my_availability():
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nome é obrigatório."}), 400
    try:
        a = MenuAvailability(
            store_id=store.id, name=name,
            start_date=data.get("startDate"),
            end_date=data.get("endDate"),
        )
        for h in data.get("hours", []):
            a.hours.append(AvailabilityHour(
                day_of_week=h.get("dayOfWeek", "MONDAY"),
                start_time=h.get("startTime", "00:00:00.000Z"),
                end_time=h.get("endTime", "23:59:00.000Z"),
            ))
        db.session.add(a)
        db.session.commit()
        return jsonify(a.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@stores_bp.put("/me/availabilities/<int:avail_id>")
@login_required
def update_my_availability(avail_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    a = MenuAvailability.query.filter_by(id=avail_id, store_id=store.id).first()
    if not a:
        return jsonify({"error": "Disponibilidade não encontrada."}), 404
    data = request.get_json(silent=True) or {}
    if "name" in data: a.name = data["name"].strip()
    if "startDate" in data: a.start_date = data["startDate"]
    if "endDate" in data: a.end_date = data["endDate"]
    if "hours" in data:
        a.hours.clear()
        for h in data["hours"]:
            a.hours.append(AvailabilityHour(
                day_of_week=h.get("dayOfWeek", "MONDAY"),
                start_time=h.get("startTime", "00:00:00.000Z"),
                end_time=h.get("endTime", "23:59:00.000Z"),
            ))
    db.session.commit()
    return jsonify(a.to_dict())


@stores_bp.delete("/me/availabilities/<int:avail_id>")
@login_required
def delete_my_availability(avail_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    a = MenuAvailability.query.filter_by(id=avail_id, store_id=store.id).first()
    if not a:
        return jsonify({"error": "Disponibilidade não encontrada."}), 404
    db.session.delete(a)
    db.session.commit()
    return jsonify({"message": "Removida."}), 200


# --- Vincula/desvincula Availability a MenuItems ---

@stores_bp.post("/me/menu/<int:item_id>/availabilities")
@login_required
def link_availability(item_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    item = MenuItem.query.filter_by(id=item_id, store_id=store.id).first()
    if not item:
        return jsonify({"error": "Item não encontrado."}), 404
    data = request.get_json(silent=True) or {}
    avail_id = data.get("availabilityId")
    a = MenuAvailability.query.filter_by(id=avail_id, store_id=store.id).first()
    if not a:
        return jsonify({"error": "Disponibilidade não encontrada."}), 404
    item.availabilities.append(a)
    db.session.commit()
    return jsonify({"message": "Vinculada."}), 200


@stores_bp.delete("/me/menu/<int:item_id>/availabilities/<int:avail_id>")
@login_required
def unlink_availability(item_id, avail_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    item = MenuItem.query.filter_by(id=item_id, store_id=store.id).first()
    if not item:
        return jsonify({"error": "Item não encontrado."}), 404
    a = MenuAvailability.query.filter_by(id=avail_id, store_id=store.id).first()
    if not a:
        return jsonify({"error": "Disponibilidade não encontrada."}), 404
    item.availabilities.remove(a)
    db.session.commit()
    return jsonify({"message": "Desvinculada."}), 200

# =============================================================================
#  routes/stores.py  —  Gerenciamento de Lojas, Categorias e Cardápio
# =============================================================================
#
#  Cada usuário só pode ver/editar a SUA PRÓPRIA loja e o cardápio dela.
#
#  Endpoints:
#    GET    /api/stores/me                  → dados da loja
#    PUT    /api/stores/me                  → renomear a loja
#    GET    /api/stores/me/categories       → listar categorias
#    POST   /api/stores/me/categories       → criar categoria
#    PUT    /api/stores/me/categories/<id>  → editar categoria
#    DELETE /api/stores/me/categories/<id>  → deletar categoria
#    GET    /api/stores/me/menu             → listar itens (com filtro ?categoryId=)
#    POST   /api/stores/me/menu             → criar item
#    PUT    /api/stores/me/menu/<id>        → editar item
#    DELETE /api/stores/me/menu/<id>        → deletar item
# =============================================================================

import re
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from database import db
from models import MenuItem, MenuCategory, MenuOptionGroup, MenuOption, MenuAvailability, AvailabilityHour
from auth_utils import login_required
import keeta_client
from keeta_client import force_menu_sync

stores_bp = Blueprint("stores", __name__)


VALID_STATUSES = {"AVAILABLE", "UNAVAILABLE"}
VALID_PRICE_METHODS = {"SUM", "HIGHEST", "LOWEST"}
VALID_DAYS = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?:\.\d{3})?Z?$")
NAME_MAX_LENGTH = 150
DESCRIPTION_MAX_LENGTH = 500
EXTERNAL_CODE_MAX_LENGTH = 100


def _parse_name(value, label="Nome"):
    name = str(value or "").strip()
    if not name:
        raise ValueError(f"{label} é obrigatório.")
    if len(name) > NAME_MAX_LENGTH:
        raise ValueError(f"{label} deve ter no máximo {NAME_MAX_LENGTH} caracteres.")
    return name


def _parse_description(value):
    description = str(value or "").strip()
    if len(description) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"A descrição deve ter no máximo {DESCRIPTION_MAX_LENGTH} caracteres.")
    return description


def _parse_index(value):
    try:
        index = int(value)
    except (TypeError, ValueError):
        raise ValueError("A posição (index) deve ser um número inteiro.")
    if index < 0:
        raise ValueError("A posição (index) não pode ser negativa.")
    return index


def _parse_optional_limit(value):
    """maxPermitted de uma opção: vazio (sem limite) ou inteiro ≥ 1."""
    if value in (None, ""):
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise ValueError("O máximo da opção deve ser um número inteiro.")
    if limit < 1:
        raise ValueError("O máximo da opção deve ser pelo menos 1.")
    return limit


def _resolve_external_code(model, store, raw_code, prefix, exclude_id=None):
    """
    Devolve um código externo único dentro da loja. Em branco, gera um novo;
    preenchido, recusa se outro registro da mesma loja já usa o código
    (a Keeta exige códigos únicos).
    """
    code = str(raw_code or "").strip()
    if not code:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"
    if len(code) > EXTERNAL_CODE_MAX_LENGTH:
        raise ValueError(f"O código externo deve ter no máximo {EXTERNAL_CODE_MAX_LENGTH} caracteres.")

    if model is MenuOption:
        query = MenuOption.query.join(MenuOption.option_group).filter(MenuOptionGroup.store_id == store.id)
    else:
        query = model.query.filter(model.store_id == store.id)
    query = query.filter(model.external_code == code)
    if exclude_id is not None:
        query = query.filter(model.id != exclude_id)
    if query.first():
        raise ValueError(f"O código externo \"{code}\" já está em uso nesta loja.")
    return code


def _parse_time(value):
    """Aceita HH:MM, HH:MM:SS ou HH:MM:SS.000Z e normaliza para HH:MM:SS.000Z (UTC)."""
    match = TIME_PATTERN.match(str(value or "").strip())
    if not match:
        raise ValueError(f"Horário inválido: \"{value}\". Use HH:MM.")
    hours, minutes, seconds = match.group(1), match.group(2), match.group(3) or "00"
    return f"{hours}:{minutes}:{seconds}.000Z"


def _parse_date(value, label):
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{label} inválida. Use o formato AAAA-MM-DD.")


def _parse_availability_hours(raw_hours):
    if not isinstance(raw_hours, list) or not raw_hours:
        raise ValueError("Informe pelo menos um horário.")
    hours = []
    for raw in raw_hours:
        if not isinstance(raw, dict):
            raise ValueError("Horário inválido.")
        day = str(raw.get("dayOfWeek") or "").strip().upper()
        if day not in VALID_DAYS:
            raise ValueError(f"Dia da semana inválido: \"{raw.get('dayOfWeek')}\".")
        start = _parse_time(raw.get("startTime"))
        end = _parse_time(raw.get("endTime"))
        if start >= end:
            raise ValueError("O horário de início deve ser antes do horário de fim.")
        hours.append(AvailabilityHour(day_of_week=day, start_time=start, end_time=end))
    return hours


def _validate_date_range(start_date, end_date):
    if start_date and end_date and start_date > end_date:
        raise ValueError("A data de início deve ser anterior à data de fim.")


def _option_usage(item_ids):
    """Grupos de opções que usam algum dos itens como subitem."""
    if not item_ids:
        return []
    rows = (
        db.session.query(MenuOptionGroup.name)
        .join(MenuOption, MenuOption.option_group_id == MenuOptionGroup.id)
        .filter(MenuOption.item_id.in_(item_ids))
        .distinct()
        .all()
    )
    return sorted(name for (name,) in rows)

def _parse_price(value, field_name="Preço", required=True):
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} é obrigatório.")
        return None
    try:
        price = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} inválido.")
    if price < 0:
        raise ValueError(f"{field_name} não pode ser negativo.")
    return price


def _validate_status(value, field_name="Status"):
    status = str(value or "AVAILABLE").upper()
    if status not in VALID_STATUSES:
        raise ValueError(f"{field_name} inválido.")
    return status


def _validate_selection_limits(min_value, max_value):
    try:
        minimum = int(min_value)
        maximum = int(max_value)
    except (TypeError, ValueError):
        raise ValueError("Os limites mínimo e máximo devem ser números inteiros.")
    if minimum < 0 or maximum < 1 or minimum > maximum:
        raise ValueError("O mínimo deve ser ≥ 0, o máximo deve ser ≥ 1 e o mínimo não pode superar o máximo.")
    return minimum, maximum


def _owned_category(store, category_id, required=True):
    if category_id in (None, ""):
        if required:
            raise ValueError("O item precisa pertencer a uma categoria (categoryId).")
        return None
    category = MenuCategory.query.filter_by(id=category_id, store_id=store.id).first()
    if not category:
        raise ValueError("Categoria não encontrada para esta loja.")
    return category


def _owned_option_item(store, item_id):
    if item_id in (None, ""):
        return None
    item = MenuItem.query.filter_by(id=item_id, store_id=store.id).first()
    if not item:
        raise ValueError("Subitem não encontrado para esta loja.")
    return item


def _notify_keeta_menu_sync(store):
    """
    Notifica a Keeta (POST /merchantUpdate) sempre que o cardápio muda,
    para que ela puxe o cardápio atualizado via GET /merchant.

    O merchant_id usado aqui é o identificador persistido no onboarding
    (`StoreConfig.keeta_merchant_id`). O body vazio dispara o fluxo pull, e a
    Keeta busca o Merchant atualizado pelo endpoint GET /merchant.

    Falhas aqui são apenas logadas (não interrompem a resposta ao
    frontend), pois o cardápio já foi salvo com sucesso no nosso banco.
    """
    try:
        # Alterações normais disparam o pull do GET /merchant.
        from models import StoreConfig

        config = StoreConfig.query.get(store.id)
        if not config or not config.keeta_merchant_id:
            print(f"[Stores][_notify_keeta_menu_sync] AVISO: sem keetaMerchantId registrado | store_id={store.id}")
            return

        merchant_id = str(config.keeta_merchant_id).strip()
        from routes.keeta_webhook import _build_menu_response

        merchant = _build_menu_response(store.id)
        success, err = force_menu_sync(merchant_id, merchant)
        if not success:
            print(f"[Stores][_notify_keeta_menu_sync] AVISO: falha ao notificar a Keeta | store_id={store.id} | erro={err}")
        else:
            print(f"[Stores][_notify_keeta_menu_sync] Keeta notificada com sucesso | store_id={store.id}")
    except Exception as e:
        print(f"[Stores][_notify_keeta_menu_sync] ERRO inesperado (ignorado): {type(e).__name__}: {e}")


def _option_group_min_permitted_warning(group) -> str | None:
    """
    Verifica se `group.min_permitted` é maior que o número de opções com
    status AVAILABLE dentro do grupo.

    Por que isso importa: a Keeta esconde do app TODOS os itens vinculados
    a um optionGroup cujo minPermitted seja impossível de satisfazer (ex:
    minPermitted=2 mas só existe 1 opção disponível). Isso normalmente
    acontece quando o lojista exclui/desativa opções e esquece de reduzir
    o mínimo do grupo.

    Retorna uma mensagem de aviso (string) para exibir no frontend, ou
    None se a configuração estiver correta.
    """
    available_count = sum(1 for opt in group.options if (opt.status or "AVAILABLE") == "AVAILABLE")
    min_permitted = group.min_permitted or 0
    if min_permitted > available_count:
        return (
            f"Atenção: o mínimo de opções exigido ({min_permitted}) é maior que o número de "
            f"opções disponíveis ({available_count}). Isso fará a Keeta esconder todos os itens "
            f"vinculados a este grupo! Reduza o mínimo ou ative/adicione mais opções."
        )
    return None


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


@stores_bp.put("/me")
@login_required
def update_my_store():
    """Renomeia a loja do usuário logado. Body: { "name": "Novo nome" }"""
    from routes.auth import validate_name, STORE_NAME_MAX_LENGTH

    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    error = validate_name(name, "o nome do restaurante", STORE_NAME_MAX_LENGTH)
    if error:
        return jsonify({"error": error}), 400

    store.name = name
    db.session.commit()
    print(f"[Stores][update_my_store] Loja renomeada | store_id={store.id}")
    _notify_keeta_menu_sync(store)
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

    try:
        name = _parse_name(data.get("name"), "Nome da categoria")
        description = _parse_description(data.get("description"))
        external_code = _resolve_external_code(
            MenuCategory, store, data.get("externalCode") or data.get("external_code"), "cat"
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

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

    _notify_keeta_menu_sync(store)
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

    try:
        if "name" in data:
            category.name = _parse_name(data["name"], "Nome da categoria")
        if "description" in data:
            category.description = _parse_description(data["description"])
        if "externalCode" in data:
            category.external_code = _resolve_external_code(
                MenuCategory, store, data["externalCode"], "cat", exclude_id=category.id
            )
        if "index" in data:
            category.index = _parse_index(data["index"])
        if "status" in data:
            category.status = _validate_status(data["status"])
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400

    try:
        db.session.commit()
        print(f"[Stores][update_my_category] Atualizado: name='{category.name}' | status={category.status}")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][update_my_category] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao atualizar categoria."}), 500

    _notify_keeta_menu_sync(store)
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

    used_in = _option_usage([item.id for item in category.items])
    if used_in:
        return jsonify({
            "error": "Itens desta categoria são usados como opção nos grupos: "
                     f"{', '.join(used_in)}. Remova essas opções antes de excluir a categoria."
        }), 409

    cat_name = category.name
    try:
        db.session.delete(category)
        db.session.commit()
        print(f"[Stores][delete_my_category] Categoria '{cat_name}' (id={category_id}) removida.")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][delete_my_category] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao remover categoria."}), 500

    _notify_keeta_menu_sync(store)
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

    category_id = data.get("categoryId")
    try:
        name = _parse_name(data.get("name"), "Nome do item")
        description = _parse_description(data.get("description"))
        _owned_category(store, category_id)
        price = _parse_price(data.get("price"))
        original_price = _parse_price(data.get("originalPrice", price), "Preço original")
        if original_price < price:
            raise ValueError("O preço original não pode ser menor que o preço atual.")
        status = _validate_status(data.get("status"))
        external_code = _resolve_external_code(
            MenuItem, store, data.get("externalCode") or data.get("external_code"), "item"
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    image_url = (data.get("imageUrl") or "").strip()
    is_option_item = bool(data.get("isOptionItem", False))

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
            price=price,
            original_price=original_price,
            status=status,
            image_url=image_url,
            is_option_item=is_option_item,
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

    _notify_keeta_menu_sync(store)
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

    try:
        if "name" in data:
            item.name = _parse_name(data["name"], "Nome do item")
        if "description" in data:
            item.description = _parse_description(data["description"])
        if "externalCode" in data:
            item.external_code = _resolve_external_code(
                MenuItem, store, data["externalCode"], "item", exclude_id=item.id
            )
        if "price" in data:
            item.price = _parse_price(data["price"])
            # Sem preço original no body, um aumento de preço remove o
            # "desconto" antigo em vez de ser recusado.
            if "originalPrice" not in data and (item.original_price is None or item.original_price < item.price):
                item.original_price = item.price
        if "originalPrice" in data:
            item.original_price = _parse_price(data["originalPrice"], "Preço original")
        if item.original_price is not None and item.original_price < item.price:
            raise ValueError("O preço original não pode ser menor que o preço atual.")
        if "categoryId" in data:
            item.category_id = _owned_category(store, data["categoryId"]).id
        if "status" in data:
            item.status = _validate_status(data["status"])
        if "index" in data:
            item.index = _parse_index(data["index"])
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    if "isOptionItem" in data:
        item.is_option_item = bool(data["isOptionItem"])
    if "imageUrl" in data:
        item.image_url = str(data["imageUrl"] or "").strip()

    try:
        db.session.commit()
        print(f"[Stores][update_my_menu_item] Atualizado: name='{item.name}' | price={item.price}")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][update_my_menu_item] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao atualizar item."}), 500

    _notify_keeta_menu_sync(store)
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

    used_in = _option_usage([item.id])
    if used_in:
        return jsonify({
            "error": f"Este item é usado como opção nos grupos: {', '.join(used_in)}. "
                     "Remova essas opções antes de excluir o item."
        }), 409

    item_name = item.name
    try:
        db.session.delete(item)
        db.session.commit()
        print(f"[Stores][delete_my_menu_item] Item '{item_name}' (id={item_id}) removido.")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][delete_my_menu_item] ERRO: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao remover item."}), 500

    _notify_keeta_menu_sync(store)
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
    return jsonify([group.to_dict() for group in groups])


@stores_bp.post("/me/option-groups")
@login_required
def create_my_option_group():
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    data = request.get_json(silent=True) or {}
    try:
        name = _parse_name(data.get("name"))
        minimum, maximum = _validate_selection_limits(data.get("minPermitted", 0), data.get("maxPermitted", 1))
        price_method = str(data.get("priceMethod", "SUM")).upper()
        if price_method not in VALID_PRICE_METHODS:
            raise ValueError("Método de preço inválido.")
        group = MenuOptionGroup(
            store_id=store.id, name=name,
            description=_parse_description(data.get("description")),
            external_code=_resolve_external_code(MenuOptionGroup, store, data.get("externalCode"), "og"),
            status=_validate_status(data.get("status")),
            min_permitted=minimum,
            max_permitted=maximum,
            price_method=price_method,
            index=(db.session.query(db.func.max(MenuOptionGroup.index)).filter_by(store_id=store.id).scalar() or -1) + 1,
        )
        db.session.add(group)
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Erro ao criar grupo."}), 500

    _notify_keeta_menu_sync(store)
    result = group.to_dict()
    warning = _option_group_min_permitted_warning(group)
    if warning:
        result["warning"] = warning
    return jsonify(result), 201


@stores_bp.put("/me/option-groups/<int:group_id>")
@login_required
def update_my_option_group(group_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    group = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not group:
        return jsonify({"error": "Grupo não encontrado."}), 404
    data = request.get_json(silent=True) or {}
    try:
        if "name" in data: group.name = _parse_name(data["name"])
        if "description" in data: group.description = _parse_description(data["description"])
        if "externalCode" in data:
            group.external_code = _resolve_external_code(
                MenuOptionGroup, store, data["externalCode"], "og", exclude_id=group.id
            )
        if "status" in data: group.status = _validate_status(data["status"])
        if "priceMethod" in data:
            group.price_method = str(data["priceMethod"]).upper()
            if group.price_method not in VALID_PRICE_METHODS:
                raise ValueError("Método de preço inválido.")
        group.min_permitted, group.max_permitted = _validate_selection_limits(
            data.get("minPermitted", group.min_permitted), data.get("maxPermitted", group.max_permitted)
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Stores] ERRO ao salvar: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao salvar no banco. Tente novamente."}), 500

    _notify_keeta_menu_sync(store)
    result = group.to_dict()
    warning = _option_group_min_permitted_warning(group)
    if warning:
        result["warning"] = warning
    return jsonify(result)


@stores_bp.delete("/me/option-groups/<int:group_id>")
@login_required
def delete_my_option_group(group_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    group = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not group:
        return jsonify({"error": "Grupo não encontrado."}), 404

    try:
        db.session.delete(group)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Stores] ERRO ao salvar: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao salvar no banco. Tente novamente."}), 500

    _notify_keeta_menu_sync(store)
    return jsonify({"message": "Removido."}), 200


# --- Options dentro de um OptionGroup ---

@stores_bp.post("/me/option-groups/<int:group_id>/options")
@login_required
def create_option(group_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    group = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not group:
        return jsonify({"error": "Grupo não encontrado."}), 404
    data = request.get_json(silent=True) or {}
    try:
        name = _parse_name(data.get("name"))
        item = _owned_option_item(store, data.get("itemId"))
        price = _parse_price(data.get("price", 0), required=False)
        option = MenuOption(
            option_group_id=group.id, item_id=item.id if item else None, name=name,
            description=_parse_description(data.get("description")),
            external_code=_resolve_external_code(MenuOption, store, data.get("externalCode"), "opt"),
            price=price if price is not None else 0.0,
            status=_validate_status(data.get("status")),
            index=(db.session.query(db.func.max(MenuOption.index)).filter_by(option_group_id=group.id).scalar() or -1) + 1,
            max_permitted=_parse_optional_limit(data.get("maxPermitted")),
        )
        db.session.add(option)
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Erro ao criar opção."}), 500

    _notify_keeta_menu_sync(store)
    result = option.to_dict()
    warning = _option_group_min_permitted_warning(group)
    if warning:
        result["warning"] = warning
    return jsonify(result), 201


@stores_bp.put("/me/option-groups/<int:group_id>/options/<int:option_id>")
@login_required
def update_option(group_id, option_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    option = MenuOption.query.join(MenuOption.option_group).filter(
        MenuOption.id == option_id,
        MenuOption.option_group_id == group_id,
        MenuOptionGroup.store_id == store.id,
    ).first()
    if not option:
        return jsonify({"error": "Opção não encontrada."}), 404
    data = request.get_json(silent=True) or {}
    try:
        if "name" in data: option.name = _parse_name(data["name"])
        if "description" in data: option.description = _parse_description(data["description"])
        if "externalCode" in data:
            option.external_code = _resolve_external_code(
                MenuOption, store, data["externalCode"], "opt", exclude_id=option.id
            )
        if "status" in data: option.status = _validate_status(data["status"])
        if "price" in data: option.price = _parse_price(data["price"], required=False) or 0.0
        if "itemId" in data:
            item = _owned_option_item(store, data["itemId"])
            option.item_id = item.id if item else None
        if "maxPermitted" in data: option.max_permitted = _parse_optional_limit(data["maxPermitted"])
        if "index" in data: option.index = _parse_index(data["index"])
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Erro ao atualizar opção."}), 500

    _notify_keeta_menu_sync(store)
    result = option.to_dict()
    warning = _option_group_min_permitted_warning(option.option_group)
    if warning:
        result["warning"] = warning
    return jsonify(result)


@stores_bp.delete("/me/option-groups/<int:group_id>/options/<int:option_id>")
@login_required
def delete_option(group_id, option_id):
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    option = MenuOption.query.join(MenuOption.option_group).filter(
        MenuOption.id == option_id,
        MenuOption.option_group_id == group_id,
        MenuOptionGroup.store_id == store.id,
    ).first()
    if not option:
        return jsonify({"error": "Opção não encontrada."}), 404

    group = option.option_group
    try:
        db.session.delete(option)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Stores] ERRO ao salvar: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao salvar no banco. Tente novamente."}), 500

    _notify_keeta_menu_sync(store)
    result = {"message": "Removida."}
    warning = _option_group_min_permitted_warning(group)
    if warning:
        result["warning"] = warning
    return jsonify(result), 200


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
    group = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not group:
        return jsonify({"error": "Grupo não encontrado."}), 404
    if group not in item.option_groups:
        item.option_groups.append(group)
    db.session.commit()

    _notify_keeta_menu_sync(store)
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
    group = MenuOptionGroup.query.filter_by(id=group_id, store_id=store.id).first()
    if not group:
        return jsonify({"error": "Grupo não encontrado."}), 404
    if group not in item.option_groups:
        return jsonify({"error": "Este grupo não está vinculado ao item."}), 404
    item.option_groups.remove(group)
    db.session.commit()

    _notify_keeta_menu_sync(store)
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
    try:
        name = _parse_name(data.get("name"))
        start_date = _parse_date(data.get("startDate"), "Data de início")
        end_date = _parse_date(data.get("endDate"), "Data de fim")
        _validate_date_range(start_date, end_date)
        hours = _parse_availability_hours(data.get("hours"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    try:
        a = MenuAvailability(store_id=store.id, name=name, start_date=start_date, end_date=end_date)
        a.hours.extend(hours)
        db.session.add(a)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Stores] ERRO ao salvar: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao salvar no banco. Tente novamente."}), 500

    _notify_keeta_menu_sync(store)
    return jsonify(a.to_dict()), 201


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
    try:
        name = _parse_name(data["name"]) if "name" in data else a.name
        start_date = _parse_date(data["startDate"], "Data de início") if "startDate" in data else a.start_date
        end_date = _parse_date(data["endDate"], "Data de fim") if "endDate" in data else a.end_date
        _validate_date_range(start_date, end_date)
        hours = _parse_availability_hours(data["hours"]) if "hours" in data else None
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    a.name, a.start_date, a.end_date = name, start_date, end_date
    if hours is not None:
        a.hours.clear()
        a.hours.extend(hours)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Stores] ERRO ao salvar: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao salvar no banco. Tente novamente."}), 500

    _notify_keeta_menu_sync(store)
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
    try:
        db.session.delete(a)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[Stores] ERRO ao salvar: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao salvar no banco. Tente novamente."}), 500

    _notify_keeta_menu_sync(store)
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
    if a not in item.availabilities:
        item.availabilities.append(a)
    db.session.commit()

    _notify_keeta_menu_sync(store)
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
    if a not in item.availabilities:
        return jsonify({"error": "Esta disponibilidade não está vinculada ao item."}), 404
    item.availabilities.remove(a)
    db.session.commit()

    _notify_keeta_menu_sync(store)
    return jsonify({"message": "Desvinculada."}), 200

# =============================================================================
#  routes/stores.py  —  Gerenciamento de Lojas e Cardápio
# =============================================================================
#
#  Cada usuário só pode ver/editar a SUA PRÓPRIA loja e o cardápio dela.
# =============================================================================

from flask import Blueprint, request, jsonify, g
from database import db
from models import MenuItem
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


# --- Cardápio ---

def _get_store_or_404():
    store = g.current_user.store
    print(f"[Stores][_get_store_or_404] user_id={g.current_user.id} | store={store.to_dict() if store else None}")
    if not store:
        return None
    return store


@stores_bp.get("/me/menu")
@login_required
def list_my_menu():
    print(f"\n[Stores][list_my_menu] INÍCIO | user_id={g.current_user.id}")

    store = _get_store_or_404()
    if not store:
        print(f"[Stores][list_my_menu] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    print(f"[Stores][list_my_menu] Buscando itens de menu para store_id={store.id}...")
    items = MenuItem.query.filter_by(store_id=store.id).all()
    print(f"[Stores][list_my_menu] {len(items)} item(ns) encontrado(s)")

    result = [i.to_dict() for i in items]
    print(f"[Stores][list_my_menu] FIM (sucesso) | store_id={store.id} | total_itens={len(result)}")
    return jsonify(result)


@stores_bp.post("/me/menu")
@login_required
def create_my_menu_item():
    print(f"\n[Stores][create_my_menu_item] INÍCIO | user_id={g.current_user.id}")

    store = _get_store_or_404()
    if not store:
        print(f"[Stores][create_my_menu_item] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Stores][create_my_menu_item] Body recebido: {data}")

    try:
        item = MenuItem(
            store_id=store.id,
            name=data["name"],
            price=data["price"],
        )
        print(f"[Stores][create_my_menu_item] Objeto MenuItem montado: name='{item.name}' | price={item.price} | store_id={store.id}")

        db.session.add(item)
        db.session.commit()
        print(f"[Stores][create_my_menu_item] Commit realizado | item_id={item.id}")
    except Exception as e:
        db.session.rollback()
        print(f"[Stores][create_my_menu_item] ERRO ao criar item. Rollback executado. Detalhes: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro ao criar item do cardápio."}), 500

    print(f"[Stores][create_my_menu_item] FIM (sucesso) | item_id={item.id} | store_id={store.id}")
    return jsonify(item.to_dict()), 201

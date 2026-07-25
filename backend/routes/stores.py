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
    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404
    return jsonify(store.to_dict())


# --- Cardápio ---

def _get_store_or_404():
    store = g.current_user.store
    if not store:
        return None
    return store


@stores_bp.get("/me/menu")
@login_required
def list_my_menu():
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    items = MenuItem.query.filter_by(store_id=store.id).all()
    return jsonify([i.to_dict() for i in items])


@stores_bp.post("/me/menu")
@login_required
def create_my_menu_item():
    store = _get_store_or_404()
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    item = MenuItem(
        store_id=store.id,
        name=data["name"],
        price=data["price"],
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201

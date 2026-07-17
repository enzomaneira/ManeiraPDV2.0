# =============================================================================
#  routes/stores.py  —  Gerenciamento de Lojas e Cardápio
# =============================================================================

from flask import Blueprint, request, jsonify
from database import db
from models import Store, MenuItem

stores_bp = Blueprint("stores", __name__)


# --- Lojas ---

@stores_bp.get("/")
def list_stores():
    return jsonify([s.to_dict() for s in Store.query.all()])


@stores_bp.get("/<int:store_id>")
def get_store(store_id):
    store = Store.query.get_or_404(store_id)
    return jsonify(store.to_dict())


@stores_bp.post("/")
def create_store():
    data = request.get_json()
    store = Store(name=data["name"])
    db.session.add(store)
    db.session.commit()
    return jsonify(store.to_dict()), 201


# --- Cardápio ---

@stores_bp.get("/<int:store_id>/menu")
def list_menu(store_id):
    items = MenuItem.query.filter_by(store_id=store_id).all()
    return jsonify([i.to_dict() for i in items])


@stores_bp.post("/<int:store_id>/menu")
def create_menu_item(store_id):
    data = request.get_json()
    item = MenuItem(
        store_id=store_id,
        name=data["name"],
        price=data["price"],
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201

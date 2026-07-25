# =============================================================================
#  routes/config.py  —  Configurações do PDV
# =============================================================================
#
#  Gerencia as configurações da loja do usuário logado: modo de aceite
#  automático e o ID do restaurante na Keeta.
#
#  Cada usuário só enxerga/edita a configuração da SUA PRÓPRIA loja
#  (StoreConfig.store_id == g.current_user.store.id).
# =============================================================================

from flask import Blueprint, request, jsonify, g
from database import db
from models import StoreConfig
from auth_utils import login_required

config_bp = Blueprint("config", __name__)


@config_bp.get("/")
@login_required
def get_config():
    """
    Retorna as configurações atuais da loja do usuário logado.
    Se não existir, cria um registro padrão com autoAccept=True.
    """
    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    config = StoreConfig.query.get(store.id)
    if not config:
        config = StoreConfig(store_id=store.id, auto_accept=True, is_store_open=True)
        db.session.add(config)
        db.session.commit()
    return jsonify(config.to_dict())


@config_bp.post("/")
@login_required
def update_config():
    """
    Salva as configurações da loja do usuário logado.

    Campos aceitos:
      autoAccept      (bool)  — aceitar pedidos automaticamente
      keetaMerchantId (str)   — ID da loja na plataforma Keeta
    """
    store = g.current_user.store
    if not store:
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}

    config = StoreConfig.query.get(store.id) or StoreConfig(store_id=store.id)
    config.auto_accept       = data.get("autoAccept", config.auto_accept)
    config.keeta_merchant_id = data.get("keetaMerchantId", config.keeta_merchant_id)

    db.session.add(config)
    db.session.commit()

    return jsonify(config.to_dict())

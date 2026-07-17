# =============================================================================
#  routes/config.py  —  Configurações do PDV
# =============================================================================
#
#  Gerencia as configurações da loja: modo de aceite e ID da Keeta.
#  Há sempre apenas UMA linha na tabela store_config (id=1).
# =============================================================================

from flask import Blueprint, request, jsonify
from database import db
from models import StoreConfig

config_bp = Blueprint("config", __name__)


@config_bp.get("/")
def get_config():
    """
    Retorna as configurações atuais da loja.
    Se não existir, cria um registro padrão com autoAccept=True.
    """
    config = StoreConfig.query.get(1)
    if not config:
        config = StoreConfig(id=1, auto_accept=True)
        db.session.add(config)
        db.session.commit()
    return jsonify(config.to_dict())


@config_bp.post("/")
def update_config():
    """
    Salva as configurações da loja.

    Campos aceitos:
      autoAccept      (bool)  — aceitar pedidos automaticamente
      keetaMerchantId (str)   — ID da loja na plataforma Keeta
    """
    data = request.get_json()

    config = StoreConfig.query.get(1) or StoreConfig(id=1)
    config.auto_accept       = data.get("autoAccept", config.auto_accept)
    config.keeta_merchant_id = data.get("keetaMerchantId", config.keeta_merchant_id)

    db.session.add(config)
    db.session.commit()

    return jsonify(config.to_dict())

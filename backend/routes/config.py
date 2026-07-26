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
    print(f"\n[Config][get_config] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    print(f"[Config][get_config] Loja do usuário: {store.to_dict() if store else None}")

    if not store:
        print(f"[Config][get_config] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    print(f"[Config][get_config] Buscando StoreConfig para store_id={store.id}...")
    config = StoreConfig.query.get(store.id)

    if not config:
        print(f"[Config][get_config] Nenhuma config encontrada. Criando config padrão para store_id={store.id}...")
        config = StoreConfig(store_id=store.id, auto_accept=True, is_store_open=True)
        db.session.add(config)
        db.session.commit()
        print(f"[Config][get_config] Config padrão criada e commitada: {config.to_dict()}")
    else:
        print(f"[Config][get_config] Config encontrada: {config.to_dict()}")

    print(f"[Config][get_config] FIM (sucesso) | store_id={store.id}")
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
    print(f"\n[Config][update_config] INÍCIO | user_id={g.current_user.id}")

    store = g.current_user.store
    print(f"[Config][update_config] Loja do usuário: {store.to_dict() if store else None}")

    if not store:
        print(f"[Config][update_config] FALHA (404): usuário sem restaurante vinculado | user_id={g.current_user.id}")
        return jsonify({"error": "Usuário não possui um restaurante vinculado."}), 404

    data = request.get_json(silent=True) or {}
    print(f"[Config][update_config] Body recebido: {data}")

    config = StoreConfig.query.get(store.id) or StoreConfig(store_id=store.id)
    print(f"[Config][update_config] Config ANTES da atualização: autoAccept={config.auto_accept} | keetaMerchantId={config.keeta_merchant_id}")

    config.auto_accept       = data.get("autoAccept", config.auto_accept)
    config.keeta_merchant_id = data.get("keetaMerchantId", config.keeta_merchant_id)

    print(f"[Config][update_config] Config DEPOIS da atualização: autoAccept={config.auto_accept} | keetaMerchantId={config.keeta_merchant_id}")

    db.session.add(config)
    db.session.commit()
    print(f"[Config][update_config] Commit realizado com sucesso | store_id={store.id}")

    print(f"[Config][update_config] FIM (sucesso) | store_id={store.id}")
    return jsonify(config.to_dict())

# =============================================================================
#  routes/config.py  —  Configurações do PDV
# =============================================================================
#
#  Gerencia as configurações da loja do usuário logado: modo de aceite
#  automático, ID do restaurante na Keeta, contatos e horário de funcionamento.
#
#  Cada usuário só enxerga/edita a configuração da SUA PRÓPRIA loja
#  (StoreConfig.store_id == g.current_user.store.id).
# =============================================================================

import json
from flask import Blueprint, request, jsonify, g
from database import db
from models import StoreConfig
from auth_utils import login_required
from routes.auth import validate_email
import keeta_client

config_bp = Blueprint("config", __name__)


def _config_response(config):
    """Config + o e-mail do dono, que é o contato usado quando a loja não cadastra outro."""
    data = config.to_dict()
    data["ownerEmail"] = g.current_user.email
    return jsonify(data)


@config_bp.get("/")
@config_bp.get("")       # aceita também sem trailing slash (evita redirect CORS)
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
    return _config_response(config)


@config_bp.post("/")
@config_bp.post("")      # aceita também sem trailing slash (evita redirect 308)
@login_required
def update_config():
    """
    Salva as configurações da loja do usuário logado.

    Campos aceitos:
      autoAccept      (bool)  — aceitar pedidos automaticamente
      keetaMerchantId (str)   — merchant ID da loja usado no onboarding
                                 e nas notificações merchantUpdate
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

    if "autoAccept" in data:
        if not isinstance(data["autoAccept"], bool):
            return jsonify({"error": "autoAccept deve ser verdadeiro ou falso."}), 400
        config.auto_accept = data["autoAccept"]

    if "detailedDeliveryStatus" in data:
        if not isinstance(data["detailedDeliveryStatus"], bool):
            return jsonify({"error": "detailedDeliveryStatus deve ser verdadeiro ou falso."}), 400
        config.detailed_delivery_status = data["detailedDeliveryStatus"]

    # O merchant ID só pode ser definido pelo onboarding (PUT /api/keeta/onboard),
    # que confirma com a Keeta e impede usar o ID de outra loja. Aqui só
    # aceitamos o mesmo valor que já está salvo (o frontend reenvia o campo).
    requested_merchant_id = str(data.get("keetaMerchantId") or data.get("merchantId") or "").strip()
    if requested_merchant_id and requested_merchant_id != (config.keeta_merchant_id or ""):
        return jsonify({"error": "Para alterar o merchant ID, use \"Ativar Integração\"."}), 400

    # Contatos e horário que a Keeta mostra para a loja. Vazio = volta ao padrão.
    try:
        if "contactEmail" in data:
            email = str(data.get("contactEmail") or "").strip().lower()
            error = validate_email(email) if email else None
            if error:
                raise ValueError("Informe um e-mail de contato válido.")
            config.contact_email = email or None
        if "contactPhone" in data:
            phone = str(data.get("contactPhone") or "").strip()
            config.contact_phone = keeta_client.normalize_phone(phone) if phone else None
        if "serviceHours" in data:
            periods = keeta_client.parse_service_hours(data.get("serviceHours") or [])
            config.service_hours_json = json.dumps(periods) if periods else None
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400

    print(f"[Config][update_config] Config DEPOIS da atualização: autoAccept={config.auto_accept} | keetaMerchantId={config.keeta_merchant_id}")

    db.session.add(config)
    db.session.commit()
    print(f"[Config][update_config] Commit realizado com sucesso | store_id={store.id}")

    print(f"[Config][update_config] FIM (sucesso) | store_id={store.id}")
    return _config_response(config)

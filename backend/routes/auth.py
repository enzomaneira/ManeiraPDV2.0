# =============================================================================
#  routes/auth.py  —  Cadastro, Login e dados do usuário logado
# =============================================================================
#
#  Fluxo:
#    POST /api/auth/register  → cria o usuário + a loja vinculada a ele
#    POST /api/auth/login     → valida email/senha e devolve um token JWT
#    GET  /api/auth/me        → retorna os dados do usuário logado (token)
# =============================================================================

from datetime import datetime
from flask import Blueprint, request, jsonify, g

from database import db
from models import User, Store, StoreConfig
from auth_utils import generate_token, login_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    """
    Cria um novo usuário e, junto, o restaurante (Store) vinculado a ele.

    Body esperado:
      {
        "name": "Enzo Maneira",
        "email": "enzo@exemplo.com",
        "password": "123456",
        "storeName": "Restaurante do Enzo"
      }
    """
    data = request.get_json(silent=True) or {}

    name       = (data.get("name") or "").strip()
    email      = (data.get("email") or "").strip().lower()
    password   = data.get("password") or ""
    store_name = (data.get("storeName") or "").strip()

    # --- Validações básicas ---
    if not name or not email or not password or not store_name:
        return jsonify({"error": "Preencha nome, e-mail, senha e nome do restaurante."}), 400

    if len(password) < 6:
        return jsonify({"error": "A senha deve ter pelo menos 6 caracteres."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Já existe uma conta cadastrada com este e-mail."}), 409

    # --- Cria o usuário ---
    user = User(
        name=name,
        email=email,
        created_at=datetime.now().isoformat(),
    )
    user.set_password(password)

    db.session.add(user)
    db.session.flush()  # garante que user.id já existe, sem precisar commitar ainda

    # --- Cria a loja (restaurante) vinculada a este usuário ---
    store = Store(name=store_name, owner_id=user.id)
    db.session.add(store)
    db.session.flush()

    # --- Cria a configuração padrão da loja (integração Keeta) ---
    config = StoreConfig(store_id=store.id, auto_accept=True, is_store_open=True)
    db.session.add(config)

    db.session.commit()

    token = generate_token(user.id)

    return jsonify({
        "token": token,
        "user": user.to_dict(),
    }), 201


@auth_bp.post("/login")
def login():
    """
    Autentica um usuário existente.

    Body esperado:
      { "email": "enzo@exemplo.com", "password": "123456" }
    """
    data = request.get_json(silent=True) or {}

    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "E-mail ou senha inválidos."}), 401

    token = generate_token(user.id)

    return jsonify({
        "token": token,
        "user": user.to_dict(),
    })


@auth_bp.get("/me")
@login_required
def me():
    """
    Retorna os dados do usuário logado (usado para validar o token salvo
    no frontend quando a página é recarregada).
    """
    return jsonify(g.current_user.to_dict())

# =============================================================================
#  routes/auth.py  —  Cadastro, Login e dados do usuário logado
# =============================================================================
#
#  Fluxo:
#    POST /api/auth/register  → cria o usuário + a loja vinculada a ele
#    POST /api/auth/login     → valida email/senha e devolve um token JWT
#    GET  /api/auth/me        → retorna os dados do usuário logado (token)
# =============================================================================

import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from flask import Blueprint, request, jsonify, g

from database import db
from models import User, Store, StoreConfig
from auth_utils import generate_token, login_required

auth_bp = Blueprint("auth", __name__)

RESET_TOKEN_TTL_MINUTES = 30


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _send_password_reset_email(email: str, reset_url: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "no-reply@maneirapdv.local")

    if not smtp_host:
        return False

    message = EmailMessage()
    message["Subject"] = "Redefinição de senha — ManeiraPDV"
    message["From"] = smtp_from
    message["To"] = email
    message.set_content(
        "Recebemos uma solicitação para redefinir sua senha do ManeiraPDV.\n\n"
        f"Acesse este link para criar uma nova senha (válido por {RESET_TOKEN_TTL_MINUTES} minutos):\n"
        f"{reset_url}\n\n"
        "Se você não solicitou a redefinição, ignore este e-mail."
    )

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
        if os.getenv("SMTP_USE_TLS", "true").lower() == "true":
            smtp.starttls()
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
    return True


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
    print("\n" + "=" * 70)
    print("[Auth][register] INÍCIO da requisição POST /api/auth/register")

    data = request.get_json(silent=True) or {}
    print(f"[Auth][register] Body recebido (bruto): {data}")

    name       = (data.get("name") or "").strip()
    email      = (data.get("email") or "").strip().lower()
    password   = data.get("password") or ""
    store_name = (data.get("storeName") or "").strip()

    print(f"[Auth][register] Dados normalizados | name='{name}' | email='{email}' | storeName='{store_name}' | password_len={len(password)}")

    # --- Validações básicas ---
    if not name or not email or not password or not store_name:
        print(f"[Auth][register] FALHA (400): campos obrigatórios ausentes | name_ok={bool(name)} email_ok={bool(email)} password_ok={bool(password)} storeName_ok={bool(store_name)}")
        return jsonify({"error": "Preencha nome, e-mail, senha e nome do restaurante."}), 400

    if len(password) < 6:
        print(f"[Auth][register] FALHA (400): senha muito curta | tamanho={len(password)}")
        return jsonify({"error": "A senha deve ter pelo menos 6 caracteres."}), 400

    print(f"[Auth][register] Verificando se já existe usuário com email='{email}'...")
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        print(f"[Auth][register] FALHA (409): e-mail já cadastrado | email='{email}' | user_id_existente={existing_user.id}")
        return jsonify({"error": "Já existe uma conta cadastrada com este e-mail."}), 409

    print(f"[Auth][register] E-mail disponível. Prosseguindo com a criação do usuário...")

    try:
        # --- Cria o usuário ---
        user = User(
            name=name,
            email=email,
            created_at=datetime.now().isoformat(),
        )
        user.set_password(password)
        print(f"[Auth][register] Objeto User montado (antes do commit) | name='{name}' | email='{email}'")

        db.session.add(user)
        print("[Auth][register] db.session.add(user) executado. Fazendo flush para obter user.id...")
        db.session.flush()  # garante que user.id já existe, sem precisar commitar ainda
        print(f"[Auth][register] Flush concluído | user.id={user.id}")

        # --- Cria a loja (restaurante) vinculada a este usuário ---
        store = Store(name=store_name, owner_id=user.id)
        print(f"[Auth][register] Objeto Store montado | name='{store_name}' | owner_id={user.id}")

        db.session.add(store)
        print("[Auth][register] db.session.add(store) executado. Fazendo flush para obter store.id...")
        db.session.flush()
        print(f"[Auth][register] Flush concluído | store.id={store.id}")

        # --- Cria a configuração padrão da loja (integração Keeta) ---
        config = StoreConfig(store_id=store.id, auto_accept=True, is_store_open=True)
        print(f"[Auth][register] Objeto StoreConfig montado | store_id={store.id} | auto_accept=True | is_store_open=True")
        db.session.add(config)

        print("[Auth][register] Executando commit final da transação (user + store + config)...")
        db.session.commit()
        print(f"[Auth][register] COMMIT bem-sucedido | user_id={user.id} | store_id={store.id}")

    except Exception as e:
        db.session.rollback()
        print(f"[Auth][register] ERRO CRÍTICO ao salvar no banco. Rollback executado. Detalhes: {type(e).__name__}: {e}")
        print("[Auth][register] FIM (falha - erro de banco)")
        print("=" * 70 + "\n")
        return jsonify({"error": "Erro interno ao criar a conta. Tente novamente."}), 500

    print(f"[Auth][register] Gerando token JWT para user_id={user.id}...")
    token = generate_token(user.id)
    print(f"[Auth][register] Token gerado com sucesso | preview={token[:20]}...")

    response_data = {
        "token": token,
        "user": user.to_dict(),
    }
    print(f"[Auth][register] Resposta final: {response_data}")
    print(f"[Auth][register] FIM (sucesso) | user_id={user.id} | store_id={store.id}")
    print("=" * 70 + "\n")

    return jsonify(response_data), 201


@auth_bp.post("/request-password-reset")
def request_password_reset():
    """Cria um token de uso único e envia o link de redefinição por e-mail."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    generic_response = {
        "message": "Se existir uma conta com este e-mail, enviaremos instruções para redefinir a senha."
    }

    if not email:
        return jsonify(generic_response)

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(generic_response)

    raw_token = secrets.token_urlsafe(32)
    user.reset_token_hash = _hash_reset_token(raw_token)
    user.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    db.session.commit()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    reset_url = f"{frontend_url}/reset-password?token={raw_token}"

    try:
        email_sent = _send_password_reset_email(email, reset_url)
    except Exception as error:
        db.session.rollback()
        print(f"[Auth][password-reset] Falha ao enviar e-mail: {type(error).__name__}: {error}")
        return jsonify({"error": "Não foi possível enviar o e-mail de recuperação."}), 500

    response_data = dict(generic_response)
    # Útil somente em desenvolvimento local sem SMTP. Nunca habilite em produção.
    if not email_sent and os.getenv("RESET_PASSWORD_EXPOSE_TOKEN", "false").lower() == "true":
        response_data["resetToken"] = raw_token
        response_data["resetUrl"] = reset_url
        print(f"[Auth][password-reset] Token de desenvolvimento gerado para {email}.")
    elif not email_sent:
        print("[Auth][password-reset] SMTP_HOST não configurado; token não exposto.")

    return jsonify(response_data)


@auth_bp.post("/reset-password")
def reset_password():
    """Valida o token de recuperação e troca a senha, invalidando o token."""
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""

    if len(password) < 6:
        return jsonify({"error": "A senha deve ter pelo menos 6 caracteres."}), 400
    if not token:
        return jsonify({"error": "Token de recuperação inválido ou expirado."}), 400

    user = User.query.filter_by(reset_token_hash=_hash_reset_token(token)).first()
    if not user or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.utcnow():
        return jsonify({"error": "Token de recuperação inválido ou expirado."}), 400

    user.set_password(password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    db.session.commit()
    return jsonify({"message": "Senha redefinida com sucesso. Você já pode entrar."})


@auth_bp.post("/login")
def login():
    """
    Autentica um usuário existente.

    Body esperado:
      { "email": "enzo@exemplo.com", "password": "123456" }
    """
    print("\n" + "=" * 70)
    print("[Auth][login] INÍCIO da requisição POST /api/auth/login")

    data = request.get_json(silent=True) or {}
    print(f"[Auth][login] Body recebido (bruto, senha oculta): {{'email': {data.get('email')!r}}}")

    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    print(f"[Auth][login] Buscando usuário com email='{email}'...")
    user = User.query.filter_by(email=email).first()

    if not user:
        print(f"[Auth][login] FALHA (401): nenhum usuário encontrado com email='{email}'")
        print("=" * 70 + "\n")
        return jsonify({"error": "E-mail ou senha inválidos."}), 401

    print(f"[Auth][login] Usuário encontrado | user_id={user.id}. Validando senha...")
    senha_valida = user.check_password(password)
    print(f"[Auth][login] Resultado da validação de senha: {senha_valida}")

    if not senha_valida:
        print(f"[Auth][login] FALHA (401): senha incorreta para user_id={user.id}")
        print("=" * 70 + "\n")
        return jsonify({"error": "E-mail ou senha inválidos."}), 401

    print(f"[Auth][login] Credenciais válidas | user_id={user.id}. Gerando token...")
    token = generate_token(user.id)

    response_data = {
        "token": token,
        "user": user.to_dict(),
    }
    print(f"[Auth][login] Resposta final: {response_data}")
    print(f"[Auth][login] FIM (sucesso) | user_id={user.id}")
    print("=" * 70 + "\n")

    return jsonify(response_data)


@auth_bp.get("/me")
@login_required
def me():
    """
    Retorna os dados do usuário logado (usado para validar o token salvo
    no frontend quando a página é recarregada).
    """
    print(f"[Auth][me] INÍCIO | user_id={g.current_user.id}")
    data = g.current_user.to_dict()
    print(f"[Auth][me] Retornando dados do usuário: {data}")
    print(f"[Auth][me] FIM | user_id={g.current_user.id}")
    return jsonify(data)

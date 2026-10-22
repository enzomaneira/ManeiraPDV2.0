# =============================================================================
#  routes/auth.py  —  Cadastro, Login e dados do usuário logado
# =============================================================================
#
#  Fluxo:
#    POST /api/auth/register         → cria o usuário + a loja vinculada a ele
#    POST /api/auth/login            → valida email/senha e devolve um token JWT
#    GET  /api/auth/me               → retorna os dados do usuário logado (token)
#    PUT  /api/auth/me               → altera nome/e-mail do usuário logado
#    POST /api/auth/change-password  → troca a senha (exige a senha atual)
#
#  Senhas e tokens nunca são escritos nos logs.
# =============================================================================

import hashlib
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from flask import Blueprint, request, jsonify, g
from sqlalchemy.exc import IntegrityError

from database import db
from models import User, Store, StoreConfig
from auth_utils import generate_token, login_required, client_ip, rate_limited, reset_rate_limit

auth_bp = Blueprint("auth", __name__)

RESET_TOKEN_TTL_MINUTES = 30

NAME_MAX_LENGTH       = 120
STORE_NAME_MAX_LENGTH = 150
EMAIL_MAX_LENGTH      = 254
PASSWORD_MIN_LENGTH   = 6
PASSWORD_MAX_LENGTH   = 128

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TOO_MANY_ATTEMPTS = ({"error": "Muitas tentativas. Aguarde alguns minutos e tente novamente."}, 429)


def validate_name(value: str, label: str, max_length: int) -> str | None:
    """Devolve a mensagem de erro do campo, ou None se estiver ok."""
    if not value:
        return f"Preencha {label}."
    if len(value) > max_length:
        return f"{label[0].upper()}{label[1:]} deve ter no máximo {max_length} caracteres."
    return None


def validate_email(email: str) -> str | None:
    if not email:
        return "Preencha o e-mail."
    if len(email) > EMAIL_MAX_LENGTH or not EMAIL_PATTERN.match(email):
        return "Informe um e-mail válido."
    return None


def validate_password(password: str) -> str | None:
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"A senha deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"A senha deve ter no máximo {PASSWORD_MAX_LENGTH} caracteres."
    return None


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def _send_password_reset_email(email: str, reset_url: str):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "no-reply@maneirapdv.local")

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
    print("[Auth][register] INÍCIO")

    if rate_limited(f"register:{client_ip()}", limit=5, window_seconds=3600):
        print("[Auth][register] FALHA (429): limite de cadastros por IP.")
        return jsonify(TOO_MANY_ATTEMPTS[0]), TOO_MANY_ATTEMPTS[1]

    data = request.get_json(silent=True) or {}

    name       = str(data.get("name") or "").strip()
    email      = str(data.get("email") or "").strip().lower()
    password   = str(data.get("password") or "")
    store_name = str(data.get("storeName") or "").strip()

    error = (
        validate_name(name, "o seu nome", NAME_MAX_LENGTH)
        or validate_name(store_name, "o nome do restaurante", STORE_NAME_MAX_LENGTH)
        or validate_email(email)
        or validate_password(password)
    )
    if error:
        print(f"[Auth][register] FALHA (400): {error}")
        return jsonify({"error": error}), 400

    duplicate_email = {"error": "Já existe uma conta cadastrada com este e-mail."}
    if User.query.filter_by(email=email).first():
        print("[Auth][register] FALHA (409): e-mail já cadastrado.")
        return jsonify(duplicate_email), 409

    try:
        user = User(name=name, email=email, created_at=datetime.now().isoformat())
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # garante que user.id já existe, sem precisar commitar ainda

        store = Store(name=store_name, owner_id=user.id)
        db.session.add(store)
        db.session.flush()

        # Configuração padrão da loja (integração Keeta)
        db.session.add(StoreConfig(store_id=store.id, auto_accept=True, is_store_open=True))
        db.session.commit()
    except IntegrityError:
        # Dois cadastros simultâneos com o mesmo e-mail: o segundo cai aqui.
        db.session.rollback()
        print("[Auth][register] FALHA (409): e-mail cadastrado em paralelo.")
        return jsonify(duplicate_email), 409
    except Exception as e:
        db.session.rollback()
        print(f"[Auth][register] ERRO ao salvar no banco. Rollback executado: {type(e).__name__}: {e}")
        return jsonify({"error": "Erro interno ao criar a conta. Tente novamente."}), 500

    print(f"[Auth][register] FIM (sucesso) | user_id={user.id} | store_id={store.id}")
    return jsonify({"token": generate_token(user), "user": user.to_dict()}), 201


@auth_bp.post("/request-password-reset")
def request_password_reset():
    """Cria um token de uso único e envia o link de redefinição por e-mail."""
    data = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip().lower()
    generic_response = {
        "message": "Se existir uma conta com este e-mail, enviaremos instruções para redefinir a senha."
    }

    if not _smtp_configured():
        # Sem SMTP o e-mail nunca chegaria; avisamos em vez de fingir que enviou.
        print("[Auth][password-reset] SMTP_HOST não configurado; recuperação indisponível.")
        return jsonify({"error": "A recuperação de senha por e-mail está indisponível no momento. Fale com o suporte."}), 503

    if rate_limited(f"reset-ip:{client_ip()}", limit=10, window_seconds=3600) or (
        email and rate_limited(f"reset-email:{email}", limit=3, window_seconds=3600)
    ):
        return jsonify(TOO_MANY_ATTEMPTS[0]), TOO_MANY_ATTEMPTS[1]

    if not email:
        return jsonify(generic_response)

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(generic_response)

    raw_token = secrets.token_urlsafe(32)
    previous_hash, previous_expiry = user.reset_token_hash, user.reset_token_expires_at
    user.reset_token_hash = _hash_reset_token(raw_token)
    user.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    db.session.commit()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    reset_url = f"{frontend_url}/reset-password?token={raw_token}"

    try:
        _send_password_reset_email(email, reset_url)
    except Exception as error:
        # O token novo nunca chegou ao usuário: volta ao estado anterior.
        user.reset_token_hash, user.reset_token_expires_at = previous_hash, previous_expiry
        db.session.commit()
        print(f"[Auth][password-reset] Falha ao enviar e-mail: {type(error).__name__}: {error}")
        return jsonify({"error": "Não foi possível enviar o e-mail de recuperação."}), 500

    return jsonify(generic_response)


@auth_bp.post("/reset-password")
def reset_password():
    """Valida o token de recuperação e troca a senha, invalidando o token e as sessões abertas."""
    if rate_limited(f"reset-confirm:{client_ip()}", limit=20, window_seconds=3600):
        return jsonify(TOO_MANY_ATTEMPTS[0]), TOO_MANY_ATTEMPTS[1]

    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    password = str(data.get("password") or "")

    error = validate_password(password)
    if error:
        return jsonify({"error": error}), 400
    if not token:
        return jsonify({"error": "Token de recuperação inválido ou expirado."}), 400

    user = User.query.filter_by(reset_token_hash=_hash_reset_token(token)).first()
    if not user or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.utcnow():
        return jsonify({"error": "Token de recuperação inválido ou expirado."}), 400

    user.set_password(password)  # muda o hash → tokens JWT antigos deixam de valer
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    db.session.commit()
    reset_rate_limit(f"login:{user.email}")
    return jsonify({"message": "Senha redefinida com sucesso. Você já pode entrar."})


@auth_bp.post("/login")
def login():
    """
    Autentica um usuário existente.

    Body esperado:
      { "email": "enzo@exemplo.com", "password": "123456" }
    """
    data = request.get_json(silent=True) or {}
    email    = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    # Limite por conta (contra força bruta numa senha) e por IP (contra varredura).
    if rate_limited(f"login:{email}", limit=10, window_seconds=900) or rate_limited(
        f"login-ip:{client_ip()}", limit=50, window_seconds=900
    ):
        print("[Auth][login] FALHA (429): limite de tentativas atingido.")
        return jsonify(TOO_MANY_ATTEMPTS[0]), TOO_MANY_ATTEMPTS[1]

    user = User.query.filter_by(email=email).first() if email else None
    if not user or not user.check_password(password):
        print(f"[Auth][login] FALHA (401): credenciais inválidas | user_id={user.id if user else None}")
        return jsonify({"error": "E-mail ou senha inválidos."}), 401

    reset_rate_limit(f"login:{email}")
    print(f"[Auth][login] FIM (sucesso) | user_id={user.id}")
    return jsonify({"token": generate_token(user), "user": user.to_dict()})


@auth_bp.get("/me")
@login_required
def me():
    """
    Retorna os dados do usuário logado (usado para validar o token salvo
    no frontend quando a página é recarregada).
    """
    return jsonify(g.current_user.to_dict())


@auth_bp.put("/me")
@login_required
def update_me():
    """
    Altera nome e/ou e-mail do usuário logado.
    Trocar o e-mail exige a senha atual (campo currentPassword).
    """
    user = g.current_user
    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = str(data.get("name") or "").strip()
        error = validate_name(name, "o seu nome", NAME_MAX_LENGTH)
        if error:
            return jsonify({"error": error}), 400
        user.name = name

    if "email" in data:
        email = str(data.get("email") or "").strip().lower()
        if email != user.email:
            error = validate_email(email)
            if error:
                return jsonify({"error": error}), 400
            if not user.check_password(str(data.get("currentPassword") or "")):
                return jsonify({"error": "Senha atual incorreta."}), 403
            if User.query.filter(User.email == email, User.id != user.id).first():
                return jsonify({"error": "Já existe uma conta cadastrada com este e-mail."}), 409
            user.email = email

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Já existe uma conta cadastrada com este e-mail."}), 409

    print(f"[Auth][update_me] Dados atualizados | user_id={user.id}")
    return jsonify(user.to_dict())


@auth_bp.post("/change-password")
@login_required
def change_password():
    """
    Troca a senha do usuário logado. Todas as sessões antigas são encerradas;
    a resposta traz um token novo para a sessão atual continuar ativa.
    """
    user = g.current_user
    data = request.get_json(silent=True) or {}

    if rate_limited(f"change-password:{user.id}", limit=10, window_seconds=900):
        return jsonify(TOO_MANY_ATTEMPTS[0]), TOO_MANY_ATTEMPTS[1]

    if not user.check_password(str(data.get("currentPassword") or "")):
        return jsonify({"error": "Senha atual incorreta."}), 403

    new_password = str(data.get("newPassword") or "")
    error = validate_password(new_password)
    if error:
        return jsonify({"error": error}), 400

    user.set_password(new_password)
    db.session.commit()
    print(f"[Auth][change_password] Senha alterada | user_id={user.id}")
    return jsonify({"message": "Senha alterada com sucesso.", "token": generate_token(user), "user": user.to_dict()})

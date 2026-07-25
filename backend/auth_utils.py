# =============================================================================
#  auth_utils.py  —  Autenticação via JWT (JSON Web Token)
# =============================================================================
#
#  Como funciona o fluxo de login neste sistema:
#
#    1. O usuário faz POST /api/auth/login com email + senha
#    2. Se estiver correto, geramos um "token" (uma string assinada)
#       que prova quem é o usuário, sem precisar guardar sessão no servidor
#    3. O frontend guarda esse token (localStorage) e manda ele em toda
#       requisição, no header:  Authorization: Bearer <token>
#    4. O decorator @login_required lê esse header, valida o token e
#       descobre qual é o usuário logado (current_user)
#
#  Isso é o mesmo princípio usado por praticamente qualquer API moderna.
# =============================================================================

import os
import jwt
from functools import wraps
from datetime import datetime, timedelta, timezone
from flask import request, jsonify, g

# Chave secreta usada para assinar os tokens.
# Em produção, configure a variável de ambiente JWT_SECRET_KEY no Railway.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "maneira-pdv-chave-secreta-de-desenvolvimento")
JWT_ALGORITHM  = "HS256"
JWT_EXPIRES_HOURS = 24 * 7  # token válido por 7 dias


def generate_token(user_id: int) -> str:
    """
    Gera um token JWT contendo o ID do usuário e a data de expiração.
    """
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int | None:
    """
    Decodifica o token e retorna o ID do usuário (ou None se for inválido/expirado).
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        print("[Auth] Token expirado.")
        return None
    except jwt.InvalidTokenError:
        print("[Auth] Token inválido.")
        return None


def login_required(view_func):
    """
    Decorator que protege uma rota, exigindo um token JWT válido.

    Uso:
        @orders_bp.get("/")
        @login_required
        def minha_rota():
            usuario = g.current_user
            ...

    Se o token não vier ou for inválido, retorna 401 Unauthorized.
    Caso contrário, disponibiliza o usuário logado em `g.current_user`.
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        from models import User  # import tardio para evitar import circular

        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Token de autenticação ausente."}), 401

        token = auth_header.split(" ", 1)[1].strip()
        user_id = decode_token(token)

        if not user_id:
            return jsonify({"error": "Token inválido ou expirado."}), 401

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Usuário não encontrado."}), 401

        g.current_user = user
        return view_func(*args, **kwargs)

    return wrapper

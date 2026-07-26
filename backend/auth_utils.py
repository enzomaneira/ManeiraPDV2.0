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

print(f"[Auth][INIT] Módulo auth_utils carregado | algorithm={JWT_ALGORITHM} | expires_hours={JWT_EXPIRES_HOURS} | secret_configurado={'sim (via env)' if os.getenv('JWT_SECRET_KEY') else 'NÃO (usando valor padrão de desenvolvimento!)'}")


def generate_token(user_id: int) -> str:
    """
    Gera um token JWT contendo o ID do usuário e a data de expiração.
    """
    print(f"[Auth][generate_token] INÍCIO | user_id={user_id}")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=JWT_EXPIRES_HOURS)

    payload = {
        "sub": user_id,
        "exp": expires_at,
        "iat": now,
    }
    print(f"[Auth][generate_token] payload montado: {payload}")

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    print(f"[Auth][generate_token] Token gerado com sucesso | user_id={user_id} | expira_em={expires_at.isoformat()} | token_preview={token[:20]}...")
    print(f"[Auth][generate_token] FIM | user_id={user_id}")
    return token


def decode_token(token: str) -> int | None:
    """
    Decodifica o token e retorna o ID do usuário (ou None se for inválido/expirado).
    """
    print(f"[Auth][decode_token] INÍCIO | token_preview={token[:20] if token else None}...")

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        print(f"[Auth][decode_token] Token válido | user_id={user_id} | payload={payload}")
        print(f"[Auth][decode_token] FIM (sucesso) | user_id={user_id}")
        return user_id
    except jwt.ExpiredSignatureError as e:
        print(f"[Auth][decode_token] ERRO: Token expirado. Detalhes: {e}")
        print("[Auth][decode_token] FIM (falha - expirado)")
        return None
    except jwt.InvalidTokenError as e:
        print(f"[Auth][decode_token] ERRO: Token inválido. Detalhes: {e}")
        print("[Auth][decode_token] FIM (falha - inválido)")
        return None
    except Exception as e:
        print(f"[Auth][decode_token] ERRO INESPERADO ao decodificar token: {e}")
        print("[Auth][decode_token] FIM (falha - erro inesperado)")
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

        print(f"[Auth][login_required] INÍCIO | rota={request.path} | method={request.method}")

        auth_header = request.headers.get("Authorization", "")
        print(f"[Auth][login_required] Header Authorization presente: {bool(auth_header)}")

        if not auth_header.startswith("Bearer "):
            print(f"[Auth][login_required] REJEITADO (401): header ausente ou malformado. Header recebido='{auth_header[:30]}'")
            return jsonify({"error": "Token de autenticação ausente."}), 401

        token = auth_header.split(" ", 1)[1].strip()
        print(f"[Auth][login_required] Token extraído do header | preview={token[:20]}...")

        user_id = decode_token(token)

        if not user_id:
            print(f"[Auth][login_required] REJEITADO (401): token inválido/expirado | rota={request.path}")
            return jsonify({"error": "Token inválido ou expirado."}), 401

        print(f"[Auth][login_required] Buscando usuário no banco | user_id={user_id}")
        user = User.query.get(user_id)

        if not user:
            print(f"[Auth][login_required] REJEITADO (401): usuário não encontrado no banco | user_id={user_id}")
            return jsonify({"error": "Usuário não encontrado."}), 401

        print(f"[Auth][login_required] Usuário autenticado com sucesso | user_id={user.id} | email={user.email} | store_id={user.store.id if user.store else None}")
        g.current_user = user

        print(f"[Auth][login_required] FIM (autorizado) | rota={request.path} | executando view '{view_func.__name__}'")
        return view_func(*args, **kwargs)

    return wrapper

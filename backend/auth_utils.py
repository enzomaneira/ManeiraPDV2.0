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

import hashlib
import os
import threading
import time
import jwt
from functools import wraps
from datetime import datetime, timedelta, timezone
from flask import request, jsonify, g

# Chave secreta usada para assinar os tokens. É OBRIGATÓRIA: o repositório é
# público, então qualquer valor padrão escrito aqui permitiria forjar tokens.
# Só em desenvolvimento local (DEBUG=true) aceitamos subir sem ela.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
if not JWT_SECRET_KEY:
    if os.getenv("DEBUG", "false").lower() == "true":
        JWT_SECRET_KEY = "dev-only-" + os.urandom(16).hex()
        print("[Auth][INIT] AVISO: JWT_SECRET_KEY ausente; usando segredo aleatório de desenvolvimento.")
    else:
        raise RuntimeError("JWT_SECRET_KEY não configurada. Defina a variável de ambiente antes de subir o backend.")
if len(JWT_SECRET_KEY) < 32:
    print("[Auth][INIT] AVISO: JWT_SECRET_KEY curta; use pelo menos 32 caracteres aleatórios.")

JWT_ALGORITHM  = "HS256"
JWT_EXPIRES_HOURS = 24 * 7  # token válido por 7 dias

print(f"[Auth][INIT] Módulo auth_utils carregado | algorithm={JWT_ALGORITHM} | expires_hours={JWT_EXPIRES_HOURS}")


def password_version(password_hash: str) -> str:
    """
    Impressão digital curta do hash da senha, gravada no token (claim "pv").
    Quando a senha muda, o hash muda e todos os tokens antigos deixam de valer.
    """
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


def generate_token(user) -> str:
    """
    Gera um token JWT contendo o ID do usuário, a versão da senha e a expiração.
    """
    print(f"[Auth][generate_token] INÍCIO | user_id={user.id}")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=JWT_EXPIRES_HOURS)

    payload = {
        "sub": str(user.id),
        "pv":  password_version(user.password_hash),
        "exp": expires_at,
        "iat": now,
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    print(f"[Auth][generate_token] FIM | user_id={user.id} | expira_em={expires_at.isoformat()}")
    return token


def decode_token(token: str) -> dict | None:
    """
    Decodifica o token e retorna o payload (ou None se for inválido/expirado).
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        int(payload.get("sub"))
        return payload
    except jwt.ExpiredSignatureError:
        print("[Auth][decode_token] Token expirado.")
        return None
    except jwt.InvalidTokenError as e:
        print(f"[Auth][decode_token] Token inválido: {type(e).__name__}")
        return None
    except Exception as e:
        print(f"[Auth][decode_token] ERRO INESPERADO ao decodificar token: {type(e).__name__}")
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

    Se o token não vier, for inválido, ou tiver sido emitido antes da última
    troca de senha, retorna 401. Caso contrário, disponibiliza o usuário
    logado em `g.current_user`.
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        from models import User  # import tardio para evitar import circular

        print(f"[Auth][login_required] INÍCIO | rota={request.path} | method={request.method}")

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            print("[Auth][login_required] REJEITADO (401): header ausente ou malformado.")
            return jsonify({"error": "Token de autenticação ausente."}), 401

        payload = decode_token(auth_header.split(" ", 1)[1].strip())
        if not payload:
            print(f"[Auth][login_required] REJEITADO (401): token inválido/expirado | rota={request.path}")
            return jsonify({"error": "Token inválido ou expirado."}), 401

        user_id = int(payload["sub"])
        user = User.query.get(user_id)
        if not user:
            print(f"[Auth][login_required] REJEITADO (401): usuário não encontrado no banco | user_id={user_id}")
            return jsonify({"error": "Usuário não encontrado."}), 401

        if payload.get("pv") != password_version(user.password_hash):
            print(f"[Auth][login_required] REJEITADO (401): token anterior à última troca de senha | user_id={user_id}")
            return jsonify({"error": "Sessão expirada. Entre novamente."}), 401

        print(f"[Auth][login_required] Autorizado | user_id={user.id} | store_id={user.store.id if user.store else None}")
        g.current_user = user
        return view_func(*args, **kwargs)

    return wrapper


# -----------------------------------------------------------------------------
#  Limite de tentativas (login, cadastro, recuperação de senha)
# -----------------------------------------------------------------------------
#  Contador em memória por processo. Com 2 workers do gunicorn o limite real
#  fica no máximo 2x o configurado, o que já basta contra força bruta.

_rate_buckets: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def client_ip() -> str:
    """IP do cliente atrás do proxy do Railway (primeiro item do X-Forwarded-For)."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "unknown"


def rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    """Registra uma tentativa para `key` e diz se o limite da janela foi estourado."""
    now = time.time()
    with _rate_lock:
        attempts = [t for t in _rate_buckets.get(key, []) if now - t < window_seconds]
        attempts.append(now)
        _rate_buckets[key] = attempts
        if len(_rate_buckets) > 10000:
            for stale in [k for k, v in _rate_buckets.items() if now - v[-1] > 3600]:
                _rate_buckets.pop(stale, None)
        return len(attempts) > limit


def reset_rate_limit(key: str):
    with _rate_lock:
        _rate_buckets.pop(key, None)

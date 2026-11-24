"""
Login com Google ("Entrar com Google", Google Identity Services).

O frontend mostra o botão do Google e recebe um ID token (JWT assinado pelo
Google). O backend confere esse token no endpoint tokeninfo do Google:
  - aud  = nosso GOOGLE_CLIENT_ID (o token foi emitido para este app)
  - iss  = accounts.google.com
  - exp  ainda válido
  - email_verified = true
Só o Client ID (público) é necessário; o client secret não é usado.
"""
import os
import time

import jwt
import requests

from auth_utils import JWT_ALGORITHM, JWT_SECRET_KEY

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_PLACEHOLDERS = {"", "COLE_AQUI"}
SIGNUP_TOKEN_MINUTES = 15


def client_id() -> str | None:
    value = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    return None if value in _PLACEHOLDERS else value


def verify_id_token(credential: str) -> tuple[dict | None, str | None]:
    """Devolve ({sub, email, name, picture}, None) ou (None, motivo)."""
    cid = client_id()
    if not cid:
        return None, "O login com Google ainda não está configurado no servidor."
    if not isinstance(credential, str) or len(credential) < 20 or len(credential) > 5000:
        return None, "Resposta do Google inválida. Tente de novo."
    try:
        response = requests.get(TOKENINFO_URL, params={"id_token": credential}, timeout=(5, 10))
    except requests.RequestException as e:
        print(f"[Google][verify] ERRO de rede: {type(e).__name__}")
        return None, "Não foi possível falar com o Google agora. Tente de novo."
    if response.status_code != 200:
        print(f"[Google][verify] token recusado | status_code={response.status_code}")
        return None, "O Google não confirmou o login. Tente de novo."
    data = response.json() if response.content else {}
    try:
        expired = int(data.get("exp", 0)) < time.time()
    except (TypeError, ValueError):
        expired = True
    if data.get("aud") != cid or data.get("iss") not in VALID_ISSUERS or expired or not data.get("sub"):
        print(f"[Google][verify] token não é deste app ou expirou | aud_ok={data.get('aud') == cid} | iss={data.get('iss')} | expirado={expired}")
        return None, "O login do Google não é válido para o ManeiraPDV."
    if str(data.get("email_verified")).lower() != "true" or not data.get("email"):
        return None, "O e-mail desta conta Google não está verificado."
    return {
        "sub": str(data["sub"]),
        "email": str(data["email"]).strip().lower(),
        "name": (data.get("name") or "").strip(),
        "picture": data.get("picture"),
    }, None


def make_signup_token(info: dict) -> str:
    """Token curto para terminar o cadastro (falta o nome do restaurante) sem
    pedir o login do Google de novo."""
    payload = {"typ": "google-signup", "sub": info["sub"], "email": info["email"], "name": info.get("name") or "",
               "exp": int(time.time()) + SIGNUP_TOKEN_MINUTES * 60}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def read_signup_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "google-signup" and payload.get("sub") and payload.get("email") else None

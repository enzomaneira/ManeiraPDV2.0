# =============================================================================
#  ifood_client.py  —  Comunicação com a API do iFood (Merchant API)
# =============================================================================
#
#  App CENTRALIZADO: uma credencial (client_credentials) acessa todas as lojas
#  que autorizaram o app. Credenciais nas variáveis IFOOD_CLIENT_ID e
#  IFOOD_CLIENT_SECRET (nunca no código: o repositório é público).
#
#  Base: https://merchant-api.ifood.com.br
#    Token .......... POST /authentication/v1.0/oauth/token (form: grantType, clientId, clientSecret)
#    Eventos ........ GET  /order/v1.0/events:polling   + POST /order/v1.0/events/acknowledgment
#    Pedido ......... GET  /order/v1.0/orders/{id}
#    Ações .......... POST /order/v1.0/orders/{id}/confirm | startPreparation | readyToPickup
#                     | dispatch | requestCancellation   (respondem 202)
#    Motivos ........ GET  /order/v1.0/orders/{id}/cancellationReasons
#    Loja ........... GET  /merchant/v1.0/merchants/{id} e /merchants/{id}/status
#    Webhook ........ header X-IFood-Signature = HMAC-SHA256(client_secret, corpo bruto) em hex
#
#  Nunca registrar nos logs dados do cliente (telefone, endereço) nem tokens.
# =============================================================================

import hashlib
import hmac
import os
import threading
import time

import requests

BASE_URL = os.getenv("IFOOD_BASE_URL", "https://merchant-api.ifood.com.br").rstrip("/")
REQUEST_TIMEOUT = (5, 15)
_PLACEHOLDERS = {"", "COLE_AQUI"}

_token_lock = threading.Lock()
_token_cache = {"value": None, "expires_at": 0.0}


def _credentials() -> tuple[str, str]:
    return os.getenv("IFOOD_CLIENT_ID", "").strip(), os.getenv("IFOOD_CLIENT_SECRET", "").strip()


def is_configured() -> bool:
    client_id, client_secret = _credentials()
    return client_id not in _PLACEHOLDERS and client_secret not in _PLACEHOLDERS


def get_access_token(force: bool = False) -> str | None:
    """Token do app (vale ~6h). Reaproveita até 5 min antes de expirar."""
    if not is_configured():
        return None
    with _token_lock:
        if not force and _token_cache["value"] and time.time() < _token_cache["expires_at"] - 300:
            return _token_cache["value"]
        client_id, client_secret = _credentials()
        try:
            response = requests.post(
                f"{BASE_URL}/authentication/v1.0/oauth/token",
                data={"grantType": "client_credentials", "clientId": client_id, "clientSecret": client_secret},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as e:
            print(f"[iFood][token] ERRO de rede: {type(e).__name__}")
            return None
        if response.status_code != 200:
            print(f"[iFood][token] FALHA | status_code={response.status_code} | body={response.text[:200]}")
            return None
        data = response.json()
        token = data.get("accessToken")
        if not token:
            print("[iFood][token] FALHA | resposta sem accessToken")
            return None
        _token_cache["value"] = token
        _token_cache["expires_at"] = time.time() + int(data.get("expiresIn") or 21600)
        print(f"[iFood][token] OK | expira em {int(data.get('expiresIn') or 21600)}s")
        return token


def _request(method: str, path: str, *, json_body=None, headers=None, retry_auth=True):
    """Chamada autenticada. Retorna (status_code, json|None) ou (None, None) em erro de rede."""
    token = get_access_token()
    if not token:
        return None, None
    all_headers = {"Authorization": f"Bearer {token}", **(headers or {})}
    try:
        response = requests.request(method, f"{BASE_URL}{path}", json=json_body, headers=all_headers, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        print(f"[iFood][{method} {path.split('?')[0]}] ERRO de rede: {type(e).__name__}")
        return None, None
    if response.status_code == 401 and retry_auth:
        get_access_token(force=True)
        return _request(method, path, json_body=json_body, headers=headers, retry_auth=False)
    try:
        body = response.json() if response.content else None
    except ValueError:
        body = None
    return response.status_code, body


# --- Webhook ----------------------------------------------------------------

def validate_webhook_signature(raw_body: bytes, received: str | None) -> bool:
    """X-IFood-Signature = HMAC-SHA256 do corpo bruto com o client_secret, em hex."""
    _, client_secret = _credentials()
    if client_secret in _PLACEHOLDERS or not received:
        return False
    expected = hmac.new(client_secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.lower(), received.strip().lower())


# --- Eventos (polling) ------------------------------------------------------

def poll_events(merchant_ids: list[str] | None = None) -> list[dict]:
    """Eventos pendentes. Sem eventos a API responde 204 (lista vazia)."""
    headers = {}
    if merchant_ids:
        headers["x-polling-merchants"] = ",".join(merchant_ids)
    status, body = _request("GET", "/order/v1.0/events:polling", headers=headers)
    if status == 200 and isinstance(body, list):
        return body
    if status not in (200, 204, None):
        print(f"[iFood][polling] status_code={status}")
    return []


def acknowledge_events(event_ids: list[str]) -> bool:
    if not event_ids:
        return True
    status, _ = _request("POST", "/order/v1.0/events/acknowledgment", json_body=[{"id": i} for i in event_ids])
    ok = status in (200, 202, 204)
    if not ok:
        print(f"[iFood][acknowledgment] FALHA | status_code={status} | eventos={len(event_ids)}")
    return ok


# --- Pedidos ----------------------------------------------------------------

def get_order(order_id: str) -> dict | None:
    status, body = _request("GET", f"/order/v1.0/orders/{order_id}")
    if status == 200 and isinstance(body, dict):
        return body
    print(f"[iFood][order] order_id={order_id} | status_code={status}")
    return None


def _order_action(order_id: str, action: str, json_body=None) -> tuple[bool, int | None]:
    status, body = _request("POST", f"/order/v1.0/orders/{order_id}/{action}", json_body=json_body)
    ok = status in (200, 202, 204)
    print(f"[iFood][{action}] order_id={order_id} | status_code={status} | sucesso={ok}"
          + ("" if ok else f" | body={str(body)[:200]}"))
    return ok, status


def confirm_order(order_id): return _order_action(order_id, "confirm")
def start_preparation(order_id): return _order_action(order_id, "startPreparation")
def ready_to_pickup(order_id): return _order_action(order_id, "readyToPickup")
def dispatch_order(order_id): return _order_action(order_id, "dispatch")


def cancellation_reasons(order_id: str) -> list[dict]:
    status, body = _request("GET", f"/order/v1.0/orders/{order_id}/cancellationReasons")
    return body if status == 200 and isinstance(body, list) else []


def request_cancellation(order_id: str, preferred_code: str | None = None) -> tuple[bool, int | None]:
    """Pede o cancelamento usando um motivo aceito pelo iFood para este pedido."""
    reasons = cancellation_reasons(order_id)
    reason = next((r for r in reasons if str(r.get("cancelCodeId")) == str(preferred_code)), None) or (reasons[0] if reasons else None)
    if not reason:
        print(f"[iFood][requestCancellation] order_id={order_id} | sem motivos de cancelamento disponíveis")
        return False, None
    return _order_action(order_id, "requestCancellation",
                         {"reason": reason.get("description") or "Cancelado pelo restaurante",
                          "cancellationCode": str(reason.get("cancelCodeId"))})


# --- Loja -------------------------------------------------------------------

def get_merchant(merchant_id: str) -> dict | None:
    """Confere se o app tem acesso à loja (usado ao vincular a loja no PDV)."""
    status, body = _request("GET", f"/merchant/v1.0/merchants/{merchant_id}")
    if status == 200 and isinstance(body, dict):
        return body
    print(f"[iFood][merchant] merchant_id={merchant_id} | status_code={status}")
    return None


def list_merchants() -> list[dict]:
    status, body = _request("GET", "/merchant/v1.0/merchants")
    return body if status == 200 and isinstance(body, list) else []

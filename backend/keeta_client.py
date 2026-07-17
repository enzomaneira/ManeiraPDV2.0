# =============================================================================
#  keeta_client.py  —  Integração com a Keeta Open Delivery API
# =============================================================================
#
#  Este arquivo centraliza TODA a comunicação com a Keeta.
#  Cada função representa uma chamada de API diferente.
#
#  Fluxo geral:
#    1. get_access_token()     →  autentica e obtém o Bearer Token
#    2. _generate_signature()  →  assina cada requisição com HMAC-SHA256
#    3. Funções de pedido      →  confirm, ready, dispatch, cancel
#    4. Funções de loja        →  onboarding, status, auth URL
# =============================================================================

import hmac
import hashlib
import base64
import time
import requests
import json
import os
from datetime import datetime

# -----------------------------------------------------------------------------
#  CREDENCIAIS (em produção, use variáveis de ambiente)
# -----------------------------------------------------------------------------
CLIENT_ID     = "2816859805"
CLIENT_SECRET = "2f6729bdd4be467aa15df35244f2a65e"

# Base da API da Keeta
BASE_URL = "https://open.mykeeta.com/api/open/opendelivery"

# URL pública do backend — usada no onboarding para informar à Keeta:
#   - onde fazer POST dos eventos de pedido (webhook)
#   - onde fazer GET do cardápio (menu endpoint)
#
# No Railway: configure a variável MY_PUBLIC_URL com a URL gerada pelo Railway
#   Ex: https://maneira-backend-production.up.railway.app/api/keeta
#
# Localmente com ngrok: coloque a URL do ngrok aqui ou na variável de ambiente.
MY_PUBLIC_URL = os.getenv("MY_PUBLIC_URL", "https://nonimperialistically-lexicostatistical-jaelyn.ngrok-free.dev/api/keeta")

# -----------------------------------------------------------------------------
#  CACHE DO TOKEN
#  A Keeta gera tokens com validade de ~5h. Guardamos em memória para não
#  ficar fazendo login a cada requisição.
# -----------------------------------------------------------------------------
_cached_token = None
_token_expires_at = 0  # timestamp UNIX de quando o token expira


# =============================================================================
#  1. AUTENTICAÇÃO
# =============================================================================

def get_access_token() -> str | None:
    """
    Obtém um App-Level Access Token da Keeta.

    Como funciona:
      - Faz POST /oauth/token com client_id, client_secret e grant_type
      - Retorna um Bearer Token que deve ser enviado no header de toda requisição
      - O token é cacheado por 4 horas para evitar chamadas desnecessárias

    Documentação: https://api-docs.mykeeta.com/apis/opendelivery/authentication
    """
    global _cached_token, _token_expires_at

    # Se o token ainda é válido, retorna o que está em cache
    if _cached_token and time.time() < _token_expires_at:
        print("[Keeta] Usando token cacheado.")
        return _cached_token

    print("[Keeta] Solicitando novo Access Token...")

    url = f"{BASE_URL}/oauth/token"

    # O body da requisição de autenticação
    payload = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "app_level_token",  # Modo App-Level (software level)
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        _cached_token = data["access_token"]
        _token_expires_at = time.time() + (4 * 60 * 60)  # expira em 4 horas

        print(f"[Keeta] Novo token obtido: {_cached_token[:20]}...")
        return _cached_token

    except Exception as e:
        print(f"[Keeta] ERRO ao obter token: {e}")
        return None


# =============================================================================
#  2. ASSINATURA (X-App-Signature)
# =============================================================================

def _generate_signature(url: str, query_params: dict = None, body: str = None) -> str:
    """
    Gera a assinatura HMAC-SHA256 que a Keeta exige em toda requisição.

    Como funciona:
      A Keeta monta uma string assim:
        <url> + "&" + <chave>=<valor> (params ordenados) + "&" + <body JSON>
      Depois assina essa string com o CLIENT_SECRET usando HMAC-SHA256
      e codifica o resultado em Base64.

    Essa assinatura vai no header: X-App-Signature

    Documentação: https://api-docs.mykeeta.com/apis/opendelivery/signature-calculation
    """
    # Monta a string que vai ser assinada
    parts = [url]

    if query_params:
        # Parâmetros de query DEVEM ser ordenados alfabeticamente
        for key in sorted(query_params.keys()):
            parts.append(f"{key}={query_params[key]}")

    if body and body.strip() not in ("", "{}"):
        parts.append(body)

    string_to_sign = "&".join(parts)

    # Calcula o HMAC-SHA256
    signature_bytes = hmac.new(
        key=CLIENT_SECRET.encode("utf-8"),
        msg=string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    # Codifica em Base64 e retorna como string
    return base64.b64encode(signature_bytes).decode("utf-8")


def _build_headers(url: str, query_params: dict = None, body: str = None) -> dict:
    """
    Monta o dicionário de headers padrão para qualquer chamada à Keeta.
    Inclui: Authorization (Bearer Token) + Content-Type + X-App-Signature
    """
    token = get_access_token()
    signature = _generate_signature(url, query_params, body)

    return {
        "Authorization":   f"Bearer {token}",
        "Content-Type":    "application/json; charset=utf-8",
        "X-App-Signature": signature,
    }


# =============================================================================
#  3. CHAMADAS DE PEDIDO (Order API)
# =============================================================================

def confirm_order(order_id: str) -> bool:
    """
    Confirma (aceita) um pedido na Keeta.

    Quando usar: quando o restaurante aceita o pedido do cliente.
    O pedido muda de estado: PLACED → CONFIRMED

    Endpoint: POST /v1/orders/{orderId}/confirm
    """
    url = f"{BASE_URL}/v1/orders/{order_id}/confirm"
    body = "{}"

    print(f"[Keeta] Confirmando pedido {order_id}...")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        print(f"[Keeta] Pedido {order_id} confirmado! Status HTTP: {response.status_code}")
        return response.status_code in (200, 201, 204)
    except Exception as e:
        print(f"[Keeta] ERRO ao confirmar pedido: {e}")
        return False


def notify_ready_for_pickup(order_id: str) -> bool:
    """
    Informa a Keeta que o pedido está pronto para retirada.

    Quando usar: quando a cozinha terminou de preparar o pedido.
    O pedido muda de estado: CONFIRMED → READY_FOR_PICKUP

    Endpoint: POST /v1/orders/{orderId}/readyForPickup
    """
    url = f"{BASE_URL}/v1/orders/{order_id}/readyForPickup"
    body = "{}"

    print(f"[Keeta] Pedido {order_id} marcado como PRONTO...")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        return response.status_code in (200, 201, 204)
    except Exception as e:
        print(f"[Keeta] ERRO ao marcar pronto: {e}")
        return False


def notify_dispatched(order_id: str) -> bool:
    """
    Informa a Keeta que o pedido saiu para entrega (despacho do motoboy).

    Quando usar: quando o entregador saiu com o pedido.
    O pedido muda de estado: READY_FOR_PICKUP → DISPATCHED

    Endpoint: POST /v1/orders/{orderId}/dispatch
    """
    url = f"{BASE_URL}/v1/orders/{order_id}/dispatch"
    body = "{}"

    print(f"[Keeta] Pedido {order_id} despachado (saiu para entrega)...")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        return response.status_code in (200, 201, 204)
    except Exception as e:
        print(f"[Keeta] ERRO ao despachar: {e}")
        return False


def request_cancellation(order_id: str, reason: str = "Dificuldades internas do restaurante") -> bool:
    """
    Solicita o cancelamento de um pedido na Keeta.

    Quando usar: quando o restaurante não consegue atender o pedido.

    Códigos válidos (code):
      SYSTEMIC_ISSUES, UNAVAILABLE_ITEM, OUTDATED_MENU,
      INTERNAL_DIFFICULTIES_OF_THE_RESTAURANT, etc.

    Endpoint: POST /v1/orders/{orderId}/requestCancellation
    """
    url = f"{BASE_URL}/v1/orders/{order_id}/requestCancellation"

    payload = {
        "reason": reason,
        "code":   "INTERNAL_DIFFICULTIES_OF_THE_RESTAURANT",
        "mode":   "MANUAL",
    }
    body = json.dumps(payload)

    print(f"[Keeta] Solicitando cancelamento do pedido {order_id}...")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        return response.status_code in (200, 201, 204)
    except Exception as e:
        print(f"[Keeta] ERRO ao cancelar: {e}")
        return False


def get_order_details(order_id: str) -> dict | None:
    """
    Busca os detalhes completos de um pedido na Keeta.

    Retorna um dicionário com todos os dados do pedido:
    itens, cliente, endereço, valores, pagamento, etc.

    Endpoint: GET /v1/orders/{orderId}
    """
    url = f"{BASE_URL}/v1/orders/{order_id}"

    print(f"[Keeta] Buscando detalhes do pedido {order_id}...")
    try:
        response = requests.get(url, headers=_build_headers(url))
        response.raise_for_status()

        order_data = response.json()
        _save_log(f"ORDER_{order_id}", order_data)  # salva o JSON bruto para debug
        return order_data

    except Exception as e:
        print(f"[Keeta] ERRO ao buscar pedido: {e}")
        return None


# =============================================================================
#  4. CHAMADAS DE LOJA (Merchant API)
# =============================================================================

def register_merchant(keeta_merchant_id: str, my_local_store_id: str) -> dict | None:
    """
    Faz o Onboarding da loja na Keeta.

    O que faz:
      - Registra o mapeamento entre o ID da loja local e o ID da Keeta
      - Informa a URL do webhook onde a Keeta vai enviar eventos de pedido
      - Informa a URL do endpoint GET /merchant (onde a Keeta busca o cardápio)

    Quando usar: uma única vez ao conectar uma loja nova.

    Endpoint: PUT /v1/merchantOnboarding?merchantId={meuId}
    """
    url = f"{BASE_URL}/v1/merchantOnboarding"
    query_params = {"merchantId": my_local_store_id}

    payload = {
        "getMerchantURL": {
            "baseURL": f"{MY_PUBLIC_URL}/menu",  # Keeta vai fazer GET aqui para buscar o cardápio
            "apiKey":  "123456",
        },
        "ordersWebhookURL": f"{MY_PUBLIC_URL}/orders",  # Keeta vai fazer POST aqui para enviar eventos
        "keetaMerchantId": keeta_merchant_id,
    }
    body = json.dumps(payload)

    full_url_with_params = f"{url}?merchantId={my_local_store_id}"

    print(f"[Keeta] Registrando loja {keeta_merchant_id} (local ID: {my_local_store_id})...")
    try:
        response = requests.put(
            full_url_with_params,
            headers=_build_headers(url, query_params=query_params, body=body),
            data=body,
        )
        print(f"[Keeta] Onboarding concluído! Resposta: {response.text}")
        return response.json()
    except Exception as e:
        print(f"[Keeta] ERRO no onboarding: {e}")
        return None


def update_store_status(keeta_merchant_id: str, is_open: bool) -> bool:
    """
    Abre ou fecha a loja na plataforma Keeta.

    Quando usar: no início/fim do expediente, ou quando a loja fica sem
    capacidade de atender (ex: sem entregador).

    Endpoint: POST /v1/merchantUpdate/{merchantId}
    """
    url = f"{BASE_URL}/v1/merchantUpdate/{keeta_merchant_id}"
    status = "AVAILABLE" if is_open else "UNAVAILABLE"

    payload = {"merchantStatus": status}
    body = json.dumps(payload)

    print(f"[Keeta] Atualizando status da loja para: {status}...")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        print(f"[Keeta] Status atualizado! HTTP {response.status_code}")
        return response.status_code in (200, 201, 204)
    except Exception as e:
        print(f"[Keeta] ERRO ao atualizar status: {e}")
        return False


def get_authorization_url(redirect_uri: str) -> str | None:
    """
    Gera a URL de autorização para que um comerciante autorize seu sistema.

    Fluxo OAuth:
      1. Você chama esta função → recebe uma URL
      2. O comerciante abre essa URL no navegador e faz login na Keeta
      3. Após autorizar, a Keeta redireciona para o `redirect_uri` com um `authId`
      4. Você usa o `authId` para buscar os dados da loja e fazer o onboarding

    Endpoint: GET /oauth/authorization/url
    """
    url = f"{BASE_URL}/oauth/authorization/url"
    params = {
        "clientId":    CLIENT_ID,
        "redirectUri": redirect_uri,
    }

    print(f"[Keeta] Gerando URL de autorização para: {redirect_uri}")
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        # A resposta pode ser string pura ou JSON com a URL
        try:
            data = response.json()
            return data.get("merchantAuthorizationUrl") or data.get("url") or str(data)
        except Exception:
            return response.text
    except Exception as e:
        print(f"[Keeta] ERRO ao gerar URL de auth: {e}")
        return None


def get_merchant_info(auth_id: str) -> dict | None:
    """
    Busca as informações da loja após o comerciante autorizar seu sistema.

    Quando usar: logo após receber o `authId` no callback OAuth.
    Retorna a lista de lojas autorizadas com os IDs da Keeta.

    Endpoint: GET /oauth/authorized/{authId}/merchantInfo
    """
    url = f"{BASE_URL}/oauth/authorized/{auth_id}/merchantInfo"
    query_params = {"pageNum": "1", "pageSize": "10"}

    full_url = f"{url}?pageNum=1&pageSize=10"

    print(f"[Keeta] Buscando info da loja com authId: {auth_id}...")
    try:
        response = requests.get(
            full_url,
            headers=_build_headers(url, query_params=query_params),
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[Keeta] ERRO ao buscar merchant info: {e}")
        return None


# =============================================================================
#  5. VALIDAÇÃO DO WEBHOOK
# =============================================================================

def validate_webhook_signature(body: str, received_signature: str) -> bool:
    """
    Valida se um webhook recebido realmente veio da Keeta.

    A Keeta assina o body do webhook com o CLIENT_SECRET.
    Recalculamos a assinatura e comparamos com o header X-App-Signature.

    Retorna True se a assinatura é válida (é da Keeta), False caso contrário.
    """
    expected_signature = hmac.new(
        key=CLIENT_SECRET.encode("utf-8"),
        msg=body.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    expected_b64 = base64.b64encode(expected_signature).decode("utf-8")
    return hmac.compare_digest(expected_b64, received_signature)


# =============================================================================
#  6. UTILITÁRIOS
# =============================================================================

def _save_log(prefix: str, data: dict):
    """
    Salva um JSON em disco para facilitar o debug durante o desenvolvimento.
    Os arquivos ficam na pasta `keeta_logs/`.
    """
    os.makedirs("keeta_logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"keeta_logs/{timestamp}_{prefix}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[Keeta] Log salvo em: {filename}")

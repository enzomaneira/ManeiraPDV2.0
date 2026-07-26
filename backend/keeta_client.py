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

print(f"[Keeta][INIT] Módulo keeta_client carregado | BASE_URL={BASE_URL} | MY_PUBLIC_URL={MY_PUBLIC_URL} | CLIENT_ID={CLIENT_ID}")

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

    print(f"[Keeta][get_access_token] INÍCIO | token_em_cache={bool(_cached_token)} | expira_em={_token_expires_at} | agora={time.time()}")

    # Se o token ainda é válido, retorna o que está em cache
    if _cached_token and time.time() < _token_expires_at:
        print(f"[Keeta][get_access_token] Usando token cacheado | preview={_cached_token[:20]}... | válido por mais {_token_expires_at - time.time():.0f}s")
        return _cached_token

    print("[Keeta][get_access_token] Token expirado ou inexistente. Solicitando novo Access Token...")

    url = f"{BASE_URL}/oauth/token"

    # O body da requisição de autenticação
    payload = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "app_level_token",  # Modo App-Level (software level)
    }
    print(f"[Keeta][get_access_token] POST {url} | payload (secret oculto): {{'client_id': '{CLIENT_ID}', 'grant_type': 'app_level_token'}}")

    try:
        response = requests.post(url, json=payload)
        print(f"[Keeta][get_access_token] Resposta recebida | status_code={response.status_code}")
        response.raise_for_status()

        data = response.json()
        _cached_token = data["access_token"]
        _token_expires_at = time.time() + (4 * 60 * 60)  # expira em 4 horas

        print(f"[Keeta][get_access_token] Novo token obtido com sucesso | preview={_cached_token[:20]}... | expira_em(unix)={_token_expires_at}")
        print("[Keeta][get_access_token] FIM (sucesso)")
        return _cached_token

    except Exception as e:
        print(f"[Keeta][get_access_token] ERRO ao obter token: {type(e).__name__}: {e}")
        print("[Keeta][get_access_token] FIM (falha)")
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
    print(f"[Keeta][_generate_signature] INÍCIO | url={url} | query_params={query_params} | body_preview={(body or '')[:100]}")

    # Monta a string que vai ser assinada
    parts = [url]

    if query_params:
        # Parâmetros de query DEVEM ser ordenados alfabeticamente
        for key in sorted(query_params.keys()):
            parts.append(f"{key}={query_params[key]}")

    if body and body.strip() not in ("", "{}"):
        parts.append(body)

    string_to_sign = "&".join(parts)
    print(f"[Keeta][_generate_signature] String a ser assinada (preview): {string_to_sign[:200]}")

    # Calcula o HMAC-SHA256
    signature_bytes = hmac.new(
        key=CLIENT_SECRET.encode("utf-8"),
        msg=string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    # Codifica em Base64 e retorna como string
    signature = base64.b64encode(signature_bytes).decode("utf-8")
    print(f"[Keeta][_generate_signature] FIM | assinatura gerada (preview)={signature[:20]}...")
    return signature


def _build_headers(url: str, query_params: dict = None, body: str = None) -> dict:
    """
    Monta o dicionário de headers padrão para qualquer chamada à Keeta.
    Inclui: Authorization (Bearer Token) + Content-Type + X-App-Signature
    """
    print(f"[Keeta][_build_headers] INÍCIO | url={url}")
    token = get_access_token()
    signature = _generate_signature(url, query_params, body)

    headers = {
        "Authorization":   f"Bearer {token}",
        "Content-Type":    "application/json; charset=utf-8",
        "X-App-Signature": signature,
    }
    print(f"[Keeta][_build_headers] FIM | headers montados (token oculto parcialmente): Authorization=Bearer {str(token)[:15]}... | X-App-Signature={signature[:15]}...")
    return headers


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
    print(f"\n[Keeta][confirm_order] INÍCIO | order_id={order_id}")
    url = f"{BASE_URL}/v1/orders/{order_id}/confirm"
    body = "{}"

    print(f"[Keeta][confirm_order] POST {url}")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        print(f"[Keeta][confirm_order] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][confirm_order] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][confirm_order] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][confirm_order] FIM (falha) | order_id={order_id}")
        return False


def notify_ready_for_pickup(order_id: str) -> bool:
    """
    Informa a Keeta que o pedido está pronto para retirada.

    Quando usar: quando a cozinha terminou de preparar o pedido.
    O pedido muda de estado: CONFIRMED → READY_FOR_PICKUP

    Endpoint: POST /v1/orders/{orderId}/readyForPickup
    """
    print(f"\n[Keeta][notify_ready_for_pickup] INÍCIO | order_id={order_id}")
    url = f"{BASE_URL}/v1/orders/{order_id}/readyForPickup"
    body = "{}"

    print(f"[Keeta][notify_ready_for_pickup] POST {url}")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        print(f"[Keeta][notify_ready_for_pickup] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][notify_ready_for_pickup] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][notify_ready_for_pickup] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][notify_ready_for_pickup] FIM (falha) | order_id={order_id}")
        return False


def notify_dispatched(order_id: str) -> bool:
    """
    Informa a Keeta que o pedido saiu para entrega (despacho do motoboy).

    Quando usar: quando o entregador saiu com o pedido.
    O pedido muda de estado: READY_FOR_PICKUP → DISPATCHED

    Endpoint: POST /v1/orders/{orderId}/dispatch
    """
    print(f"\n[Keeta][notify_dispatched] INÍCIO | order_id={order_id}")
    url = f"{BASE_URL}/v1/orders/{order_id}/dispatch"
    body = "{}"

    print(f"[Keeta][notify_dispatched] POST {url}")
    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        print(f"[Keeta][notify_dispatched] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][notify_dispatched] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][notify_dispatched] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][notify_dispatched] FIM (falha) | order_id={order_id}")
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
    print(f"\n[Keeta][request_cancellation] INÍCIO | order_id={order_id} | reason='{reason}'")
    url = f"{BASE_URL}/v1/orders/{order_id}/requestCancellation"

    payload = {
        "reason": reason,
        "code":   "INTERNAL_DIFFICULTIES_OF_THE_RESTAURANT",
        "mode":   "MANUAL",
    }
    body = json.dumps(payload)
    print(f"[Keeta][request_cancellation] POST {url} | payload={payload}")

    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        print(f"[Keeta][request_cancellation] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][request_cancellation] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][request_cancellation] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][request_cancellation] FIM (falha) | order_id={order_id}")
        return False


def get_order_details(order_id: str) -> dict | None:
    """
    Busca os detalhes completos de um pedido na Keeta.

    Retorna um dicionário com todos os dados do pedido:
    itens, cliente, endereço, valores, pagamento, etc.

    Endpoint: GET /v1/orders/{orderId}
    """
    print(f"\n[Keeta][get_order_details] INÍCIO | order_id={order_id}")
    url = f"{BASE_URL}/v1/orders/{order_id}"

    print(f"[Keeta][get_order_details] GET {url}")
    try:
        response = requests.get(url, headers=_build_headers(url))
        print(f"[Keeta][get_order_details] Resposta | status_code={response.status_code}")
        response.raise_for_status()

        order_data = response.json()
        print(f"[Keeta][get_order_details] Dados do pedido obtidos (chaves de topo): {list(order_data.keys())}")
        _save_log(f"ORDER_{order_id}", order_data)  # salva o JSON bruto para debug
        print(f"[Keeta][get_order_details] FIM (sucesso) | order_id={order_id}")
        return order_data

    except Exception as e:
        print(f"[Keeta][get_order_details] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][get_order_details] FIM (falha) | order_id={order_id}")
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
    print(f"\n[Keeta][register_merchant] INÍCIO | keeta_merchant_id={keeta_merchant_id} | my_local_store_id={my_local_store_id}")

    url = f"{BASE_URL}/v1/merchantOnboarding"
    query_params = {"merchantId": my_local_store_id}

    payload = {
        "getMerchantURL": {
            # Inclui o storeId na própria URL, assim cada loja tem seu cardápio
            "baseURL": f"{MY_PUBLIC_URL}/menu?storeId={my_local_store_id}",
            "apiKey":  "123456",
        },
        "ordersWebhookURL": f"{MY_PUBLIC_URL}/orders",  # Keeta vai fazer POST aqui para enviar eventos
        "keetaMerchantId": keeta_merchant_id,
    }
    body = json.dumps(payload)
    print(f"[Keeta][register_merchant] Payload montado: {payload}")

    full_url_with_params = f"{url}?merchantId={my_local_store_id}"
    print(f"[Keeta][register_merchant] PUT {full_url_with_params}")

    try:
        response = requests.put(
            full_url_with_params,
            headers=_build_headers(url, query_params=query_params, body=body),
            data=body,
        )
        print(f"[Keeta][register_merchant] Resposta | status_code={response.status_code} | body={response.text[:500]}")
        resultado = response.json()
        print(f"[Keeta][register_merchant] FIM (sucesso) | keeta_merchant_id={keeta_merchant_id}")
        return resultado
    except Exception as e:
        print(f"[Keeta][register_merchant] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][register_merchant] FIM (falha) | keeta_merchant_id={keeta_merchant_id}")
        return None


def update_store_status(keeta_merchant_id: str, is_open: bool) -> bool:
    """
    Abre ou fecha a loja na plataforma Keeta.

    Quando usar: no início/fim do expediente, ou quando a loja fica sem
    capacidade de atender (ex: sem entregador).

    Endpoint: POST /v1/merchantUpdate/{merchantId}
    """
    print(f"\n[Keeta][update_store_status] INÍCIO | keeta_merchant_id={keeta_merchant_id} | is_open={is_open}")

    url = f"{BASE_URL}/v1/merchantUpdate/{keeta_merchant_id}"
    status = "AVAILABLE" if is_open else "UNAVAILABLE"

    payload = {"merchantStatus": status}
    body = json.dumps(payload)
    print(f"[Keeta][update_store_status] POST {url} | payload={payload}")

    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body)
        print(f"[Keeta][update_store_status] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][update_store_status] FIM | keeta_merchant_id={keeta_merchant_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][update_store_status] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][update_store_status] FIM (falha) | keeta_merchant_id={keeta_merchant_id}")
        return False


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
    print(f"[Keeta][validate_webhook_signature] INÍCIO | body_len={len(body)} | received_signature_preview={received_signature[:20]}...")

    expected_signature = hmac.new(
        key=CLIENT_SECRET.encode("utf-8"),
        msg=body.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    expected_b64 = base64.b64encode(expected_signature).decode("utf-8")
    valida = hmac.compare_digest(expected_b64, received_signature)

    print(f"[Keeta][validate_webhook_signature] Assinatura esperada (preview)={expected_b64[:20]}... | válida={valida}")
    print(f"[Keeta][validate_webhook_signature] FIM | válida={valida}")
    return valida


# =============================================================================
#  6. UTILITÁRIOS
# =============================================================================

def _save_log(prefix: str, data: dict):
    """
    Salva um JSON em disco para facilitar o debug durante o desenvolvimento.
    Os arquivos ficam na pasta `keeta_logs/`.
    """
    print(f"[Keeta][_save_log] INÍCIO | prefix={prefix}")
    try:
        os.makedirs("keeta_logs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"keeta_logs/{timestamp}_{prefix}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[Keeta][_save_log] Log salvo em: {filename}")
    except Exception as e:
        print(f"[Keeta][_save_log] AVISO: não foi possível salvar o log em disco: {type(e).__name__}: {e}")
    print(f"[Keeta][_save_log] FIM | prefix={prefix}")

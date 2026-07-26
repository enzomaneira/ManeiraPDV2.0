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

# Timeout (em segundos) para TODAS as chamadas HTTP feitas à Keeta.
#
# IMPORTANTE: sem um timeout explícito, a biblioteca `requests` espera
# INDEFINIDAMENTE por uma resposta. Isso é extremamente perigoso no fluxo do
# webhook: se a Keeta (ou a rede) demorar/travar, o worker do Gunicorn que
# está processando o webhook fica preso para sempre, nunca respondendo 200
# para a Keeta. Como resultado, a Keeta entende que o webhook falhou
# ("Failed" / "Unknown Protocol" — a conexão é derrubada pelo proxy antes de
# terminar) e reenvia o MESMO evento repetidamente em loop (a cada ~12s),
# esgotando os workers disponíveis.
#
# (connect_timeout, read_timeout) — generosos o suficiente para não afetar
# operação normal, mas curtos o suficiente para nunca travar um worker.
REQUEST_TIMEOUT = (5, 15)

# URL pública do backend — usada no onboarding para informar à Keeta:
#   - onde fazer POST dos eventos de pedido (webhook)
#   - onde fazer GET do cardápio (menu endpoint)
#
# No Railway: já está configurada via variável de ambiente MY_PUBLIC_URL
#   (ver backend/.env): https://backend-production-818f.up.railway.app/api/keeta
#
# Localmente com ngrok: defina MY_PUBLIC_URL no seu .env local com a URL do ngrok.
#
# O fallback abaixo é a própria URL de produção do backend no Railway, para
# nunca cairmos em um placeholder inválido caso a env var não esteja setada.
_PRODUCTION_URL_FALLBACK = "https://backend-production-818f.up.railway.app/api/keeta"
MY_PUBLIC_URL = os.getenv("MY_PUBLIC_URL", _PRODUCTION_URL_FALLBACK)

# --- Proteção extra: se a variável de ambiente estiver configurada no Railway
# com um valor placeholder esquecido (ex: "SEU-BACKEND"), ignoramos o valor da
# env var e usamos a URL de produção correta, para nunca enviar um webhook
# quebrado no onboarding da Keeta.
if "SEU-BACKEND" in MY_PUBLIC_URL or "seu-backend" in MY_PUBLIC_URL.lower():
    print(f"[Keeta][INIT] AVISO: MY_PUBLIC_URL contém um placeholder inválido ('{MY_PUBLIC_URL}'). "
          f"Corrija a variável de ambiente no Railway! Usando fallback de produção por segurança.")
    MY_PUBLIC_URL = _PRODUCTION_URL_FALLBACK

# Normalização: remove sufixos de rota que podem ter sido incluídos por engano
# na env var. MY_PUBLIC_URL deve ser a raiz do blueprint (/api/keeta), sem
# /orders, /menu etc. Caso contrário as URLs ficam quebradas como:
#   .../api/keeta/orders/menu   (invés de .../api/keeta/menu)
#   .../api/keeta/orders/orders (invés de .../api/keeta/orders)
_original = MY_PUBLIC_URL
MY_PUBLIC_URL = MY_PUBLIC_URL.rstrip("/")  # remove trailing slash
for _suffix in ("/onboard", "/store-status", "/authorization", "/orders", "/menu"):
    if MY_PUBLIC_URL.endswith(_suffix):
        MY_PUBLIC_URL = MY_PUBLIC_URL[:-len(_suffix)]
        print(f"[Keeta][INIT] CORRIGIDO: removido sufixo '{_suffix}' de MY_PUBLIC_URL. "
              f"Antes='{_original}' → Depois='{MY_PUBLIC_URL}'. Corrija a env var no Railway!")
        break

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
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
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

def canonical_json(payload) -> str:
    """
    Serializa um dict em JSON "canônico", seguindo o espírito da RFC 8785
    (JSON Canonicalization Scheme) exigido pela Keeta para o cálculo da
    assinatura:

      - Chaves ordenadas alfabeticamente (recursivamente, em sub-objetos)
      - SEM espaços após ":" e "," (separators compactos)
      - Sem espaços/indentação extra

    Isso é crítico: o texto que vira `body` da requisição precisa ser
    EXATAMENTE igual (byte a byte) ao texto usado para calcular a assinatura.
    Se usarmos json.dumps(payload) "normal", o Python insere espaços
    (ex: '{"key": "value"}') e a Keeta rejeita com 401 Invalid signature.

    Retorna uma string vazia se payload for None.
    """
    if payload is None:
        return ""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _generate_signature(url: str, query_params: dict = None, body: str = None) -> str:
    """
    Gera a assinatura HMAC-SHA256 que a Keeta exige em toda requisição.

    Como funciona (conforme documentação oficial):
      signature_string = URL + "&" + sorted_query_params + "&" + request_body

      1. URL: base, sem query string
      2. Query params: ordenados alfabeticamente por chave, formato key=value,
         unidos com "&"
      3. Body: o JSON exatamente como foi enviado (canônico, sem espaços,
         chaves ordenadas). Corpos vazios ("" ou "{}") são omitidos.

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
            value = query_params[key]
            value_str = "" if value is None else str(value)
            parts.append(f"{key}={value_str}")

    if body and body.strip() not in ("", "{}"):
        parts.append(body)

    string_to_sign = "&".join(parts)
    print(f"[Keeta][_generate_signature] String a ser assinada (completa): {string_to_sign}")

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
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
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
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
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
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
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
    body = canonical_json(payload)
    print(f"[Keeta][request_cancellation] POST {url} | payload={payload} | body_canonico={body}")

    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][request_cancellation] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        print(f"[Keeta][request_cancellation] FIM | order_id={order_id} | sucesso={sucesso}")
        return sucesso
    except Exception as e:
        print(f"[Keeta][request_cancellation] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][request_cancellation] FIM (falha) | order_id={order_id}")
        return False


def get_order_details(order_id: str, order_url: str | None = None) -> dict | None:
    """
    Busca os detalhes completos de um pedido na Keeta.

    Retorna um dicionário com todos os dados do pedido:
    itens, cliente, endereço, valores, pagamento, etc.

    Endpoint: GET /v1/orders/{orderId}

    IMPORTANTE: sempre que um evento de webhook/polling for recebido, a Keeta
    já envia o campo `orderURL` — "The URL to get the order details" — dentro
    do próprio payload do evento. Por segurança e para seguir exatamente a
    documentação oficial, damos preferência a essa URL (order_url) em vez de
    montar `{BASE_URL}/v1/orders/{orderId}` manualmente.

    Se `order_url` não for informado (ex: chamadas antigas/manuais), caímos
    no fallback de montar a URL padrão a partir do order_id.
    """
    print(f"\n[Keeta][get_order_details] INÍCIO | order_id={order_id} | order_url_recebida={order_url}")

    if order_url:
        url = order_url
        print(f"[Keeta][get_order_details] Usando orderURL vinda do evento (recomendado pela doc oficial): {url}")
    else:
        url = f"{BASE_URL}/v1/orders/{order_id}"
        print(f"[Keeta][get_order_details] orderURL não informada. Usando fallback montado manualmente: {url}")

    print(f"[Keeta][get_order_details] GET {url}")
    try:
        response = requests.get(url, headers=_build_headers(url), timeout=REQUEST_TIMEOUT)
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

    # ATENÇÃO: `keetaMerchantId` DEVE ser um número inteiro, NÃO uma string.
    # A documentação oficial da Keeta especifica o tipo como `number`, e enviar
    # como string pode fazer o onboarding ser aceito mas o webhook não ser
    # efetivamente registrado do lado da Keeta.
    try:
        keeta_merchant_id_int = int(keeta_merchant_id)
    except (ValueError, TypeError):
        print(f"[Keeta][register_merchant] FALHA: keetaMerchantId='{keeta_merchant_id}' não é um número válido.")
        return None

    payload = {
        "getMerchantURL": {
            # Inclui o storeId na própria URL, assim cada loja tem seu cardápio
            "baseURL": f"{MY_PUBLIC_URL}/menu?storeId={my_local_store_id}",
            "apiKey":  "123456",
        },
        "ordersWebhookURL": f"{MY_PUBLIC_URL}/orders",  # Keeta vai fazer POST aqui para enviar eventos
        "keetaMerchantId": keeta_merchant_id_int,         # DEVE ser number (int), não string
    }
    body = canonical_json(payload)
    print(f"[Keeta][register_merchant] Payload montado: {payload} | body_canonico={body}")

    full_url_with_params = f"{url}?merchantId={my_local_store_id}"
    print(f"[Keeta][register_merchant] PUT {full_url_with_params}")

    try:
        response = requests.put(
            full_url_with_params,
            headers=_build_headers(url, query_params=query_params, body=body),
            data=body,
            timeout=REQUEST_TIMEOUT,
        )
        print(f"[Keeta][register_merchant] Resposta | status_code={response.status_code} | body={response.text[:500]}")
        resultado = response.json()
        print(f"[Keeta][register_merchant] FIM (sucesso) | keeta_merchant_id={keeta_merchant_id}")
        return resultado
    except Exception as e:
        print(f"[Keeta][register_merchant] ERRO: {type(e).__name__}: {e}")
        print(f"[Keeta][register_merchant] FIM (falha) | keeta_merchant_id={keeta_merchant_id}")
        return None


def update_store_status(keeta_merchant_id: str, is_open: bool) -> tuple[bool, str | None]:
    """
    Abre ou fecha a loja na plataforma Keeta.

    Quando usar: no início/fim do expediente, ou quando a loja fica sem
    capacidade de atender (ex: sem entregador).

    Endpoint: POST /v1/merchantUpdate/{merchantId}

    Retorna (sucesso, mensagem_de_erro). Se sucesso=True, mensagem é None.
    """
    print(f"\n[Keeta][update_store_status] INÍCIO | keeta_merchant_id={keeta_merchant_id} | is_open={is_open}")

    url = f"{BASE_URL}/v1/merchantUpdate/{keeta_merchant_id}"
    status = "AVAILABLE" if is_open else "UNAVAILABLE"

    payload = {"merchantStatus": status}
    body = canonical_json(payload)
    print(f"[Keeta][update_store_status] POST {url} | payload={payload} | body_canonico={body}")

    try:
        response = requests.post(url, headers=_build_headers(url, body=body), data=body, timeout=REQUEST_TIMEOUT)
        print(f"[Keeta][update_store_status] Resposta | status_code={response.status_code} | body={response.text[:300]}")
        sucesso = response.status_code in (200, 201, 204)
        erro = None if sucesso else f"Keeta API retornou {response.status_code}: {response.text[:200]}"
        print(f"[Keeta][update_store_status] FIM | keeta_merchant_id={keeta_merchant_id} | sucesso={sucesso}")
        return sucesso, erro
    except Exception as e:
        erro_msg = f"{type(e).__name__}: {e}"
        print(f"[Keeta][update_store_status] ERRO: {erro_msg}")
        print(f"[Keeta][update_store_status] FIM (falha) | keeta_merchant_id={keeta_merchant_id}")
        return False, erro_msg


# =============================================================================
#  5. VALIDAÇÃO DO WEBHOOK
# =============================================================================

def validate_webhook_signature(body: str, received_signature: str) -> bool:
    """
    Valida se um webhook recebido realmente veio da Keeta.

    Segundo a documentação oficial de assinatura da Keeta, a mesma fórmula
    usada para assinar requisições que ENVIAMOS também é usada pela Keeta
    para assinar as requisições que ela nos ENVIA (webhooks):

        signature_string = URL + "&" + sorted_query_params + "&" + body

    Ou seja, a assinatura do webhook NÃO é calculada apenas sobre o body:
    ela inclui a URL do próprio webhook (a mesma informada como
    `ordersWebhookURL` no onboarding). Por isso, tentamos validar contra
    duas possibilidades, para sermos compatíveis mesmo com pequenas
    variações de URL (com ou sem barra final, etc):

      1. URL + body   (fórmula oficial, URL = ordersWebhookURL)
      2. body isolado (fallback legado, caso a Keeta não inclua a URL)

    Retorna True se a assinatura é válida (é da Keeta), False caso contrário.
    """
    print(f"[Keeta][validate_webhook_signature] INÍCIO | body_len={len(body)} | received_signature_preview={received_signature[:20]}...")

    webhook_url = f"{MY_PUBLIC_URL}/orders"

    candidatos = {
        "url+body":        f"{webhook_url}&{body}" if body and body.strip() not in ("", "{}") else webhook_url,
        "url+body(sem_barra)": (f"{webhook_url.rstrip('/')}&{body}" if body and body.strip() not in ("", "{}") else webhook_url.rstrip("/")),
        "body_apenas":     body,
    }

    for nome, string_to_sign in candidatos.items():
        expected_signature = hmac.new(
            key=CLIENT_SECRET.encode("utf-8"),
            msg=string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_b64 = base64.b64encode(expected_signature).decode("utf-8")
        valida = hmac.compare_digest(expected_b64, received_signature)
        print(f"[Keeta][validate_webhook_signature] Tentativa '{nome}' | string_preview={string_to_sign[:80]}... | esperado(preview)={expected_b64[:20]}... | válida={valida}")

        if valida:
            print(f"[Keeta][validate_webhook_signature] FIM | válida=True (método='{nome}')")
            return True

    print(f"[Keeta][validate_webhook_signature] FIM | válida=False (nenhum método bateu)")
    return False


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

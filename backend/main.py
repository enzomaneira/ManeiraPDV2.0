# =============================================================================
#  main.py  —  Ponto de entrada do ManeiraPDV (Backend Python)
# =============================================================================
#
#  Inicializa a aplicação Flask, registra os blueprints (grupos de rotas)
#  e conecta ao banco de dados.
#
#  Para rodar localmente:
#    pip install -r requirements.txt
#    python main.py
#
#  No Railway:
#    O Railway injeta automaticamente a variável $PORT.
#    O gunicorn usa essa porta para servir a aplicação.
# =============================================================================

import os

from flask import Flask
from flask_cors import CORS

from database import init_db
import models  # importa os modelos para o SQLAlchemy reconhecê-los

# Blueprints (grupos de rotas organizados por domínio)
from routes.orders        import orders_bp
from routes.keeta_webhook import keeta_bp
from routes.config        import config_bp
from routes.stores        import stores_bp

import keeta_client  # importa para testar a conexão no startup

# Porta que o Railway injeta via variável de ambiente (padrão 8080 local)
PORT = int(os.getenv("PORT", 8080))

# -----------------------------------------------------------------------------
#  Cria a aplicação Flask
# -----------------------------------------------------------------------------
app = Flask(__name__)

# Permite requisições de qualquer origem (necessário para o frontend React)
CORS(app)

# -----------------------------------------------------------------------------
#  Conecta ao banco e cria as tabelas (se não existirem)
# -----------------------------------------------------------------------------
init_db(app)

# -----------------------------------------------------------------------------
#  Registra os blueprints com seus prefixos de URL
#
#  Mapeamento de endpoints:
#    /api/orders/*    → routes/orders.py
#    /api/keeta/*     → routes/keeta_webhook.py
#    /api/config/*    → routes/config.py
#    /api/stores/*    → routes/stores.py
# -----------------------------------------------------------------------------
app.register_blueprint(orders_bp, url_prefix="/api/orders")
app.register_blueprint(keeta_bp,  url_prefix="/api/keeta")
app.register_blueprint(config_bp, url_prefix="/api/config")
app.register_blueprint(stores_bp, url_prefix="/api/stores")


# -----------------------------------------------------------------------------
#  Teste de integração no startup
#  (equivalente ao CommandLineRunner do Spring Boot)
# -----------------------------------------------------------------------------
with app.app_context():
    print("\n" + "="*60)
    print("  ManeiraPDV — Backend Python iniciando...")
    print("="*60)

    print("\n[Startup] Testando conexão com a Keeta API...")
    token = keeta_client.get_access_token()
    if token:
        print(f"[Startup] ✅ Token Keeta obtido com sucesso!")
    else:
        print(f"[Startup] ⚠️  Não foi possível obter o token da Keeta. Verifique as credenciais.")

    print("\n[Startup] Gerando URL de autorização de exemplo...")
    auth_url = keeta_client.get_authorization_url("http://localhost:8080/api/keeta/callback")
    if auth_url:
        print(f"[Startup] URL de Auth: {str(auth_url)[:80]}...")

    print("\n" + "="*60 + "\n")


# -----------------------------------------------------------------------------
#  Inicia o servidor
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # debug=False em produção (Railway define RAILWAY_ENVIRONMENT=production)
    is_dev = os.getenv("RAILWAY_ENVIRONMENT") is None
    app.run(host="0.0.0.0", port=PORT, debug=is_dev)

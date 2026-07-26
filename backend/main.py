# =============================================================================
#  main.py  —  Ponto de entrada do ManeiraPDV (Backend Python / Flask)
# =============================================================================

import os
from flask import Flask, request
from flask_cors import CORS
from database import db, get_database_url
import models  # garante que os modelos são registrados no SQLAlchemy

from routes.orders        import orders_bp
from routes.keeta_webhook import keeta_bp
from routes.config        import config_bp
from routes.stores        import stores_bp
from routes.auth          import auth_bp

print("\n" + "=" * 70)
print("[Main][INIT] Carregando módulo main.py...")
print("=" * 70)


def _get_cors_origins() -> list[str]:
    """
    Lê as origens permitidas da variável de ambiente CORS_ORIGINS.
    Formato: múltiplas origens separadas por vírgula, sem espaços.

    Ex: https://meu-frontend.up.railway.app,http://localhost:5173

    Igual ao padrão usado no mmb-backend.
    """
    print("[Main][_get_cors_origins] INÍCIO")

    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000",
    )
    print(f"[Main][_get_cors_origins] Valor bruto de CORS_ORIGINS: '{raw}'")

    origins = [o.strip() for o in raw.split(",") if o.strip()]
    print(f"[CORS] Origins permitidas: {origins}")
    print("[Main][_get_cors_origins] FIM")
    return origins


def create_app():
    print("\n[Main][create_app] INÍCIO da criação da aplicação Flask...")

    application = Flask(__name__)
    print("[Main][create_app] Instância Flask criada.")

    # CORS com origins vindas do ambiente
    cors_origins = _get_cors_origins()
    CORS(application, origins=cors_origins)
    print(f"[Main][create_app] CORS configurado | origins={cors_origins}")

    # Log de todas as requisições recebidas (método + path + origem)
    @application.before_request
    def _log_request():
        print(f"[HTTP][REQUEST] {request.method} {request.path} | origin={request.headers.get('Origin')} | remote_addr={request.remote_addr}")

    @application.after_request
    def _log_response(response):
        print(f"[HTTP][RESPONSE] {request.method} {request.path} → status={response.status_code}")
        return response

    @application.errorhandler(Exception)
    def _log_unhandled_exception(e):
        print(f"[HTTP][UNHANDLED_ERROR] {request.method} {request.path} → {type(e).__name__}: {e}")
        raise e

    # Banco de dados
    database_url = get_database_url()
    application.config["SQLALCHEMY_DATABASE_URI"]        = database_url
    application.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    print("[Main][create_app] Configuração SQLALCHEMY_DATABASE_URI definida.")

    db.init_app(application)
    print("[Main][create_app] db.init_app(application) executado.")

    # Blueprints
    print("[Main][create_app] Registrando blueprints...")
    application.register_blueprint(orders_bp, url_prefix="/api/orders")
    print("[Main][create_app]   → orders_bp registrado em /api/orders")
    application.register_blueprint(keeta_bp,  url_prefix="/api/keeta")
    print("[Main][create_app]   → keeta_bp registrado em /api/keeta")
    application.register_blueprint(config_bp, url_prefix="/api/config")
    print("[Main][create_app]   → config_bp registrado em /api/config")
    application.register_blueprint(stores_bp, url_prefix="/api/stores")
    print("[Main][create_app]   → stores_bp registrado em /api/stores")
    application.register_blueprint(auth_bp,   url_prefix="/api/auth")
    print("[Main][create_app]   → auth_bp registrado em /api/auth")

    # Cria as tabelas ao iniciar
    print("[Main][create_app] Verificando/criando tabelas no banco de dados...")
    with application.app_context():
        try:
            db.create_all()
            print("[DB] Tabelas verificadas/criadas com sucesso.")
            try:
                tabelas = list(db.metadata.tables.keys())
                print(f"[DB] Tabelas registradas no metadata: {tabelas}")
            except Exception as inner_e:
                print(f"[DB] AVISO: não foi possível listar tabelas do metadata: {inner_e}")
        except Exception as e:
            print(f"[DB] AVISO ao criar tabelas: {type(e).__name__}: {e}")

        _run_lightweight_migrations()

    print("[Main][create_app] FIM (aplicação criada com sucesso)")
    return application


def _run_lightweight_migrations():
    """
    Como o projeto não usa Alembic/Flask-Migrate, `db.create_all()` só cria
    tabelas que ainda não existem — ele NÃO adiciona colunas novas em tabelas
    já existentes. Para não quebrar o banco de produção sempre que um novo
    campo for adicionado a um model, rodamos aqui pequenos `ALTER TABLE ...
    ADD COLUMN IF NOT EXISTS` (idempotentes e seguros de rodar toda vez que
    a aplicação sobe).
    """
    from sqlalchemy import text

    print("[DB][_run_lightweight_migrations] INÍCIO")

    statements = [
        # StoreConfig: campos do webhook de autorização Keeta (eventos 1301/1302)
        "ALTER TABLE store_config ADD COLUMN IF NOT EXISTS keeta_authorized BOOLEAN DEFAULT FALSE",
        "ALTER TABLE store_config ADD COLUMN IF NOT EXISTS keeta_auth_id VARCHAR(100)",
    ]

    for stmt in statements:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
            print(f"[DB][_run_lightweight_migrations] OK: {stmt}")
        except Exception as e:
            db.session.rollback()
            print(f"[DB][_run_lightweight_migrations] AVISO ao executar '{stmt}': {type(e).__name__}: {e}")

    print("[DB][_run_lightweight_migrations] FIM")


# Instância global usada pelo gunicorn (gunicorn main:app)
print("[Main] Instanciando app global via create_app()...")
app = create_app()
print("[Main] App global instanciada com sucesso.")


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8080))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    print(f"\n[ManeiraPDV] Iniciando na porta {PORT} | debug={DEBUG}\n")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)

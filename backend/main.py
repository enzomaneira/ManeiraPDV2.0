# =============================================================================
#  main.py  —  Ponto de entrada do ManeiraPDV (Backend Python / Flask)
# =============================================================================

import os
from flask import Flask
from flask_cors import CORS
from database import db, get_database_url
import models  # garante que os modelos são registrados no SQLAlchemy

from routes.orders        import orders_bp
from routes.keeta_webhook import keeta_bp
from routes.config        import config_bp
from routes.stores        import stores_bp


def _get_cors_origins() -> list[str]:
    """
    Lê as origens permitidas da variável de ambiente CORS_ORIGINS.
    Formato: múltiplas origens separadas por vírgula, sem espaços.

    Ex: https://meu-frontend.up.railway.app,http://localhost:5173

    Igual ao padrão usado no mmb-backend.
    """
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000",
    )
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    print(f"[CORS] Origins permitidas: {origins}")
    return origins


def create_app():
    application = Flask(__name__)

    # CORS com origins vindas do ambiente
    CORS(application, origins=_get_cors_origins())

    # Banco de dados
    application.config["SQLALCHEMY_DATABASE_URI"]        = get_database_url()
    application.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(application)

    # Blueprints
    application.register_blueprint(orders_bp, url_prefix="/api/orders")
    application.register_blueprint(keeta_bp,  url_prefix="/api/keeta")
    application.register_blueprint(config_bp, url_prefix="/api/config")
    application.register_blueprint(stores_bp, url_prefix="/api/stores")

    # Cria as tabelas ao iniciar
    with application.app_context():
        try:
            db.create_all()
            print("[DB] Tabelas verificadas/criadas com sucesso.")
        except Exception as e:
            print(f"[DB] AVISO ao criar tabelas: {e}")

    return application


# Instância global usada pelo gunicorn (gunicorn main:app)
app = create_app()


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8080))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    print(f"\n[ManeiraPDV] Iniciando na porta {PORT} | debug={DEBUG}\n")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)

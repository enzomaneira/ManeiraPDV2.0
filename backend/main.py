# =============================================================================
#  main.py  —  Ponto de entrada do ManeiraPDV (Backend Python)
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

# -----------------------------------------------------------------------------
#  Factory function — cria e configura a aplicação Flask
#  O gunicorn chama: gunicorn main:app, então 'app' precisa estar no módulo
# -----------------------------------------------------------------------------
def create_app():
    application = Flask(__name__)
    CORS(application)

    # Banco de dados
    application.config["SQLALCHEMY_DATABASE_URI"]        = get_database_url()
    application.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(application)

    # Blueprints
    application.register_blueprint(orders_bp, url_prefix="/api/orders")
    application.register_blueprint(keeta_bp,  url_prefix="/api/keeta")
    application.register_blueprint(config_bp, url_prefix="/api/config")
    application.register_blueprint(stores_bp, url_prefix="/api/stores")

    # Cria as tabelas ao iniciar (só roda uma vez dentro do contexto correto)
    with application.app_context():
        try:
            db.create_all()
            print("[DB] Tabelas verificadas/criadas com sucesso.")
        except Exception as e:
            print(f"[DB] AVISO ao criar tabelas: {e}")

    return application


# Instância global usada pelo gunicorn (gunicorn main:app)
app = create_app()


# -----------------------------------------------------------------------------
#  Inicia o servidor (apenas quando rodado diretamente: python main.py)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8080))
    is_dev = os.getenv("RAILWAY_ENVIRONMENT") is None
    print(f"\n[ManeiraPDV] Iniciando na porta {PORT} | debug={is_dev}\n")
    app.run(host="0.0.0.0", port=PORT, debug=is_dev)

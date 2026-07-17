# =============================================================================
#  database.py  —  Configuração do banco de dados
# =============================================================================
#
#  Usamos Flask-SQLAlchemy como ORM.
#  A conexão com o PostgreSQL é configurada via variável de ambiente.
# =============================================================================

import os
from flask_sqlalchemy import SQLAlchemy

# Instância global do banco — importada em models.py e em main.py
db = SQLAlchemy()


def get_database_url() -> str:
    """
    Retorna a URL de conexão com o banco.

    O Railway injeta automaticamente a variável DATABASE_URL quando você
    adiciona um serviço PostgreSQL ao projeto. O formato que ele fornece é:
      postgresql://user:pass@host:port/db

    O SQLAlchemy (com psycopg2) precisa do prefixo:
      postgresql+psycopg2://user:pass@host:port/db

    Por isso fazemos a substituição abaixo.
    """
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:senha123@localhost:5433/maneira_pdv",
    )
    # Corrige o prefixo antigo "postgres://" que algumas plataformas ainda usam
    url = url.replace("postgres://", "postgresql://", 1)
    # Garante que o driver psycopg2 seja usado explicitamente
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def init_db(app):
    """
    Inicializa o banco de dados com a aplicação Flask e cria as tabelas.
    Chamada uma única vez no main.py.
    """
    app.config["SQLALCHEMY_DATABASE_URI"]       = get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        print("[DB] Tabelas verificadas/criadas com sucesso.")

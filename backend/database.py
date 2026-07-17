# =============================================================================
#  database.py  —  Configuração do banco de dados
# =============================================================================

import os
from flask_sqlalchemy import SQLAlchemy

# Instância global do banco — importada em models.py e nas routes
db = SQLAlchemy()


def get_database_url() -> str:
    """
    Retorna a URL de conexão com o banco.

    O Railway injeta automaticamente DATABASE_URL quando você adiciona
    um serviço PostgreSQL ao projeto.

    O SQLAlchemy precisa do prefixo postgresql+psycopg2://, mas o Railway
    entrega postgresql:// — corrigimos aqui.
    """
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:senha123@localhost:5433/maneira_pdv",
    )
    # Corrige prefixo legado "postgres://" (usado por algumas plataformas)
    url = url.replace("postgres://", "postgresql://", 1)
    # Adiciona o driver psycopg2 explicitamente
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url

# =============================================================================
#  database.py  —  Configuração do banco de dados
# =============================================================================

import os
from flask_sqlalchemy import SQLAlchemy

# Instância global do banco — importada em models.py e nas routes
db = SQLAlchemy()

print("[Database][INIT] Instância global do SQLAlchemy criada.")


def get_database_url() -> str:
    """
    Retorna a URL de conexão com o banco.

    O Railway injeta automaticamente DATABASE_URL quando você adiciona
    um serviço PostgreSQL ao projeto.

    O SQLAlchemy precisa do prefixo postgresql+psycopg2://, mas o Railway
    entrega postgresql:// — corrigimos aqui.
    """
    print("[Database][get_database_url] INÍCIO")

    raw_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:senha123@localhost:5433/maneira_pdv",
    )
    origem = "variável de ambiente DATABASE_URL" if os.getenv("DATABASE_URL") else "valor padrão (localhost)"
    print(f"[Database][get_database_url] URL bruta obtida de: {origem}")

    # Oculta a senha ao logar, por segurança
    def _mask(url: str) -> str:
        try:
            if "@" in url and "://" in url:
                scheme, rest = url.split("://", 1)
                creds, host_part = rest.split("@", 1)
                user = creds.split(":")[0]
                return f"{scheme}://{user}:****@{host_part}"
        except Exception:
            pass
        return "****"

    print(f"[Database][get_database_url] URL bruta (senha oculta): {_mask(raw_url)}")

    # Corrige prefixo legado "postgres://" (usado por algumas plataformas)
    url = raw_url.replace("postgres://", "postgresql://", 1)
    if url != raw_url:
        print("[Database][get_database_url] Prefixo 'postgres://' corrigido para 'postgresql://'")

    # Adiciona o driver psycopg2 explicitamente
    url_final = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    print(f"[Database][get_database_url] URL final (senha oculta): {_mask(url_final)}")

    print("[Database][get_database_url] FIM")
    return url_final

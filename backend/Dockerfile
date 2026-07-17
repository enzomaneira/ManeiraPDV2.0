FROM python:3.12-slim

WORKDIR /app

# Instala as dependências primeiro (camada cacheável)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Usa sh -c para que o shell expanda $PORT antes de passar para o gunicorn
# O Railway injeta $PORT automaticamente em tempo de execução
CMD ["sh", "-c", "gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120"]

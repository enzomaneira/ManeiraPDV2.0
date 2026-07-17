FROM python:3.12-slim

WORKDIR /app

# Instala as dependências primeiro (camada cacheável)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

EXPOSE 8080

CMD ["python", "main.py"]

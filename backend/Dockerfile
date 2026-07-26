FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8080

# --threads 4: permite que cada worker atenda várias requisições concorrentes
# (ex: vários webhooks da Keeta chegando ao mesmo tempo) sem enfileirar e
# sem depender só do número de workers, já que agora as chamadas HTTP à
# Keeta têm timeout curto (ver keeta_client.REQUEST_TIMEOUT) e não travam
# o processo indefinidamente.
CMD sh -c "gunicorn main:app --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 4 --timeout 120"

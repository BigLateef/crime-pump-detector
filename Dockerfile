FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x scripts/start_prod.sh

EXPOSE 8000

# Render (and most Docker-based platforms) run this CMD directly - they
# don't read a Procfile's separate `release` step the way Heroku does.
# start_prod.sh is what actually runs migrations and rejects placeholder
# secrets before starting uvicorn - calling uvicorn directly here would
# silently skip both. See scripts/start_prod.sh.
CMD ["./scripts/start_prod.sh"]

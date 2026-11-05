# Akademik İz: localdeki gibi tam uygulama (FastAPI + Scrapling + REA + Chromium)
FROM python:3.11-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt package.json package-lock.json ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && python -m patchright install chromium \
    && npm ci --no-audit --no-fund \
    && rm -rf /root/.npm

COPY . .

# Render portu PORT ortam değişkeniyle verir
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

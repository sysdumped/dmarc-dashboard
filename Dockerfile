# ── Stage 1: build React frontend ──────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json ./
RUN npm install --legacy-peer-deps

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + serve frontend ────────────────────────────────
FROM python:3.12-slim AS final

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend source
COPY backend/main.py ./

# Frontend build output
COPY --from=frontend-build /build/frontend/build ./frontend

# Data volume mount point
RUN mkdir -p /data

EXPOSE 8000

ENV DB_PATH=/data/dmarc.db \
    IMAP_HOST="" \
    IMAP_PORT="993" \
    IMAP_USER="" \
    IMAP_PASS="" \
    IMAP_FOLDER="INBOX" \
    IMAP_USE_SSL="true" \
    POLL_INTERVAL_SECONDS="300"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

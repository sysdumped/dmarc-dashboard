FROM node:18-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json ./
RUN npm install --legacy-peer-deps && \
    npm install --legacy-peer-deps ajv@^8.11.0 ajv-keywords@^5.1.0
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS final
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libssl-dev ca-certificates && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/main.py ./
COPY --from=frontend-build /build/frontend/build ./frontend
RUN mkdir -p /data
EXPOSE 8000
ENV DB_PATH=/data/dmarc.db \
    IMAP_HOST="" IMAP_PORT="993" IMAP_USER="" IMAP_PASS="" \
    IMAP_FOLDER="INBOX" IMAP_PROCESSED_FOLDER="Processed" \
    IMAP_USE_SSL="true" POLL_INTERVAL_SECONDS="300" \
    DB_BACKEND="sqlite" \
    OIDC_ENABLED="false" OIDC_ISSUER="" OIDC_CLIENT_ID="" \
    OIDC_CLIENT_SECRET="" OIDC_REDIRECT_URI="" \
    OIDC_SCOPES="openid profile email" SESSION_MAX_AGE="28800"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

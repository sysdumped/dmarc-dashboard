# DMARC Dashboard

Cruscotto fullstack per aggregare e visualizzare report DMARC ricevuti via IMAP.

## Stack

| Componente | Tecnologia |
|------------|-----------|
| Backend    | Python 3.12 · FastAPI · imaplib |
| Frontend   | React 18 · Recharts · Leaflet |
| Storage    | SQLite (persistente su PVC) |
| Geo lookup | ip-api.com (gratuito, senza chiave) |
| Deploy     | Docker multi-stage · Helm chart |

---

## Build locale

```bash
# 1. Build immagine Docker
docker build -t dmarc-dashboard:latest .

# 2. Avvia con docker-compose
cat > .env <<EOF
IMAP_HOST=mail.example.com
IMAP_PORT=993
IMAP_USER=dmarc@example.com
IMAP_PASS=password_sicura
IMAP_FOLDER=INBOX
IMAP_USE_SSL=true
POLL_INTERVAL_SECONDS=300
EOF

docker-compose up -d

# Dashboard disponibile su http://localhost:8000
```

---

## Deploy su Kubernetes (Helm)

### 1. Crea il Secret con la password IMAP

```bash
kubectl create secret generic dmarc-imap-secret \
  --from-literal=password='la_tua_password' \
  -n <namespace>
```

### 2. Configura `helm/values.yaml`

Cambia almeno:
- `image.repository` → il tuo registry (es. `registry.example.com/dmarc-dashboard`)
- `ingress.host` → l'hostname pubblico
- `imap.host` / `imap.user`

### 3. Push immagine e deploy

```bash
docker build -t registry.example.com/dmarc-dashboard:latest .
docker push registry.example.com/dmarc-dashboard:latest

helm upgrade --install dmarc-dashboard ./helm \
  -n <namespace> \
  --create-namespace \
  -f helm/values.yaml
```

---

## Variabili d'ambiente

| Variabile              | Default   | Descrizione                        |
|------------------------|-----------|------------------------------------|
| `IMAP_HOST`            | —         | Hostname server IMAP               |
| `IMAP_PORT`            | `993`     | Porta IMAP                         |
| `IMAP_USER`            | —         | Indirizzo email                    |
| `IMAP_PASS`            | —         | Password (usa un Secret K8s!)      |
| `IMAP_FOLDER`          | `INBOX`   | Cartella IMAP da scansionare       |
| `IMAP_USE_SSL`         | `true`    | SSL/TLS abilitato                  |
| `POLL_INTERVAL_SECONDS`| `300`     | Frequenza polling IMAP (secondi)   |
| `DB_PATH`              | `/data/dmarc.db` | Percorso database SQLite    |

---

## API REST (backend)

| Endpoint              | Descrizione                          |
|-----------------------|--------------------------------------|
| `GET /api/stats/overview` | Totali messaggi, DKIM/SPF pass, disposizioni |
| `GET /api/stats/timeline` | Dati per grafico temporale           |
| `GET /api/stats/by_domain`| Disposizione aggregata per dominio   |
| `GET /api/stats/sources`  | Tabella IP sorgenti con geo          |
| `GET /api/stats/geo`      | Punti per mappa geografica           |
| `GET /api/alerts`         | Alert policy non enforced/failing    |
| `GET /api/fetch_log`      | Log ultimi sync IMAP                 |
| `POST /api/fetch_now`     | Avvia sync IMAP manuale              |

Tutti gli endpoint accettano il parametro `?days=N` (default 30).

---

## Note DMARC

I report DMARC arrivano come allegati `.xml.gz` o `.zip` alle email inviate
dagli ESP (Google, Microsoft, Yahoo…) alla mailbox configurata con il tag
`rua` nel record DNS DMARC, es:

```
_dmarc.example.com TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com"
```

Il backend legge le ultime 500 email nella cartella configurata ad ogni polling,
deduplicando i report già importati tramite `report_id`.

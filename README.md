# DMARC Dashboard

Cruscotto fullstack per aggregare e visualizzare report DMARC ricevuti via IMAP.  
I report vengono letti dalla mailbox configurata, importati nel database e visualizzati in una SPA React con dark theme.

---

## Stack tecnico

| Layer      | Tecnologia                                      |
|------------|-------------------------------------------------|
| Backend    | Python 3.12 · FastAPI · imaplib                 |
| Frontend   | React 18 · Recharts · Leaflet · JetBrains Mono  |
| Storage    | SQLite (default) oppure PostgreSQL              |
| Geo lookup | ip-api.com (gratuito, nessuna chiave richiesta) |
| Container  | Docker multi-stage (Node 18 + Python 3.12-slim) |
| Deploy     | Helm chart v0.4.0 (Rancher-ready)               |

---

## Funzionalità

### Cruscotto principale (tab Overview)
- **6 KPI cards** — messaggi totali, DKIM pass %, SPF pass %, consegnati, quarantena, rifiutati
- **Filtro dominio** — ricerca con autocomplete sui domini presenti nel DB; filtra in tempo reale tutti i widget
- **Filtri temporali** — 1g / 7g / 14g / 30g / 90g
- **Alert policy** — domini con `p=none` e riepilogo reject/quarantena per dominio
- **Timeline** — area chart giornaliero per disposizione (consegnati / quarantena / rifiutati)
- **Bar chart per dominio** — disposizione aggregata, top 10 domini
- **Mappa geografica** — sorgenti IP su CartoDB dark, marker colorati per disposizione, popup con dettaglio
- **Tabella IP sorgenti** — ordinabile, filtrabile, con badge DKIM/SPF/disposizione e geolocalizzazione

### Tab Reject / Quarantena
- Tabella dettagliata di tutti i record con `disposition = reject | quarantine`
- Filtro rapido per tipo (tutti / reject / quarantine) e ricerca full-text
- Per ogni record: dominio, IP sorgente, conteggi, DKIM/SPF, header from, paese
- **Dettaglio IMAP** — espandendo la riga si vedono i metadati dell'email che trasportava il report: `From:`, `To:`, `Subject:`
- Colonne ordinabili per data, dominio, IP, conteggio

### Gestione mailbox
- Polling automatico configurabile (default ogni 5 minuti)
- Sync manuale dal pulsante in header
- Email processate spostate automaticamente nella cartella `Processed` (root level, creata automaticamente se non esiste)
- Deduplicazione report tramite `report_id`
- Log degli ultimi 20 sync in `/api/fetch_log`

### Filtro temporale — nota semantica
Il filtro è applicato su `date_end` (non `date_begin`) del report DMARC.  
Questo garantisce che un report che copre ieri (arrivato stamattina) sia visibile nel filtro **1g**, anche se il suo `date_begin` è fuori dalla finestra.

---

## Struttura del progetto

```
dmarc-dashboard/
├── backend/
│   ├── main.py            # FastAPI app: IMAP poller, parser XML, API REST
│   └── requirements.txt
├── frontend/
│   ├── public/index.html
│   ├── .eslintrc.json
│   ├── package.json
│   └── src/
│       ├── App.js / App.css       # Layout, tab bar, domain filter
│       ├── index.js
│       ├── hooks/
│       │   └── useApi.js          # Fetch + auto-refresh
│       └── components/
│           ├── OverviewCards.js   # 6 KPI cards
│           ├── AlertsPanel.js     # Alert policy DMARC
│           ├── TimelineChart.js   # Area chart per giorno
│           ├── DomainChart.js     # Bar chart per dominio
│           ├── GeoMap.js          # Mappa Leaflet CartoDB dark
│           ├── SourcesTable.js    # Tabella IP sorgenti
│           └── RejectDetail.js    # Dettaglio reject/quarantena con expand
├── Dockerfile             # Multi-stage: Node 18 build → Python 3.12 serve
├── docker-compose.yml     # Per test locale con .env
└── helm/                  # Helm chart v0.4.0
    ├── Chart.yaml
    ├── values.yaml
    ├── questions.yaml     # Form Rancher (5 gruppi)
    └── templates/
        ├── _helpers.tpl
        ├── secret.yaml            # Secret IMAP + Secret PG (condizionale)
        ├── deployment.yaml        # Env var condizionali per DB backend
        └── service-ingress-pvc.yaml
```

---

## Avvio locale con Docker Compose

```bash
# 1. Clona / estrai il progetto
tar xzf dmarc-dashboard.tar.gz && cd dmarc-dashboard

# 2. Crea il file .env
cat > .env << EOF
IMAP_HOST=mail.example.com
IMAP_PORT=993
IMAP_USER=dmarc@example.com
IMAP_PASS=password_sicura
IMAP_FOLDER=INBOX
IMAP_PROCESSED_FOLDER=Processed
IMAP_USE_SSL=true
POLL_INTERVAL_SECONDS=300
DB_BACKEND=sqlite
EOF

# 3. Build e avvio
docker compose up -d --build

# Dashboard disponibile su http://localhost:8000
```

---

## Deploy su Kubernetes via Rancher / Helm

### 1. Build e push dell'immagine

```bash
docker build -t registry.example.com/dmarc-dashboard:latest .
docker push registry.example.com/dmarc-dashboard:latest
```

### 2. Deploy da Rancher Apps

1. Aggiungi il repository Gitea come **Helm Chart Repository** in Rancher  
   *(Apps → Repositories → Add → URL del tuo Gitea)*
2. Vai su **Apps → Charts**, cerca `dmarc-dashboard`
3. Compila il form (5 gruppi: Immagine, Connessione IMAP, Database, Ingress, Storage, Risorse)
4. Le password finiscono automaticamente in Secret Kubernetes separati (`-imap`, `-pg`)

### 3. Deploy da CLI

```bash
# Crea i namespace se necessario
kubectl create namespace dmarc

helm upgrade --install dmarc-dashboard ./helm \
  -n dmarc \
  --create-namespace \
  -f helm/values.yaml \
  --set image.repository=registry.example.com/dmarc-dashboard \
  --set imap.host=mail.example.com \
  --set imap.user=dmarc@example.com \
  --set imap.password=PASSWORD \
  --set ingress.host=dmarc.example.com
```

---

## Variabili d'ambiente

| Variabile               | Default          | Descrizione                                           |
|-------------------------|------------------|-------------------------------------------------------|
| `IMAP_HOST`             | —                | Hostname server IMAP                                  |
| `IMAP_PORT`             | `993`            | Porta IMAP                                            |
| `IMAP_USER`             | —                | Indirizzo email / username                            |
| `IMAP_PASS`             | —                | Password (usa un Secret K8s in produzione)            |
| `IMAP_FOLDER`           | `INBOX`          | Cartella IMAP da cui leggere i report                 |
| `IMAP_PROCESSED_FOLDER` | `Processed`      | Cartella root dove spostare le email processate       |
| `IMAP_USE_SSL`          | `true`           | Abilita SSL/TLS                                       |
| `POLL_INTERVAL_SECONDS` | `300`            | Frequenza polling IMAP in secondi                     |
| `DB_BACKEND`            | `sqlite`         | Backend DB: `sqlite` oppure `postgres`                |
| `DB_PATH`               | `/data/dmarc.db` | Percorso SQLite (solo se `DB_BACKEND=sqlite`)         |
| `PG_HOST`               | `localhost`      | Host PostgreSQL (solo se `DB_BACKEND=postgres`)       |
| `PG_PORT`               | `5432`           | Porta PostgreSQL                                      |
| `PG_DB`                 | `dmarc`          | Nome database PostgreSQL                              |
| `PG_USER`               | `dmarc`          | Utente PostgreSQL                                     |
| `PG_PASS`               | —                | Password PostgreSQL                                   |
| `PG_SSLMODE`            | `prefer`         | SSL mode PostgreSQL                                   |

---

## Schema database

### Tabella `reports`

| Colonna        | Tipo    | Descrizione                                          |
|----------------|---------|------------------------------------------------------|
| `report_id`    | TEXT    | ID univoco del report DMARC (chiave dedup)           |
| `org_name`     | TEXT    | Organizzazione che ha inviato il report (es. Google) |
| `domain`       | TEXT    | Dominio DMARC monitorato                             |
| `date_begin`   | INTEGER | Inizio periodo report (Unix timestamp)               |
| `date_end`     | INTEGER | Fine periodo report (Unix timestamp)                 |
| `policy_p`     | TEXT    | Policy DMARC: `none` / `quarantine` / `reject`       |
| `policy_sp`    | TEXT    | Policy subdomain                                     |
| `policy_pct`   | INTEGER | Percentuale di applicazione policy                   |
| `imap_from`    | TEXT    | Header `From:` dell'email IMAP portante              |
| `imap_to`      | TEXT    | Header `To:` dell'email IMAP portante                |
| `imap_subject` | TEXT    | Header `Subject:` dell'email IMAP portante           |
| `fetched_at`   | TEXT    | Timestamp import (UTC ISO)                           |

### Tabella `records`

| Colonna        | Tipo  | Descrizione                              |
|----------------|-------|------------------------------------------|
| `source_ip`    | TEXT  | IP sorgente del messaggio                |
| `count`        | INT   | Numero messaggi nel record               |
| `disposition`  | TEXT  | `none` / `quarantine` / `reject`         |
| `dkim_result`  | TEXT  | `pass` / `fail` / `unknown`              |
| `spf_result`   | TEXT  | `pass` / `fail` / `unknown`              |
| `header_from`  | TEXT  | Header From del messaggio originale      |
| `envelope_from`| TEXT  | Envelope From (MAIL FROM SMTP)           |
| `geo_country`  | TEXT  | Paese risolto via ip-api.com             |
| `geo_lat`      | REAL  | Latitudine                               |
| `geo_lon`      | REAL  | Longitudine                              |

> **Upgrade da versioni precedenti**: le colonne `imap_from`, `imap_to`, `imap_subject`  
> vengono aggiunte automaticamente via `ALTER TABLE` all'avvio se non presenti.  
> I report già importati avranno quei campi a `NULL`.

---

## API REST

Tutti gli endpoint statistici accettano i parametri opzionali `?days=N` (default 30) e `?domain=example.com`.

| Metodo | Endpoint                 | Descrizione                                          |
|--------|--------------------------|------------------------------------------------------|
| GET    | `/api/stats/domains`     | Lista domini distinti nel periodo                    |
| GET    | `/api/stats/overview`    | KPI aggregati: totali, DKIM/SPF pass, disposizioni   |
| GET    | `/api/stats/timeline`    | Dati giornalieri per area chart                      |
| GET    | `/api/stats/by_domain`   | Disposizione aggregata per dominio                   |
| GET    | `/api/stats/sources`     | Tabella IP sorgenti con geo (`?limit=N`)             |
| GET    | `/api/stats/geo`         | Punti per mappa geografica                           |
| GET    | `/api/alerts`            | Policy non enforced + riepilogo failing deliveries   |
| GET    | `/api/rejects`           | Dettaglio record reject/quarantena con campi IMAP    |
| GET    | `/api/fetch_log`         | Log ultimi 20 sync IMAP                              |
| POST   | `/api/fetch_now`         | Avvia sync IMAP manuale (background task)            |
| GET    | `/api/db_info`           | Backend DB attivo e host                             |

---

## Configurazione DNS DMARC

Per ricevere i report nella mailbox configurata, il record DNS del dominio deve includere il tag `rua`:

```
_dmarc.example.com TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com"
```

Gli ESP (Google, Microsoft, Yahoo, ecc.) inviano report aggregati giornalieri come allegati `.xml.gz` o `.zip`.  
Il backend supporta entrambi i formati.

---

## Changelog

| Versione | Modifiche                                                                         |
|----------|-----------------------------------------------------------------------------------|
| 0.4.0    | Tab Reject/Quarantena con dettaglio IMAP (From/To/Subject); migrazione automatica schema |
| 0.3.0    | Filtro dominio con autocomplete; filtro 1g aggiunto; fix cluster-issuer `letsencrypt-production` |
| 0.2.0    | Supporto PostgreSQL; `questions.yaml` Rancher; Secret K8s generati dal chart; spostamento email in cartella `Processed` |
| 0.1.0    | Release iniziale: IMAP poller, parser DMARC XML, dashboard React, Helm chart base  |

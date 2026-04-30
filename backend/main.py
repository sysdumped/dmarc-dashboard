import os
import threading
import time
import gzip
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional
import email
import imaplib

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import requests

app = FastAPI(title="DMARC Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

IMAP_HOST            = os.environ.get("IMAP_HOST", "")
IMAP_PORT            = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER            = os.environ.get("IMAP_USER", "")
IMAP_PASS            = os.environ.get("IMAP_PASS", "")
IMAP_FOLDER          = os.environ.get("IMAP_FOLDER", "INBOX")
IMAP_PROCESSED_FOLDER = os.environ.get("IMAP_PROCESSED_FOLDER", "Processed")
IMAP_USE_SSL         = os.environ.get("IMAP_USE_SSL", "true").lower() == "true"
POLL_INTERVAL        = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))

# DB backend: "sqlite" (default) or "postgres"
DB_BACKEND           = os.environ.get("DB_BACKEND", "sqlite").lower()

# SQLite
DB_PATH              = os.environ.get("DB_PATH", "/data/dmarc.db")

# PostgreSQL
PG_HOST              = os.environ.get("PG_HOST", "localhost")
PG_PORT              = int(os.environ.get("PG_PORT", "5432"))
PG_DB                = os.environ.get("PG_DB", "dmarc")
PG_USER              = os.environ.get("PG_USER", "dmarc")
PG_PASS              = os.environ.get("PG_PASS", "")
PG_SSLMODE           = os.environ.get("PG_SSLMODE", "prefer")

# ---------------------------------------------------------------------------
# DATABASE ABSTRACTION
# ---------------------------------------------------------------------------
# Both backends expose the same interface:
#   get_db()  -> connection (context-manager safe)
#   ph(n)     -> placeholder string for n positional params ("?,?,?" / "%s,%s,%s")
#   lastrowid(cursor) -> last inserted id
#   executescript(conn, sql) -> run DDL (SQLite) or split+execute (PG)
# ---------------------------------------------------------------------------

if DB_BACKEND == "postgres":
    import psycopg2
    import psycopg2.extras

    def get_db():
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS, sslmode=PG_SSLMODE,
        )
        conn.autocommit = False
        return conn

    def ph(n: int = 1) -> str:
        return ",".join(["%s"] * n)

    def row_factory(cursor, row):
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))

    def fetchall_dict(cursor):
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetchone_val(cursor):
        row = cursor.fetchone()
        return row[0] if row else None

    def init_db():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id          SERIAL PRIMARY KEY,
                report_id   TEXT UNIQUE,
                org_name    TEXT,
                email       TEXT,
                domain      TEXT,
                date_begin  BIGINT,
                date_end    BIGINT,
                policy_p    TEXT,
                policy_sp   TEXT,
                policy_pct  INTEGER,
                fetched_at  TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id            SERIAL PRIMARY KEY,
                report_id     TEXT REFERENCES reports(report_id),
                source_ip     TEXT,
                count         INTEGER,
                disposition   TEXT,
                dkim_result   TEXT,
                spf_result    TEXT,
                header_from   TEXT,
                envelope_from TEXT,
                geo_country   TEXT,
                geo_lat       DOUBLE PRECISION,
                geo_lon       DOUBLE PRECISION
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fetch_log (
                id          SERIAL PRIMARY KEY,
                fetched_at  TEXT,
                new_reports INTEGER,
                errors      TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()

    PH = "%s"

else:
    import sqlite3

    def get_db():
        os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def fetchall_dict(cursor):
        return [dict(r) for r in cursor.fetchall()]

    def fetchone_val(cursor):
        row = cursor.fetchone()
        return row[0] if row else None

    def init_db():
        conn = get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id   TEXT UNIQUE,
                org_name    TEXT,
                email       TEXT,
                domain      TEXT,
                date_begin  INTEGER,
                date_end    INTEGER,
                policy_p    TEXT,
                policy_sp   TEXT,
                policy_pct  INTEGER,
                fetched_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS records (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id     TEXT REFERENCES reports(report_id),
                source_ip     TEXT,
                count         INTEGER,
                disposition   TEXT,
                dkim_result   TEXT,
                spf_result    TEXT,
                header_from   TEXT,
                envelope_from TEXT,
                geo_country   TEXT,
                geo_lat       REAL,
                geo_lon       REAL
            );
            CREATE TABLE IF NOT EXISTS fetch_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at  TEXT,
                new_reports INTEGER,
                errors      TEXT
            );
        """)
        conn.commit()
        conn.close()

    PH = "?"

def _ph(*args):
    """Return a comma-separated placeholder string for len(args) values."""
    return ", ".join([PH] * len(args))

# ---------------------------------------------------------------------------
# GEO LOOKUP
# ---------------------------------------------------------------------------

_geo_cache: dict = {}

def geo_lookup(ip: str) -> dict:
    if ip in _geo_cache:
        return _geo_cache[ip]
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=country,countryCode,lat,lon",
            timeout=4,
        )
        if r.status_code == 200:
            data = r.json()
            result = {
                "country": data.get("country", ""),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
            }
            _geo_cache[ip] = result
            return result
    except Exception:
        pass
    return {"country": "", "lat": None, "lon": None}

# ---------------------------------------------------------------------------
# DMARC XML PARSER
# ---------------------------------------------------------------------------

def parse_dmarc_xml(xml_bytes: bytes) -> Optional[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    meta   = root.find("report_metadata")
    policy = root.find("policy_published")
    if meta is None or policy is None:
        return None

    report = {
        "report_id":  (meta.findtext("report_id") or "").strip(),
        "org_name":   (meta.findtext("org_name") or "").strip(),
        "email":      (meta.findtext("email") or "").strip(),
        "domain":     (policy.findtext("domain") or "").strip(),
        "date_begin": int(meta.findtext("date_range/begin") or 0),
        "date_end":   int(meta.findtext("date_range/end") or 0),
        "policy_p":   (policy.findtext("p") or "none").strip(),
        "policy_sp":  (policy.findtext("sp") or "none").strip(),
        "policy_pct": int(policy.findtext("pct") or 100),
        "records": [],
    }

    for rec in root.findall("record"):
        row        = rec.find("row")
        policy_ev  = rec.find("row/policy_evaluated")
        auth       = rec.find("auth_results")
        identifiers= rec.find("identifiers")
        if row is None:
            continue

        dkim_result = "unknown"
        spf_result  = "unknown"
        if auth is not None:
            dkim_el = auth.find("dkim/result")
            spf_el  = auth.find("spf/result")
            if dkim_el is not None: dkim_result = (dkim_el.text or "unknown").strip()
            if spf_el  is not None: spf_result  = (spf_el.text  or "unknown").strip()

        report["records"].append({
            "source_ip":     (row.findtext("source_ip") or "").strip(),
            "count":         int(row.findtext("count") or 0),
            "disposition":   (policy_ev.findtext("disposition") if policy_ev is not None else "") or "none",
            "dkim_result":   dkim_result,
            "spf_result":    spf_result,
            "header_from":   (identifiers.findtext("header_from")   if identifiers is not None else "") or "",
            "envelope_from": (identifiers.findtext("envelope_from") if identifiers is not None else "") or "",
        })

    return report


def extract_xml_from_attachment(payload: bytes, filename: str) -> Optional[bytes]:
    fname = (filename or "").lower()
    try:
        if fname.endswith(".gz"):
            return gzip.decompress(payload)
        if fname.endswith(".zip"):
            with zipfile.ZipFile(BytesIO(payload)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        return zf.read(name)
        if fname.endswith(".xml"):
            return payload
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# IMAP FETCHER
# ---------------------------------------------------------------------------

def _imap_ensure_folder(mail, folder: str) -> bool:
    """Create folder if it does not exist. Returns True on success."""
    typ, _ = mail.select(folder)
    if typ == "OK":
        return True
    # Folder missing — create it at root level (not under INBOX)
    typ, data = mail.create(folder)
    if typ != "OK":
        return False
    mail.subscribe(folder)
    return True


def fetch_reports_from_imap() -> tuple[int, list[str]]:
    if not IMAP_HOST or not IMAP_USER or not IMAP_PASS:
        return 0, ["IMAP not configured"]

    errors    = []
    new_count = 0

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) if IMAP_USE_SSL else imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)

        # Ensure the Processed folder exists at root level before starting
        if not _imap_ensure_folder(mail, IMAP_PROCESSED_FOLDER):
            errors.append(f"Cannot create/access folder: {IMAP_PROCESSED_FOLDER}")
            mail.logout()
            return 0, errors

        # Re-select the source folder after the ensure_folder call
        mail.select(IMAP_FOLDER)

        _, data = mail.search(None, "ALL")
        ids = data[0].split()

        conn = get_db()
        cur  = conn.cursor()

        for msg_id in ids[-500:]:
            imported = False
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                for part in msg.walk():
                    ct      = part.get_content_type()
                    fname   = part.get_filename() or ""
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue

                    xml_bytes = None
                    if ct in ("application/gzip","application/x-gzip","application/zip",
                              "application/octet-stream","text/xml","application/xml") or fname:
                        xml_bytes = extract_xml_from_attachment(payload, fname)

                    if xml_bytes is None:
                        continue

                    report = parse_dmarc_xml(xml_bytes)
                    if not report or not report["report_id"]:
                        continue

                    # dedup
                    cur.execute(f"SELECT id FROM reports WHERE report_id={PH}", (report["report_id"],))
                    if cur.fetchone():
                        # Already imported — still move to Processed to keep inbox clean
                        imported = True
                        continue

                    fetched_at = datetime.utcnow().isoformat()
                    cur.execute(f"""
                        INSERT INTO reports
                          (report_id,org_name,email,domain,date_begin,date_end,
                           policy_p,policy_sp,policy_pct,fetched_at)
                        VALUES ({_ph(*[0]*10)})
                    """, (
                        report["report_id"], report["org_name"], report["email"],
                        report["domain"], report["date_begin"], report["date_end"],
                        report["policy_p"], report["policy_sp"], report["policy_pct"],
                        fetched_at,
                    ))

                    for rec in report["records"]:
                        geo = geo_lookup(rec["source_ip"])
                        cur.execute(f"""
                            INSERT INTO records
                              (report_id,source_ip,count,disposition,dkim_result,spf_result,
                               header_from,envelope_from,geo_country,geo_lat,geo_lon)
                            VALUES ({_ph(*[0]*11)})
                        """, (
                            report["report_id"], rec["source_ip"], rec["count"],
                            rec["disposition"], rec["dkim_result"], rec["spf_result"],
                            rec["header_from"], rec["envelope_from"],
                            geo["country"], geo["lat"], geo["lon"],
                        ))

                    conn.commit()
                    new_count += 1
                    imported = True

            except Exception as e:
                errors.append(str(e))
                continue

            # Move message to Processed folder if it contained a DMARC report
            # (imported = True covers both new inserts and already-known duplicates)
            if imported:
                try:
                    # IMAP COPY + mark original as \Deleted + EXPUNGE
                    result = mail.copy(msg_id, IMAP_PROCESSED_FOLDER)
                    if result[0] == "OK":
                        mail.store(msg_id, "+FLAGS", "\\Deleted")
                    else:
                        errors.append(f"COPY to {IMAP_PROCESSED_FOLDER} failed for msg {msg_id}: {result}")
                except Exception as e:
                    errors.append(f"Move failed for msg {msg_id}: {e}")

        # Expunge deleted messages from source folder in one shot
        mail.expunge()

        cur.execute(
            f"INSERT INTO fetch_log (fetched_at,new_reports,errors) VALUES ({_ph(*[0]*3)})",
            (datetime.utcnow().isoformat(), new_count, "; ".join(errors[:5])),
        )
        conn.commit()
        cur.close()
        conn.close()
        mail.logout()

    except Exception as e:
        errors.append(f"IMAP connection error: {e}")

    return new_count, errors


# ---------------------------------------------------------------------------
# BACKGROUND POLLER
# ---------------------------------------------------------------------------

def poller_loop():
    time.sleep(10)
    while True:
        try:
            fetch_reports_from_imap()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    init_db()
    threading.Thread(target=poller_loop, daemon=True).start()


def _q(days: int):
    """Return UNIX timestamp for 'days ago'."""
    return int((datetime.utcnow() - timedelta(days=days)).timestamp())


@app.get("/api/stats/overview")
def overview(days: int = 30):
    since = _q(days)
    conn  = get_db()
    cur   = conn.cursor()

    cur.execute(f"""
        SELECT COALESCE(SUM(r.count),0) FROM records r
        JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= {PH}
    """, (since,))
    total_messages = fetchone_val(cur)

    cur.execute(f"""
        SELECT disposition, COALESCE(SUM(count),0) as n
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= {PH}
        GROUP BY disposition
    """, (since,))
    by_disp = fetchall_dict(cur)

    cur.execute(f"""
        SELECT COALESCE(SUM(count),0) FROM records r
        JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= {PH} AND r.dkim_result='pass'
    """, (since,))
    dkim_pass = fetchone_val(cur)

    cur.execute(f"""
        SELECT COALESCE(SUM(count),0) FROM records r
        JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= {PH} AND r.spf_result='pass'
    """, (since,))
    spf_pass = fetchone_val(cur)

    cur.execute(f"SELECT COUNT(*) FROM reports WHERE date_begin >= {PH}", (since,))
    report_count = fetchone_val(cur)

    cur.close(); conn.close()

    disp = {row["disposition"]: row["n"] for row in by_disp}
    return {
        "total_messages": total_messages,
        "report_count":   report_count,
        "dkim_pass":      dkim_pass,
        "spf_pass":       spf_pass,
        "disposition":    disp,
    }


@app.get("/api/stats/timeline")
def timeline(days: int = 30):
    since = _q(days)
    conn  = get_db()
    cur   = conn.cursor()

    if DB_BACKEND == "postgres":
        cur.execute(f"""
            SELECT TO_CHAR(TO_TIMESTAMP(p.date_begin),'YYYY-MM-DD') as day,
                   r.disposition, COALESCE(SUM(r.count),0) as n
            FROM records r JOIN reports p ON r.report_id=p.report_id
            WHERE p.date_begin >= {PH}
            GROUP BY day, r.disposition ORDER BY day
        """, (since,))
    else:
        cur.execute(f"""
            SELECT date(p.date_begin,'unixepoch') as day,
                   r.disposition, COALESCE(SUM(r.count),0) as n
            FROM records r JOIN reports p ON r.report_id=p.report_id
            WHERE p.date_begin >= {PH}
            GROUP BY day, r.disposition ORDER BY day
        """, (since,))

    rows = fetchall_dict(cur)
    cur.close(); conn.close()

    result = {}
    for row in rows:
        d = row["day"]
        if d not in result:
            result[d] = {"date": d, "none": 0, "quarantine": 0, "reject": 0}
        result[d][row["disposition"]] = row["n"]
    return list(result.values())


@app.get("/api/stats/by_domain")
def by_domain(days: int = 30):
    since = _q(days)
    conn  = get_db()
    cur   = conn.cursor()
    cur.execute(f"""
        SELECT p.domain, r.disposition, COALESCE(SUM(r.count),0) as n
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= {PH}
        GROUP BY p.domain, r.disposition
    """, (since,))
    rows = fetchall_dict(cur)
    cur.close(); conn.close()

    domains = {}
    for row in rows:
        d = row["domain"]
        if d not in domains:
            domains[d] = {"domain": d, "none": 0, "quarantine": 0, "reject": 0}
        domains[d][row["disposition"]] = row["n"]
    return list(domains.values())


@app.get("/api/stats/sources")
def sources(days: int = 30, limit: int = 100):
    since = _q(days)
    conn  = get_db()
    cur   = conn.cursor()

    if DB_BACKEND == "postgres":
        cur.execute(f"""
            SELECT r.source_ip, COALESCE(SUM(r.count),0) as total,
                   r.dkim_result, r.spf_result, r.disposition,
                   r.geo_country, r.geo_lat, r.geo_lon,
                   STRING_AGG(DISTINCT p.domain, ',') as domains
            FROM records r JOIN reports p ON r.report_id=p.report_id
            WHERE p.date_begin >= {PH}
            GROUP BY r.source_ip,r.dkim_result,r.spf_result,r.disposition,r.geo_country,r.geo_lat,r.geo_lon
            ORDER BY total DESC LIMIT {PH}
        """, (since, limit))
    else:
        cur.execute(f"""
            SELECT r.source_ip, COALESCE(SUM(r.count),0) as total,
                   r.dkim_result, r.spf_result, r.disposition,
                   r.geo_country, r.geo_lat, r.geo_lon,
                   GROUP_CONCAT(DISTINCT p.domain) as domains
            FROM records r JOIN reports p ON r.report_id=p.report_id
            WHERE p.date_begin >= {PH}
            GROUP BY r.source_ip,r.dkim_result,r.spf_result,r.disposition
            ORDER BY total DESC LIMIT {PH}
        """, (since, limit))

    rows = fetchall_dict(cur)
    cur.close(); conn.close()
    return rows


@app.get("/api/stats/geo")
def geo(days: int = 30):
    since = _q(days)
    conn  = get_db()
    cur   = conn.cursor()
    cur.execute(f"""
        SELECT r.geo_lat, r.geo_lon, r.geo_country,
               r.disposition, COALESCE(SUM(r.count),0) as total
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= {PH} AND r.geo_lat IS NOT NULL
        GROUP BY r.geo_lat, r.geo_lon, r.geo_country, r.disposition
    """, (since,))
    rows = fetchall_dict(cur)
    cur.close(); conn.close()
    return rows


@app.get("/api/alerts")
def alerts(days: int = 30):
    since = _q(days)
    conn  = get_db()
    cur   = conn.cursor()

    cur.execute(f"""
        SELECT p.domain, p.policy_p, r.disposition, SUM(r.count) as n
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= {PH} AND r.disposition IN ('reject','quarantine')
        GROUP BY p.domain, p.policy_p, r.disposition ORDER BY n DESC
    """, (since,))
    failing = fetchall_dict(cur)

    cur.execute(f"""
        SELECT DISTINCT domain, policy_p FROM reports
        WHERE date_begin >= {PH} AND policy_p='none'
    """, (since,))
    not_enforced = fetchall_dict(cur)

    cur.close(); conn.close()
    return {"failing_deliveries": failing, "unenforced_policies": not_enforced}


@app.get("/api/fetch_log")
def fetch_log():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM fetch_log ORDER BY id DESC LIMIT 20")
    rows = fetchall_dict(cur)
    cur.close(); conn.close()
    return rows


@app.post("/api/fetch_now")
def fetch_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_reports_from_imap)
    return {"status": "fetch started"}


@app.get("/api/db_info")
def db_info():
    return {"backend": DB_BACKEND, "host": PG_HOST if DB_BACKEND == "postgres" else "local"}


# Serve React SPA
try:
    app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="static")
except Exception:
    pass

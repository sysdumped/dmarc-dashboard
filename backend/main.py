import os
import sqlite3
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

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests

app = FastAPI(title="DMARC Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.environ.get("DB_PATH", "/data/dmarc.db")
IMAP_HOST = os.environ.get("IMAP_HOST", "")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ.get("IMAP_USER", "")
IMAP_PASS = os.environ.get("IMAP_PASS", "")
IMAP_FOLDER = os.environ.get("IMAP_FOLDER", "INBOX")
IMAP_USE_SSL = os.environ.get("IMAP_USE_SSL", "true").lower() == "true"
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id       TEXT UNIQUE,
            org_name        TEXT,
            email           TEXT,
            domain          TEXT,
            date_begin      INTEGER,
            date_end        INTEGER,
            policy_p        TEXT,
            policy_sp       TEXT,
            policy_pct      INTEGER,
            fetched_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id       TEXT REFERENCES reports(report_id),
            source_ip       TEXT,
            count           INTEGER,
            disposition     TEXT,
            dkim_result     TEXT,
            spf_result      TEXT,
            header_from     TEXT,
            envelope_from   TEXT,
            geo_country     TEXT,
            geo_lat         REAL,
            geo_lon         REAL
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

# ---------------------------------------------------------------------------
# GEO LOOKUP  (ip-api.com, free, no key required)
# ---------------------------------------------------------------------------

_geo_cache: dict = {}

def geo_lookup(ip: str) -> dict:
    if ip in _geo_cache:
        return _geo_cache[ip]
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=country,countryCode,lat,lon", timeout=4)
        if r.status_code == 200:
            data = r.json()
            result = {
                "country": data.get("country", ""),
                "country_code": data.get("countryCode", ""),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
            }
            _geo_cache[ip] = result
            return result
    except Exception:
        pass
    return {"country": "", "country_code": "", "lat": None, "lon": None}

# ---------------------------------------------------------------------------
# DMARC XML PARSER
# ---------------------------------------------------------------------------

def parse_dmarc_xml(xml_bytes: bytes) -> Optional[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    meta = root.find("report_metadata")
    policy = root.find("policy_published")

    if meta is None or policy is None:
        return None

    report = {
        "report_id": (meta.findtext("report_id") or "").strip(),
        "org_name": (meta.findtext("org_name") or "").strip(),
        "email": (meta.findtext("email") or "").strip(),
        "domain": (policy.findtext("domain") or "").strip(),
        "date_begin": int(meta.findtext("date_range/begin") or 0),
        "date_end": int(meta.findtext("date_range/end") or 0),
        "policy_p": (policy.findtext("p") or "none").strip(),
        "policy_sp": (policy.findtext("sp") or "none").strip(),
        "policy_pct": int(policy.findtext("pct") or 100),
        "records": [],
    }

    for rec in root.findall("record"):
        row = rec.find("row")
        if row is None:
            continue
        policy_eval = rec.find("row/policy_evaluated")
        auth = rec.find("auth_results")
        identifiers = rec.find("identifiers")

        dkim_result = "unknown"
        spf_result = "unknown"
        if auth is not None:
            dkim_el = auth.find("dkim/result")
            spf_el = auth.find("spf/result")
            if dkim_el is not None:
                dkim_result = dkim_el.text or "unknown"
            if spf_el is not None:
                spf_result = spf_el.text or "unknown"

        record = {
            "source_ip": (row.findtext("source_ip") or "").strip(),
            "count": int(row.findtext("count") or 0),
            "disposition": (policy_eval.findtext("disposition") if policy_eval is not None else "") or "none",
            "dkim_result": dkim_result.strip(),
            "spf_result": spf_result.strip(),
            "header_from": (identifiers.findtext("header_from") if identifiers is not None else "") or "",
            "envelope_from": (identifiers.findtext("envelope_from") if identifiers is not None else "") or "",
        }
        report["records"].append(record)

    return report

def extract_xml_from_attachment(payload: bytes, filename: str) -> Optional[bytes]:
    fname = (filename or "").lower()
    try:
        if fname.endswith(".gz") or fname.endswith(".xml.gz"):
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

def fetch_reports_from_imap() -> tuple[int, list[str]]:
    if not IMAP_HOST or not IMAP_USER or not IMAP_PASS:
        return 0, ["IMAP not configured"]

    errors = []
    new_count = 0

    try:
        if IMAP_USE_SSL:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        else:
            mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(IMAP_FOLDER)

        _, data = mail.search(None, "ALL")
        ids = data[0].split()

        conn = get_db()
        for msg_id in ids[-500:]:  # cap at last 500 emails
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                for part in msg.walk():
                    ct = part.get_content_type()
                    fname = part.get_filename() or ""
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue

                    xml_bytes = None
                    if ct in ("application/gzip", "application/x-gzip", "application/zip",
                              "application/octet-stream", "text/xml", "application/xml"):
                        xml_bytes = extract_xml_from_attachment(payload, fname)
                    elif fname:
                        xml_bytes = extract_xml_from_attachment(payload, fname)

                    if xml_bytes is None:
                        continue

                    report = parse_dmarc_xml(xml_bytes)
                    if not report or not report["report_id"]:
                        continue

                    # Check duplicate
                    existing = conn.execute(
                        "SELECT id FROM reports WHERE report_id=?", (report["report_id"],)
                    ).fetchone()
                    if existing:
                        continue

                    fetched_at = datetime.utcnow().isoformat()
                    conn.execute("""
                        INSERT INTO reports
                          (report_id, org_name, email, domain, date_begin, date_end,
                           policy_p, policy_sp, policy_pct, fetched_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (
                        report["report_id"], report["org_name"], report["email"],
                        report["domain"], report["date_begin"], report["date_end"],
                        report["policy_p"], report["policy_sp"], report["policy_pct"],
                        fetched_at,
                    ))

                    for rec in report["records"]:
                        geo = geo_lookup(rec["source_ip"])
                        conn.execute("""
                            INSERT INTO records
                              (report_id, source_ip, count, disposition,
                               dkim_result, spf_result, header_from, envelope_from,
                               geo_country, geo_lat, geo_lon)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            report["report_id"], rec["source_ip"], rec["count"],
                            rec["disposition"], rec["dkim_result"], rec["spf_result"],
                            rec["header_from"], rec["envelope_from"],
                            geo["country"], geo["lat"], geo["lon"],
                        ))

                    conn.commit()
                    new_count += 1

            except Exception as e:
                errors.append(str(e))

        conn.close()
        mail.logout()

    except Exception as e:
        errors.append(f"IMAP connection error: {e}")

    conn2 = get_db()
    conn2.execute(
        "INSERT INTO fetch_log (fetched_at, new_reports, errors) VALUES (?,?,?)",
        (datetime.utcnow().isoformat(), new_count, "; ".join(errors[:5])),
    )
    conn2.commit()
    conn2.close()

    return new_count, errors

# ---------------------------------------------------------------------------
# BACKGROUND POLLER
# ---------------------------------------------------------------------------

def poller_loop():
    time.sleep(10)  # wait for app startup
    while True:
        try:
            fetch_reports_from_imap()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)

# ---------------------------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    init_db()
    t = threading.Thread(target=poller_loop, daemon=True)
    t.start()


@app.get("/api/stats/overview")
def overview(days: int = 30):
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    conn = get_db()

    total_msgs = conn.execute("""
        SELECT COALESCE(SUM(r.count),0) FROM records r
        JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ?
    """, (since,)).fetchone()[0]

    by_disposition = conn.execute("""
        SELECT disposition, COALESCE(SUM(count),0) as n
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ?
        GROUP BY disposition
    """, (since,)).fetchall()

    dkim_pass = conn.execute("""
        SELECT COALESCE(SUM(count),0) FROM records r
        JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ? AND r.dkim_result='pass'
    """, (since,)).fetchone()[0]

    spf_pass = conn.execute("""
        SELECT COALESCE(SUM(count),0) FROM records r
        JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ? AND r.spf_result='pass'
    """, (since,)).fetchone()[0]

    report_count = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE date_begin >= ?", (since,)
    ).fetchone()[0]

    conn.close()

    disp = {row["disposition"]: row["n"] for row in by_disposition}
    return {
        "total_messages": total_msgs,
        "report_count": report_count,
        "dkim_pass": dkim_pass,
        "spf_pass": spf_pass,
        "disposition": disp,
    }


@app.get("/api/stats/timeline")
def timeline(days: int = 30):
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    conn = get_db()
    rows = conn.execute("""
        SELECT
            date(p.date_begin, 'unixepoch') as day,
            r.disposition,
            COALESCE(SUM(r.count),0) as n
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ?
        GROUP BY day, r.disposition
        ORDER BY day
    """, (since,)).fetchall()
    conn.close()
    result = {}
    for row in rows:
        d = row["day"]
        if d not in result:
            result[d] = {"date": d, "none": 0, "quarantine": 0, "reject": 0}
        result[d][row["disposition"]] = row["n"]
    return list(result.values())


@app.get("/api/stats/by_domain")
def by_domain(days: int = 30):
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    conn = get_db()
    rows = conn.execute("""
        SELECT p.domain, r.disposition, COALESCE(SUM(r.count),0) as n
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ?
        GROUP BY p.domain, r.disposition
    """, (since,)).fetchall()
    conn.close()
    domains = {}
    for row in rows:
        d = row["domain"]
        if d not in domains:
            domains[d] = {"domain": d, "none": 0, "quarantine": 0, "reject": 0}
        domains[d][row["disposition"]] = row["n"]
    return list(domains.values())


@app.get("/api/stats/sources")
def sources(days: int = 30, limit: int = 100):
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    conn = get_db()
    rows = conn.execute("""
        SELECT r.source_ip, COALESCE(SUM(r.count),0) as total,
               r.dkim_result, r.spf_result, r.disposition,
               r.geo_country, r.geo_lat, r.geo_lon,
               GROUP_CONCAT(DISTINCT p.domain) as domains
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ?
        GROUP BY r.source_ip, r.dkim_result, r.spf_result, r.disposition
        ORDER BY total DESC
        LIMIT ?
    """, (since, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats/geo")
def geo(days: int = 30):
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    conn = get_db()
    rows = conn.execute("""
        SELECT r.geo_lat, r.geo_lon, r.geo_country,
               r.disposition, COALESCE(SUM(r.count),0) as total
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ? AND r.geo_lat IS NOT NULL
        GROUP BY r.geo_lat, r.geo_lon, r.disposition
    """, (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/alerts")
def alerts(days: int = 30):
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    conn = get_db()

    # Domains with reject/quarantine hits
    failing = conn.execute("""
        SELECT p.domain, p.policy_p, r.disposition, SUM(r.count) as n
        FROM records r JOIN reports p ON r.report_id=p.report_id
        WHERE p.date_begin >= ? AND r.disposition IN ('reject','quarantine')
        GROUP BY p.domain, r.disposition
        ORDER BY n DESC
    """, (since,)).fetchall()

    # Policy not enforced (p=none)
    not_enforced = conn.execute("""
        SELECT DISTINCT domain, policy_p FROM reports
        WHERE date_begin >= ? AND policy_p='none'
    """, (since,)).fetchall()

    conn.close()
    return {
        "failing_deliveries": [dict(r) for r in failing],
        "unenforced_policies": [dict(r) for r in not_enforced],
    }


@app.get("/api/fetch_log")
def fetch_log():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM fetch_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/fetch_now")
def fetch_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_reports_from_imap)
    return {"status": "fetch started"}


# Serve React frontend for everything else
@app.get("/")
def root():
    return FileResponse("/app/frontend/index.html")

try:
    app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="static")
except Exception:
    pass

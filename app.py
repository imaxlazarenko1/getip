import os
import requests
from flask import Flask, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1)

DATABASE_URL = os.environ.get("DATABASE_URL")


@app.route("/knock.wav")
def knock_file():
    return send_from_directory(".", "knock.wav")


def get_client_ip():
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def geo_lookup(ip):
    if ip.startswith(("10.", "127.", "192.168.", "172.")):
        return {}
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,country,countryCode,regionName,city,isp,lat,lon"},
            timeout=5,
        )
        d = r.json()
        if d.get("status") == "success":
            return d
    except Exception:
        pass
    return {}


def get_db():
    url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL else None
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS visits (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    ip TEXT NOT NULL,
                    user_agent TEXT,
                    country TEXT,
                    country_code TEXT,
                    region TEXT,
                    city TEXT,
                    isp TEXT,
                    lat DOUBLE PRECISION,
                    lon DOUBLE PRECISION
                );
            """)
            for col, typ in [
                ("country", "TEXT"), ("country_code", "TEXT"),
                ("region", "TEXT"), ("city", "TEXT"),
                ("isp", "TEXT"), ("lat", "DOUBLE PRECISION"), ("lon", "DOUBLE PRECISION"),
            ]:
                cur.execute(f"ALTER TABLE visits ADD COLUMN IF NOT EXISTS {col} {typ};")
        conn.commit()


def log_visit(ip, ua, geo):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO visits
                   (ts, ip, user_agent, country, country_code, region, city, isp, lat, lon)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
                (
                    datetime.now(timezone.utc), ip, ua,
                    geo.get("country"), geo.get("countryCode"),
                    geo.get("regionName"), geo.get("city"),
                    geo.get("isp"), geo.get("lat"), geo.get("lon"),
                )
            )
        conn.commit()


@app.route("/")
def index():
    ip = get_client_ip()
    ua = request.headers.get("User-Agent", "-")
    geo = geo_lookup(ip)
    log_visit(ip, ua, geo)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>getip</title>
</head>
<body>
  <h1>Slava Ukraine!</h1>
  <p>ip: {ip}</p>
  <p>ua: {ua}</p>
  <p>time: {datetime.now(timezone.utc).isoformat()}</p>

  <audio id="laugh" src="/knock.wav" preload="auto"></audio>
  <script>
    const laugh = document.getElementById("laugh");
    laugh.volume = 1.0;

    function tryPlay() {{
      laugh.play().catch(() => {{}});
    }}

    window.addEventListener("load", tryPlay);
    document.addEventListener("click", tryPlay, {{ once: true }});
  </script>
</body>
</html>
"""
    return html


@app.route("/log")
def view_log():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM visits ORDER BY ts DESC LIMIT 100;")
            rows = cur.fetchall()
    return {"count": len(rows), "visits": rows}


try:
    init_db()
except Exception as e:
    print(f"[init_db] {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

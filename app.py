import os
from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_client_ip():
    return request.remote_addr or "unknown"


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
                    user_agent TEXT
                );
            """)
        conn.commit()


def log_visit(ip, ua):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO visits (ts, ip, user_agent) VALUES (%s, %s, %s);",
                (datetime.now(timezone.utc), ip, ua)
            )
        conn.commit()


@app.route("/")
def index():
    ip = get_client_ip()
    ua = request.headers.get("User-Agent", "-")
    log_visit(ip, ua)  # в БД пишем только IP, UA, время — без фразы

    # Ответ пользователю — начинается с приветствия
    return f"Slava Ukraine!\n\nip: {ip}\nua: {ua}\ntime: {datetime.now(timezone.utc).isoformat()}\n"


@app.route("/log")
def view_log():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ts, ip, user_agent FROM visits ORDER BY ts DESC LIMIT 100;")
            rows = cur.fetchall()
    return {"count": len(rows), "visits": rows}


try:
    init_db()
except Exception as e:
    print(f"[init_db] {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

#!/bin/sh
# Container entrypoint: wait for Postgres, migrate, create admin user, then run CMD.
set -e

echo "==> Waiting for the database ..."
python - <<'PY'
import os
import socket
import time

if os.environ.get("DB_ENGINE", "postgres") == "sqlite":
    raise SystemExit(0)

host = os.environ.get("POSTGRES_HOST", "db")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
for attempt in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"    database is up at {host}:{port}")
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"Database {host}:{port} is not reachable")
PY

echo "==> Applying migrations ..."
python manage.py migrate --noinput

echo "==> Ensuring an admin user exists ..."
python manage.py ensure_superuser

exec "$@"

#!/bin/sh
# Migrations run on every boot. They are idempotent, and this keeps a fresh
# container (or a fresh volume mid-demo) from serving a schema-less database.
set -e

cd /app/backend

echo "[cadence] applying migrations..."
python manage.py migrate --noinput

# gunicorn needs the port wired to $PORT explicitly; runserver in compose
# passes its own bind address and skips this branch.
if [ "$1" = "gunicorn" ]; then
    shift
    exec gunicorn \
        --bind "0.0.0.0:${PORT:-8000}" \
        --workers "${WEB_CONCURRENCY:-2}" \
        --timeout "${GUNICORN_TIMEOUT:-120}" \
        --access-logfile - \
        --error-logfile - \
        "$@"
fi

exec "$@"

#!/bin/bash
echo "Starting RadMac application..."
echo "Waiting 15 seconds for database to initialize (RouterOS race condition mitigation)..."
sleep 15

echo "Running database migrations..."
python db_migrate.py

set -x
echo "Starting Flask development server (Debugging Gunicorn/App crash)..."
export FLASK_APP=wsgi:app
set -e
echo "Starting Gunicorn server on internal port 8042..."
exec gunicorn --bind 0.0.0.0:8042 wsgi:app --timeout 120 --workers 2

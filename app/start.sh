#!/bin/bash
echo "Starting RadMac application..."
echo "Waiting 15 seconds for database to initialize (RouterOS race condition mitigation)..."
sleep 15

echo "Running database migrations..."
python db_migrate.py

set -x
echo "Starting Flask development server (Debugging Gunicorn/App crash)..."
export FLASK_APP=wsgi:app
export FLASK_DEBUG=1
export PYTHONUNBUFFERED=1

if python -m flask run --host=0.0.0.0 --port=8042; then
  echo "Flask exited normally."
else
  echo "Flask CRASHED with exit code $?"
fi

echo "Keeping container alive for 60 seconds to allow reading RouterOS logs..."
sleep 60

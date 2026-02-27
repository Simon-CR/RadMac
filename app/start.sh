#!/bin/bash
echo "Starting RadMac application..."
echo "Waiting 15 seconds for database to initialize (RouterOS race condition mitigation)..."
sleep 15

echo "Running database migrations..."
python db_migrate.py

echo "Starting Gunicorn server..."
exec gunicorn --bind 0.0.0.0:8080 wsgi:app --timeout 120 --workers 2

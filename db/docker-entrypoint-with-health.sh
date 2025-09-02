#!/bin/bash
set -e

# Start the health endpoint in the background
echo "Starting health monitoring endpoint..."
python3 /usr/local/bin/health_endpoint.py &
HEALTH_PID=$!

# Function to cleanup background processes
cleanup() {
    echo "Shutting down health endpoint..."
    kill $HEALTH_PID 2>/dev/null || true
    wait $HEALTH_PID 2>/dev/null || true
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Start MariaDB using the original entrypoint
echo "Starting MariaDB..."
exec /usr/local/bin/docker-entrypoint.sh "$@" &
MARIADB_PID=$!

# Wait for MariaDB to exit
wait $MARIADB_PID

#!/bin/bash
# Simple health check script that returns HTTP responses
# This can be called by a lightweight HTTP server

check_mariadb() {
    mariadb-admin ping -h localhost -u root -p"${MARIADB_ROOT_PASSWORD}" >/dev/null 2>&1
    return $?
}

while true; do
    echo "HTTP/1.1 200 OK"
    echo "Content-Type: application/json"
    echo ""
    
    if check_mariadb; then
        echo '{"status":"healthy","service":"mariadb","timestamp":"'$(date -Iseconds)'"}'
    else
        echo "HTTP/1.1 503 Service Unavailable"
        echo "Content-Type: application/json"
        echo ""
        echo '{"status":"unhealthy","service":"mariadb","timestamp":"'$(date -Iseconds)'"}'
    fi
    
    # Simple HTTP server using netcat - listens once and exits
    break
done | nc -l -p 8080 -q 1

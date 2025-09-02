#!/bin/bash
# HTTP health check server using socat and mysqladmin
# Serves HTTP responses on port 8080 based on MySQL health

while true; do
    # Use socat to listen on port 8080 and serve HTTP responses
    socat TCP-LISTEN:8080,reuseaddr,fork EXEC:'/bin/bash -c "
        if mysqladmin ping -h localhost --silent 2>/dev/null; then
            echo -e \"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 44\r\n\r\n{\\\"status\\\":\\\"healthy\\\",\\\"message\\\":\\\"MySQL OK\\\"}\"
        else
            echo -e \"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\nContent-Length: 48\r\n\r\n{\\\"status\\\":\\\"unhealthy\\\",\\\"message\\\":\\\"MySQL down\\\"}\"
        fi
    "'
done

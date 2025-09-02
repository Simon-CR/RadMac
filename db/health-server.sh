#!/bin/bash
# HTTP health check server using netcat (nc) and mysqladmin
# Uses tools already available in the MariaDB base image

while true; do
    # Use netcat to listen on port 8080 and serve HTTP responses
    if mysqladmin ping -h localhost --silent 2>/dev/null; then
        echo -e "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 44\r\n\r\n{\"status\":\"healthy\",\"message\":\"MySQL OK\"}" | nc -l -p 8080 -q 1
    else
        echo -e "HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\nContent-Length: 48\r\n\r\n{\"status\":\"unhealthy\",\"message\":\"MySQL down\"}" | nc -l -p 8080 -q 1
    fi
    sleep 0.1
done

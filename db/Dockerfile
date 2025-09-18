FROM mariadb:latest

# Install additional tools for health monitoring  
RUN apt-get update && \
    apt-get install -y mariadb-client python3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy configuration files
COPY conf.d/ /etc/mysql/conf.d/
COPY init/ /docker-entrypoint-initdb.d/

# Copy health monitoring files
COPY health_endpoint.py /usr/local/bin/health_endpoint.py
COPY recovery_script.py /usr/local/bin/recovery_script.py

# Make health endpoint executable
RUN chmod +x /usr/local/bin/health_endpoint.py
RUN chmod +x /usr/local/bin/recovery_script.py

# Expose health monitoring port
EXPOSE 8080

# Use custom entrypoint that starts both MariaDB and health endpoint
COPY docker-entrypoint-with-health.sh /usr/local/bin/docker-entrypoint-with-health.sh
RUN chmod +x /usr/local/bin/docker-entrypoint-with-health.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint-with-health.sh"]
CMD ["mariadbd"]
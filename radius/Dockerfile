FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies (for mysql-connector, networking tools, and supervisord)
RUN apt-get update && \
    apt-get install -y gcc libmariadb-dev iputils-ping iproute2 supervisor curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy RADIUS service source code
COPY . .

# Expose RADIUS port (UDP)
EXPOSE 1812/udp

# Expose health endpoint port
EXPOSE 8080

# Copy supervisord config
COPY supervisord.conf /etc/supervisord.conf

# Start both RADIUS and health endpoint
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]

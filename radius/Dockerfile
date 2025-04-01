FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies (for mysql-connector and networking tools)
RUN apt-get update && \
    apt-get install -y gcc libmariadb-dev iputils-ping && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy RADIUS service source code
COPY . .

# Expose RADIUS port (UDP)
EXPOSE 1812/udp

# Run the RADIUS service
CMD ["python", "main.py"]

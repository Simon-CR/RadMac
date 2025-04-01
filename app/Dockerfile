FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Optional: Set timezone via build argument (can override in docker-compose)
ARG TIMEZONE=UTC
ENV TZ=$TIMEZONE

# Install tzdata and optional tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata iputils-ping telnet && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create logs directory (used if LOG_TO_FILE=true)
RUN mkdir -p /app/logs

# Copy dependencies and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose internal port (Gunicorn default)
EXPOSE 8080

# Run the app via Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "wsgi:app"]

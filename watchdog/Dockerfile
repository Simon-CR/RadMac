FROM python:3.9-slim

# Set working directory
WORKDIR /watchdog

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt



# Copy watchdog script
COPY watchdog.py .

# Only copy the example config if one does not already exist (for local/dev builds)
RUN [ ! -f /watchdog/watchdog_config.yaml ] && cp /watchdog/watchdog_config.yaml /watchdog/watchdog_config.yaml.example || true
COPY watchdog_config.yaml /watchdog/watchdog_config.yaml.example

# In production, always mount your own watchdog_config.yaml as a volume to avoid overwriting changes.

# Make script executable
RUN chmod +x watchdog.py

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash watchdog
USER watchdog

# Run the watchdog
CMD ["python", "watchdog.py"]

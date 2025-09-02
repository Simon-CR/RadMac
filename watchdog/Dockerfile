FROM python:3.9-slim

# Set working directory
WORKDIR /watchdog

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy watchdog script
COPY watchdog.py .

# Make script executable
RUN chmod +x watchdog.py

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash watchdog
USER watchdog

# Run the watchdog
CMD ["python", "watchdog.py"]

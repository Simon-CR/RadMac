FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Create logs directory
RUN mkdir -p /app/logs

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional tools (useful for debugging)
RUN apt-get update && apt-get install -y iputils-ping telnet && apt-get clean

# Copy application code
COPY . .

# Expose port (optional, for documentation)
EXPOSE 8080

# Default command to run app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "wsgi:app"]

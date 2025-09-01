# RadMac Watchdog

An optional health monitoring and automated remediation service for RadMac deployments.

## Features

- **Health Monitoring**: Polls the `/health` endpoint at configurable intervals
- **Smart Actions**: Different responses based on which service is unhealthy
- **Flexible Notifications**: Webhook support for Slack, Discord, email, etc.
- **Container Management**: Optional automatic container restarts
- **State Tracking**: Only acts on status changes, not every check
- **Configurable Limits**: Prevents infinite restart loops

## Configuration

All configuration is done via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WATCHDOG_HEALTH_URL` | `http://app:8080/health` | Health endpoint to monitor |
| `WATCHDOG_CHECK_INTERVAL` | `30` | Check interval in seconds |
| `WATCHDOG_ACTIONS` | `log` | Comma-separated actions: `log,webhook,restart` |
| `WATCHDOG_WEBHOOK_URL` | - | Webhook URL for notifications |
| `WATCHDOG_MAX_RESTART_ATTEMPTS` | `3` | Max container restarts before giving up |
| `WATCHDOG_CONTAINER_PREFIX` | `radmac` | Container name prefix for restart functionality |

## Available Actions

### `log` (Default)
- Logs health status changes
- Safe for all environments

### `webhook` 
- Sends JSON notifications to webhook URL
- Perfect for Slack, Discord, email services
- Includes health details and timestamps

### `restart`
- Automatically restarts unhealthy containers
- Requires Docker socket access (`/var/run/docker.sock`)
- Only restarts `app` and `database` services
- Respects restart attempt limits

## Usage

### 1. Log Only (Safest)
```yaml
watchdog:
  image: simonclr/radmac-watchdog:latest
  environment:
    - WATCHDOG_ACTIONS=log
```

### 2. With Slack Notifications
```yaml
watchdog:
  image: simonclr/radmac-watchdog:latest
  environment:
    - WATCHDOG_ACTIONS=log,webhook
    - WATCHDOG_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
```

### 3. Full Automation (Restarts + Alerts)
```yaml
watchdog:
  image: simonclr/radmac-watchdog:latest
  environment:
    - WATCHDOG_ACTIONS=log,webhook,restart
    - WATCHDOG_WEBHOOK_URL=https://your-webhook-url
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
```

## Webhook Payload Format

```json
{
  "text": "🚨 RadMac Watchdog Alert: database is unhealthy: Connection failed",
  "timestamp": "2025-08-31T23:45:30Z",
  "status": "unhealthy",
  "health_url": "http://app:8080/health"
}
```

## Service Restart Logic

- **App issues**: Restarts the app container
- **Database issues**: Restarts the database container (use with caution)
- **RADIUS issues**: Logs only (typically external service)

## Security Considerations

- Watchdog runs as non-root user
- Docker socket access is optional (only needed for restarts)
- Webhook URLs should be secured
- Consider network policies in production

## Enable/Disable

The watchdog service is commented out by default in `docker-compose.yml`. Simply uncomment the section to enable it.

## Monitoring

The watchdog logs all activities:

```
2025-08-31 23:45:30 - RadMac-Watchdog - INFO - RadMac Watchdog started - monitoring health endpoint
2025-08-31 23:45:30 - RadMac-Watchdog - INFO - Initial health check - monitoring started
2025-08-31 23:46:00 - RadMac-Watchdog - WARNING - database is unhealthy: Connection failed
2025-08-31 23:46:00 - RadMac-Watchdog - INFO - Restart initiated for database
2025-08-31 23:46:30 - RadMac-Watchdog - INFO - 🎉 Services recovered - all healthy!
```

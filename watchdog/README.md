# RadMac Watchdog

A comprehensive health monitoring and alerting service for the RadMac authentication stack. Monitors service health endpoints and triggers configurable actions when services become unhealthy.

## Features

- **Health Monitoring**: Continuously monitors HTTP health endpoints
- **Status Change Detection**: Only triggers alerts on actual status changes (no spam)  
- **Multiple Alert Channels**: Email, Slack, Discord, Telegram, webhooks, and more
- **Container Restart**: Automatic container restart for single-host deployments
- **Docker Swarm Compatible**: Works with both Docker Compose and Docker Swarm
- **Configurable Intervals**: Per-service monitoring intervals with environment overrides

## Quick Start

1. **Configure services** in `watchdog_config.yaml`
2. **Set environment variables** for your notification channels  
3. **Deploy** with Docker Compose or Docker Swarm

```yaml
# Basic configuration
services:
  app:
    health_url: http://app:8080/health
    default_interval: 30
    actions: [log, email, slack]
```

## Deployment Scenarios

### Docker Swarm (Production)
- Use `examples/swarm-config.yaml` as template
- **Omit `restart` actions** - Swarm handles auto-recovery
- Focus on monitoring and alerting

### Single-Host Docker Compose (Development/Testing)
- Use `examples/single-host-config.yaml` as template  
- **Include `restart` actions** for automatic recovery
- Full functionality available

## Configuration

### Service Configuration
```yaml
services:
  service_name:
    health_url: http://service:8080/health    # Health endpoint URL
    interval_env: WATCHDOG_CHECK_INTERVAL_SERVICE  # Environment variable override
    default_interval: 30                      # Default check interval in seconds
    actions: [log, email, restart]           # Actions to take when unhealthy
```

### Supported Actions
- `log` - Log to stdout
- `email` - Send email alert
- `slack` - Slack webhook notification
- `discord` - Discord webhook notification  
- `telegram` - Telegram bot message
- `teams` - Microsoft Teams webhook
- `pushbullet` - Pushbullet notification
- `webhook` - Generic webhook POST
- `restart` - Restart container (single-host only)

### Environment Variables

#### Notification Credentials
```bash
# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=alerts@example.com
EMAIL_PASSWORD=app_password
EMAIL_TO=admin@example.com

# Slack
WATCHDOG_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Discord
WATCHDOG_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Telegram
WATCHDOG_TELEGRAM_BOT_TOKEN=bot_token
WATCHDOG_TELEGRAM_CHAT_ID=chat_id

# Generic Webhook  
WATCHDOG_WEBHOOK_URL=https://your-webhook-url
```

#### Monitoring Intervals
```bash
WATCHDOG_CHECK_INTERVAL_APP=30
WATCHDOG_CHECK_INTERVAL_DATABASE=60
WATCHDOG_CHECK_INTERVAL_RADIUS=45
```

#### Watchdog Settings
```bash
WATCHDOG_STARTUP_GRACE_PERIOD=60      # Seconds to wait before monitoring
WATCHDOG_MAX_RESTART_ATTEMPTS=3       # Max restart attempts per service
WATCHDOG_CONTAINER_PREFIX=radmac      # Container name prefix for restart
```

## Docker Compose Example

```yaml
services:
  watchdog:
    image: simonclr/radmac-watchdog:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./watchdog_config.yaml:/app/watchdog_config.yaml:ro
    environment:
      - EMAIL_HOST=smtp.gmail.com
      - EMAIL_USER=alerts@example.com
      - EMAIL_PASSWORD=app_password
      - EMAIL_TO=admin@example.com
      - WATCHDOG_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
    depends_on:
      - app
      - db
      - radius
```

## Health Endpoint Format

Services should provide health endpoints returning:

```json
{
  "status": "healthy|unhealthy",
  "service": "service_name", 
  "timestamp": 1693747200,
  "details": {
    "database": "connected",
    "dependencies": "available"
  }
}
```

## Alert Behavior

- **Status Change Only**: Alerts trigger only when service status changes (healthy ↔ unhealthy)
- **No Spam**: Won't flood you with repeated alerts for the same incident
- **Recovery Notifications**: Logs when services recover (configurable notifications)

## Development

### Testing Locally
```bash
# Test restart functionality
./test-docker-restart.sh

# Run with test config
python3 watchdog.py --config test_config.yaml
```

### Building Images
```bash
# Multi-platform build
docker buildx build --platform linux/amd64,linux/arm64 -t simonclr/radmac-watchdog:latest --push .
```

## Version History

- **v1.2.2** - Fixed alert spam, added deployment examples, improved documentation
- **v1.2.1** - Added direct health endpoints for all services, environment overrides
- **v1.2.0** - Initial release with multi-service monitoring

## License

Part of the RadMac authentication system.

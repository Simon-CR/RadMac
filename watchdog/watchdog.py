#!/usr/bin/env python3
"""
RadMac Watchdog - Health monitoring and automated remediation service
Monitors the /health endpoint and takes configurable actions when services are unhealthy.
"""


import os
import time
import json
import logging
import requests
import docker
import yaml
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('RadMac-Watchdog')


class RadMacWatchdog:
    def __init__(self, config_path='watchdog_config.yaml'):
        self.config_path = config_path
        self.services = {}
        self.last_status = {}
        self.restart_attempts = {}
        self.docker_client = None
        self.max_restart_attempts = int(os.getenv('WATCHDOG_MAX_RESTART_ATTEMPTS', '3'))
        self.container_prefix = os.getenv('WATCHDOG_CONTAINER_PREFIX', 'radmac')
        self.load_config()
        self.init_docker()
        logger.info("RadMac Watchdog initialized with services:")
        for name, svc in self.services.items():
            logger.info(f"  {name}: {svc['health_url']} (interval: {svc['interval']}s, actions: {svc['actions']})")

    def load_config(self):
        # Load YAML config
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        self.services = {}
        for name, svc in config.get('services', {}).items():
            # Allow override by env var
            interval = int(os.getenv(svc.get('interval_env', ''), svc.get('default_interval', 30)))
            actions = svc.get('actions', ['log'])
            self.services[name] = {
                'health_url': svc['health_url'],
                'interval': interval,
                'actions': actions
            }

    def init_docker(self):
        # Only initialize if any service uses restart
        if any('restart' in svc['actions'] for svc in self.services.values()):
            try:
                self.docker_client = docker.from_env()
                logger.info("Docker client initialized for container management")
            except Exception as e:
                logger.error(f"Failed to initialize Docker client: {e}")
                for svc in self.services.values():
                    svc['actions'] = [a for a in svc['actions'] if a != 'restart']
    

    def check_health(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(url, timeout=10)
            return {
                'status_code': response.status_code,
                'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else None,
                'healthy': response.status_code == 200
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed for {url}: {e}")
            return {
                'status_code': 0,
                'data': None,
                'healthy': False,
                'error': str(e)
            }
    

    # --- Notification Actions ---
    def send_webhook(self, message: str, url: str):
        try:
            payload = {
                'text': f"🚨 RadMac Watchdog Alert: {message}",
                'timestamp': datetime.utcnow().isoformat() + 'Z',
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Webhook notification sent: {message}")
            else:
                logger.error(f"Webhook failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")

    def send_discord(self, message: str):
        webhook_url = os.getenv('WATCHDOG_DISCORD_WEBHOOK_URL')
        if webhook_url:
            self.send_webhook(message, webhook_url)
        else:
            logger.warning("Discord webhook URL not set")

    def send_pushbullet(self, message: str):
        token = os.getenv('WATCHDOG_PUSHBULLET_TOKEN')
        if not token:
            logger.warning("Pushbullet token not set")
            return
        try:
            resp = requests.post('https://api.pushbullet.com/v2/pushes',
                                headers={'Access-Token': token, 'Content-Type': 'application/json'},
                                json={'type': 'note', 'title': 'RadMac Watchdog', 'body': message})
            if resp.status_code == 200:
                logger.info("Pushbullet notification sent")
            else:
                logger.error(f"Pushbullet failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Pushbullet error: {e}")

    def send_email(self, message: str):
        # Stub: implement SMTP or use a service like SendGrid
        logger.info(f"Email notification: {message} (implement SMTP/sendgrid)")

    def send_slack(self, message: str):
        webhook_url = os.getenv('WATCHDOG_SLACK_WEBHOOK_URL')
        if webhook_url:
            self.send_webhook(message, webhook_url)
        else:
            logger.warning("Slack webhook URL not set")

    def send_teams(self, message: str):
        webhook_url = os.getenv('WATCHDOG_TEAMS_WEBHOOK_URL')
        if webhook_url:
            payload = {
                "text": message
            }
            try:
                resp = requests.post(webhook_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info("Teams notification sent")
                else:
                    logger.error(f"Teams webhook failed: {resp.status_code}")
            except Exception as e:
                logger.error(f"Teams webhook error: {e}")
        else:
            logger.warning("Teams webhook URL not set")

    def send_telegram(self, message: str):
        token = os.getenv('WATCHDOG_TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('WATCHDOG_TELEGRAM_CHAT_ID')
        if not token or not chat_id:
            logger.warning("Telegram bot token or chat ID not set")
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        try:
            resp = requests.post(url, data=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram notification sent")
            else:
                logger.error(f"Telegram send failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Telegram error: {e}")
    
    def restart_container(self, service_name: str) -> bool:
        """Restart a specific container/service."""
        if not self.docker_client:
            logger.error("Docker client not available for restart")
            return False
        
        try:
            # Find containers with the service name
            containers = self.docker_client.containers.list(
                filters={"name": f"{self.container_prefix}.*{service_name}"}
            )
            
            if not containers:
                logger.warning(f"No containers found matching {service_name}")
                return False
            
            for container in containers:
                container_name = container.name
                
                # Check restart attempt limits
                if container_name not in self.restart_attempts:
                    self.restart_attempts[container_name] = 0
                
                if self.restart_attempts[container_name] >= self.max_restart_attempts:
                    logger.warning(f"Max restart attempts reached for {container_name}")
                    continue
                
                logger.info(f"Restarting container: {container_name}")
                container.restart()
                self.restart_attempts[container_name] += 1
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to restart {service_name}: {e}")
            return False
        
        return False
    

    def handle_unhealthy_service(self, service_name: str, service_data: Dict[str, Any], actions):
        message = f"{service_name} is {service_data['status']}: {service_data.get('message', 'No details')}"
        logger.warning(message)
        for action in actions:
            if action == 'log':
                logger.warning(f"Service unhealthy: {message}")
            elif action == 'webhook':
                url = os.getenv('WATCHDOG_WEBHOOK_URL')
                if url:
                    self.send_webhook(message, url)
            elif action == 'discord':
                self.send_discord(message)
            elif action == 'pushbullet':
                self.send_pushbullet(message)
            elif action == 'email':
                self.send_email(message)
            elif action == 'slack':
                self.send_slack(message)
            elif action == 'teams':
                self.send_teams(message)
            elif action == 'telegram':
                self.send_telegram(message)
            elif action == 'restart':
                if self.restart_container(service_name):
                    logger.info(f"Restart initiated for {service_name}")
                else:
                    logger.error(f"Failed to restart {service_name}")
    

    def handle_status_change(self, service_name, health_response, actions):
        current_healthy = health_response['healthy']
        if self.last_status.get(service_name) is None:
            logger.info(f"Initial health check for {service_name} - monitoring started")
        elif self.last_status[service_name] != current_healthy:
            if current_healthy:
                logger.info(f"🎉 {service_name} recovered - healthy!")
            else:
                logger.error(f"🚨 {service_name} became unhealthy!")
        if not current_healthy and health_response.get('data'):
            # If health endpoint returns per-service, use that, else just this service
            if 'services' in health_response['data']:
                for sub_name, sub_data in health_response['data']['services'].items():
                    if sub_data.get('status') == 'unhealthy':
                        self.handle_unhealthy_service(sub_name, sub_data, actions)
            else:
                self.handle_unhealthy_service(service_name, health_response['data'], actions)
        self.last_status[service_name] = current_healthy
    

    def run(self):
        logger.info("RadMac Watchdog started - monitoring all configured services")
        next_check = {name: 0 for name in self.services}
        while True:
            now = time.time()
            for name, svc in self.services.items():
                if now >= next_check[name]:
                    try:
                        health_response = self.check_health(svc['health_url'])
                        if health_response:
                            self.handle_status_change(name, health_response, svc['actions'])
                        else:
                            logger.error(f"No health response for {name}")
                        if health_response and health_response['healthy']:
                            self.restart_attempts.clear()
                    except Exception as e:
                        logger.error(f"Watchdog error for {name}: {e}")
                    next_check[name] = now + svc['interval']
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Watchdog stopped by user")
                break

if __name__ == "__main__":
    watchdog = RadMacWatchdog()
    watchdog.run()

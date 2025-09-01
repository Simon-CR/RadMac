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
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('RadMac-Watchdog')

class RadMacWatchdog:
    def __init__(self):
        # Configuration from environment variables
        self.health_url = os.getenv('WATCHDOG_HEALTH_URL', 'http://app:8080/health')
        self.check_interval = int(os.getenv('WATCHDOG_CHECK_INTERVAL', '30'))
        self.actions = os.getenv('WATCHDOG_ACTIONS', 'log').split(',')
        self.webhook_url = os.getenv('WATCHDOG_WEBHOOK_URL')
        self.max_restart_attempts = int(os.getenv('WATCHDOG_MAX_RESTART_ATTEMPTS', '3'))
        self.container_prefix = os.getenv('WATCHDOG_CONTAINER_PREFIX', 'radmac')
        
        # State tracking
        self.last_status = None
        self.restart_attempts = {}
        self.docker_client = None
        
        # Initialize Docker client if restart action is enabled
        if 'restart' in self.actions:
            try:
                self.docker_client = docker.from_env()
                logger.info("Docker client initialized for container management")
            except Exception as e:
                logger.error(f"Failed to initialize Docker client: {e}")
                logger.warning("Restart actions will be disabled")
                self.actions = [action for action in self.actions if action != 'restart']
        
        logger.info(f"RadMac Watchdog initialized:")
        logger.info(f"  Health URL: {self.health_url}")
        logger.info(f"  Check interval: {self.check_interval}s")
        logger.info(f"  Actions: {', '.join(self.actions)}")
    
    def check_health(self) -> Optional[Dict[str, Any]]:
        """Check the health endpoint and return parsed response."""
        try:
            response = requests.get(self.health_url, timeout=10)
            return {
                'status_code': response.status_code,
                'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else None,
                'healthy': response.status_code == 200
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status_code': 0,
                'data': None,
                'healthy': False,
                'error': str(e)
            }
    
    def send_webhook(self, message: str, status: str = "unhealthy"):
        """Send notification to webhook URL."""
        if not self.webhook_url:
            return
        
        try:
            payload = {
                'text': f"🚨 RadMac Watchdog Alert: {message}",
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'status': status,
                'health_url': self.health_url
            }
            
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Webhook notification sent: {message}")
            else:
                logger.error(f"Webhook failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
    
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
    
    def handle_unhealthy_service(self, service_name: str, service_data: Dict[str, Any]):
        """Handle a specific unhealthy service."""
        message = f"{service_name} is {service_data['status']}: {service_data.get('message', 'No details')}"
        logger.warning(message)
        
        # Always log
        if 'log' in self.actions:
            logger.warning(f"Service unhealthy: {message}")
        
        # Send webhook notification
        if 'webhook' in self.actions:
            self.send_webhook(message)
        
        # Restart container (be selective about what to restart)
        if 'restart' in self.actions:
            if service_name in ['app', 'database']:  # Only restart these services
                if self.restart_container(service_name):
                    logger.info(f"Restart initiated for {service_name}")
                else:
                    logger.error(f"Failed to restart {service_name}")
            else:
                logger.info(f"Skipping restart for {service_name} (not configured for auto-restart)")
    
    def handle_status_change(self, health_response: Dict[str, Any]):
        """Handle health status changes."""
        current_healthy = health_response['healthy']
        
        # Status change detection
        if self.last_status is None:
            logger.info("Initial health check - monitoring started")
        elif self.last_status != current_healthy:
            if current_healthy:
                logger.info("🎉 Services recovered - all healthy!")
                if 'webhook' in self.actions:
                    self.send_webhook("All services have recovered", "healthy")
            else:
                logger.error("🚨 Services became unhealthy!")
        
        # Handle unhealthy services
        if not current_healthy and health_response.get('data'):
            services = health_response['data'].get('services', {})
            for service_name, service_data in services.items():
                if service_data.get('status') == 'unhealthy':
                    self.handle_unhealthy_service(service_name, service_data)
        
        self.last_status = current_healthy
    
    def run(self):
        """Main monitoring loop."""
        logger.info("RadMac Watchdog started - monitoring health endpoint")
        
        while True:
            try:
                health_response = self.check_health()
                
                if health_response:
                    self.handle_status_change(health_response)
                else:
                    logger.error("No health response received")
                
                # Reset restart attempts on successful health checks
                if health_response and health_response['healthy']:
                    self.restart_attempts.clear()
                
            except KeyboardInterrupt:
                logger.info("Watchdog stopped by user")
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            
            time.sleep(self.check_interval)

if __name__ == "__main__":
    watchdog = RadMacWatchdog()
    watchdog.run()

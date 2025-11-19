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
import smtplib
import importlib
from email.message import EmailMessage
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
        self.service_destinations = {}
        self.next_check = {}
        self.service_ready_at = {}
        self.smtp_settings = {}
        self.last_status = {}
        self.restart_attempts = {}
        self.docker_client = None
        self.docker_module = None
        self.docker_errors = None
        self.api_config_url = os.getenv('WATCHDOG_CONFIG_API_URL')
        self.api_token = os.getenv('WATCHDOG_CONFIG_API_TOKEN')
        try:
            refresh_env = os.getenv('WATCHDOG_CONFIG_REFRESH_SECONDS', '120')
            if refresh_env.startswith('{') and refresh_env.endswith('}'):
                self.api_refresh_interval = 120
            else:
                self.api_refresh_interval = max(30, int(refresh_env))
        except (TypeError, ValueError):
            self.api_refresh_interval = 120
        self.next_config_refresh = 0
        
        # Parse max restart attempts with error handling
        try:
            max_attempts_env = os.getenv('WATCHDOG_MAX_RESTART_ATTEMPTS', '3')
            if max_attempts_env.startswith('{') and max_attempts_env.endswith('}'):
                logger.warning(f"WATCHDOG_MAX_RESTART_ATTEMPTS appears to be a template: {max_attempts_env}, using default (3)")
                self.max_restart_attempts = 3
            else:
                self.max_restart_attempts = int(max_attempts_env)
        except (ValueError, TypeError):
            logger.warning(f"Invalid WATCHDOG_MAX_RESTART_ATTEMPTS value: {os.getenv('WATCHDOG_MAX_RESTART_ATTEMPTS')}, using default (3)")
            self.max_restart_attempts = 3
        self.container_prefix = os.getenv('WATCHDOG_CONTAINER_PREFIX', 'radmac')
        self.load_config()
        self._sync_tracking_maps(time.time(), reset=True)
        if self.api_config_url:
            self.refresh_from_api(initial=True)
        self.init_docker()
        logger.info("RadMac Watchdog initialized with services:")
        for name, svc in self.services.items():
            logger.info(f"  {name}: {svc['health_url']} (interval: {svc['interval']}s, actions: {svc['actions']})")

    def _normalize_actions(self, actions):
        if not actions:
            return ['log']
        if isinstance(actions, str):
            try:
                parsed = json.loads(actions)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, TypeError):
                return [a.strip() for a in actions.split(',') if a.strip()]
        return actions

    def _to_int(self, value, default):
        try:
            if value is None:
                return default
            if isinstance(value, str) and not value.strip():
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def load_config(self):
        # Load YAML config
        try:
            yaml = importlib.import_module('yaml')
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to load the watchdog configuration") from exc
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        self.services = {}
        self.service_destinations = {}
        for name, svc in config.get('services', {}).items():
            # Parse interval with error handling
            interval_env_var = svc.get('interval_env', '')
            default_interval = svc.get('default_interval', 30)
            
            try:
                interval_env_value = os.getenv(interval_env_var, str(default_interval))
                if interval_env_value.startswith('{') and interval_env_value.endswith('}'):
                    logger.warning(f"Interval environment variable {interval_env_var} appears to be a template: {interval_env_value}, using default ({default_interval})")
                    interval = default_interval
                else:
                    interval = int(interval_env_value)
            except (ValueError, TypeError):
                logger.warning(f"Invalid interval value for {name}: {os.getenv(interval_env_var)}, using default ({default_interval})")
                interval = default_interval
                
            actions = self._normalize_actions(svc.get('actions', ['log']))
            startup_delay = self._to_int(svc.get('startup_delay_seconds'), 0)
            self.services[name] = {
                'health_url': svc['health_url'],
                'interval': interval,
                'actions': actions,
                'startup_delay': startup_delay
            }
            self.service_destinations[name] = []
        self._sync_tracking_maps(time.time(), reset=True)

    def _sync_tracking_maps(self, current_time=None, reset=False):
        if current_time is None:
            current_time = time.time()
        if reset:
            self.next_check = {}
            self.service_ready_at = {}
        # Remove stale entries
        for name in list(self.next_check.keys()):
            if name not in self.services:
                self.next_check.pop(name, None)
        for name in list(self.service_ready_at.keys()):
            if name not in self.services:
                self.service_ready_at.pop(name, None)
        for name, svc in self.services.items():
            self.next_check.setdefault(name, 0)
            if name not in self.service_ready_at:
                self.service_ready_at[name] = current_time + svc.get('startup_delay', 0)

    def refresh_from_api(self, initial=False):
        if not self.api_config_url:
            return
        now = time.time()
        if not initial and now < self.next_config_refresh:
            return
        try:
            headers = {}
            if self.api_token:
                headers['X-Watchdog-Token'] = self.api_token
            response = requests.get(self.api_config_url, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
            self._apply_api_config(payload)
            logger.info("Loaded monitoring config from API%s", " (initial)" if initial else "")
        except Exception as exc:
            logger.error(f"Failed to refresh config from API: {exc}")
            if initial and not self.services:
                logger.warning("Falling back to static YAML config; API config unavailable")
        finally:
            self.next_config_refresh = now + self.api_refresh_interval

    def _apply_api_config(self, payload):
        services_payload = payload.get('services', []) if isinstance(payload, dict) else []
        new_services = {}
        new_destinations = {}
        now = time.time()
        for svc in services_payload:
            if not svc or not svc.get('enabled', True):
                continue
            name = svc.get('service_name') or svc.get('name')
            if not name:
                continue
            health_url = svc.get('health_url') or svc.get('url')
            if not health_url:
                logger.debug(f"Skipping service {name}: missing health URL")
                continue
            interval_value = svc.get('interval_seconds', svc.get('interval'))
            interval = self._to_int(interval_value, 30)
            startup_delay = self._to_int(svc.get('startup_delay_seconds'), 0)
            actions = self._normalize_actions(svc.get('actions') or ['log'])
            new_services[name] = {
                'health_url': health_url,
                'interval': interval,
                'actions': actions,
                'startup_delay': startup_delay
            }
            dest_entries = []
            for dest in svc.get('destinations', []) or []:
                normalized = self._normalize_destination(dest)
                if normalized and normalized.get('enabled', True):
                    dest_entries.append(normalized)
            new_destinations[name] = dest_entries
        self.services = new_services
        self.service_destinations = new_destinations
        self.smtp_settings = payload.get('smtp_settings') or {}
        self._sync_tracking_maps(now, reset=False)
        if any('restart' in svc['actions'] for svc in self.services.values()) and not self.docker_client:
            self.init_docker()

    def _normalize_destination(self, dest):
        if not dest:
            return None
        config = dest.get('config') if isinstance(dest, dict) else None
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}
        elif config is None and dest.get('config_json'):
            try:
                config = json.loads(dest['config_json'])
            except json.JSONDecodeError:
                config = {}
        return {
            'id': dest.get('id'),
            'name': dest.get('name'),
            'destination_type': (dest.get('destination_type') or '').lower(),
            'enabled': dest.get('enabled', True),
            'config': config or {},
        }

    def init_docker(self):
        # Only initialize if any service uses restart
        if not any('restart' in svc['actions'] for svc in self.services.values()):
            return
        try:
            self.docker_module = importlib.import_module('docker')
            self.docker_errors = getattr(self.docker_module, 'errors', None)
            self.docker_client = self.docker_module.from_env()
            logger.info("Docker client initialized for container management")
        except ImportError:
            logger.error("Docker SDK for Python is not installed; disabling restart actions")
            for svc in self.services.values():
                svc['actions'] = [a for a in svc['actions'] if a != 'restart']
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
    
    def _parse_json_blob(self, value):
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _build_alert_payload(self, service_name: str, service_data: Dict[str, Any]) -> Dict[str, Any]:
        status = service_data.get('status') or service_data.get('service_status') or 'unhealthy'
        message = service_data.get('message') or service_data.get('error') or service_data.get('details') or ''
        payload = {
            'service': service_name,
            'status': status,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'details': service_data,
        }
        if message:
            payload['message'] = message
        return payload

    def _format_alert_text(self, payload: Dict[str, Any]) -> str:
        detail = payload.get('message') or ''
        ip = payload['details'].get('resolved_ip') if isinstance(payload.get('details'), dict) else None
        lines = [
            f"Service: {payload.get('service')}",
            f"Status: {payload.get('status')}",
            f"Timestamp: {payload.get('timestamp')}",
        ]
        if ip:
            lines.append(f"Target: {ip}")
        if detail:
            lines.append(f"Details: {detail}")
        return "\n".join(lines)

    def _post_webhook(self, url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        try:
            response = requests.post(url, json=payload, headers=headers or {}, timeout=10)
            if response.status_code >= 300:
                logger.error(f"Webhook {url} failed with status {response.status_code}")
        except Exception as exc:
            logger.error(f"Webhook send failure for {url}: {exc}")

    def _send_email_via_config(self, config: Dict[str, Any], subject: str, body: str):
        config = config or {}
        smtp_defaults = self.smtp_settings or {}

        recipient = config.get('email_to') or config.get('to')
        sender = config.get('email_from') or smtp_defaults.get('from_email') or os.getenv('WATCHDOG_EMAIL_FROM', 'watchdog@radmac.local')
        if not recipient:
            logger.warning("Email destination missing recipient; skipping")
            return
        smtp_host = config.get('smtp_host') or smtp_defaults.get('host') or os.getenv('WATCHDOG_SMTP_HOST')
        if not smtp_host:
            logger.warning("SMTP host not configured for email destination")
            return
        smtp_port = config.get('smtp_port') or smtp_defaults.get('port') or os.getenv('WATCHDOG_SMTP_PORT', 587)
        try:
            smtp_port = int(smtp_port)
        except (TypeError, ValueError):
            smtp_port = 587
        use_tls = config.get('use_tls')
        if isinstance(use_tls, str):
            use_tls = use_tls.lower() in ('1', 'true', 'yes', 'on')
        if use_tls is None:
            default_tls = smtp_defaults.get('use_tls')
            if default_tls is None:
                use_tls = True
            else:
                use_tls = bool(default_tls)
        smtp_user = config.get('smtp_user') or smtp_defaults.get('username') or os.getenv('WATCHDOG_SMTP_USER')
        smtp_password = config.get('smtp_password') or smtp_defaults.get('password') or os.getenv('WATCHDOG_SMTP_PASSWORD')
        use_ssl = config.get('use_ssl')
        if isinstance(use_ssl, str):
            use_ssl = use_ssl.lower() in ('1', 'true', 'yes', 'on')
        if use_ssl is None:
            use_ssl = bool(smtp_defaults.get('use_ssl'))
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = recipient
        msg.set_content(body)
        try:
            if use_ssl:
                smtp_client = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
            else:
                smtp_client = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            with smtp_client as smtp:
                if use_tls and not use_ssl:
                    smtp.starttls()
                if smtp_user and smtp_password:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
            logger.info(f"Email alert sent to {recipient}")
        except Exception as exc:
            logger.error(f"Failed to send email alert: {exc}")

    def notify_destinations(self, service_name: str, service_data: Dict[str, Any]):
        destinations = self.service_destinations.get(service_name) or []
        if not destinations:
            return
        payload = self._build_alert_payload(service_name, service_data)
        text_body = self._format_alert_text(payload)
        subject = f"RadMac alert: {service_name} {payload.get('status')}"
        for destination in destinations:
            config = destination.get('config') or {}
            dtype = (destination.get('destination_type') or 'webhook').lower()
            try:
                if dtype in ('webhook', 'slack', 'discord', 'teams'):
                    url = config.get('webhook_url') or config.get('url')
                    if not url:
                        logger.warning(f"Destination {destination.get('name')} missing webhook_url")
                        continue
                    headers = self._parse_json_blob(config.get('headers_json'))
                    extra = self._parse_json_blob(config.get('extra_payload'))
                    webhook_payload = {**payload, **extra}
                    self._post_webhook(url, webhook_payload, headers=headers)
                elif dtype in ('email', 'smtp'):
                    self._send_email_via_config(config, subject, text_body)
                elif dtype == 'telegram':
                    token = config.get('telegram_bot_token') or os.getenv('WATCHDOG_TELEGRAM_BOT_TOKEN')
                    chat_id = config.get('telegram_chat_id') or os.getenv('WATCHDOG_TELEGRAM_CHAT_ID')
                    if not token or not chat_id:
                        logger.warning("Telegram destination missing token or chat_id")
                        continue
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    resp = requests.post(url, data={'chat_id': chat_id, 'text': text_body[:4000]}, timeout=10)
                    if resp.status_code >= 300:
                        logger.error(f"Telegram API error {resp.status_code}: {resp.text[:120]}")
                elif dtype == 'pushbullet':
                    token = config.get('pushbullet_token') or os.getenv('WATCHDOG_PUSHBULLET_TOKEN')
                    if not token:
                        logger.warning("Pushbullet destination missing token")
                        continue
                    headers = {'Access-Token': token, 'Content-Type': 'application/json'}
                    payload_data = {
                        'type': 'note',
                        'title': subject,
                        'body': text_body,
                    }
                    if config.get('pushbullet_device'):
                        payload_data['device_iden'] = config['pushbullet_device']
                    resp = requests.post('https://api.pushbullet.com/v2/pushes', headers=headers, json=payload_data, timeout=10)
                    if resp.status_code >= 300:
                        logger.error(f"Pushbullet API error {resp.status_code}: {resp.text[:120]}")
                else:
                    logger.warning(f"Unsupported destination type {dtype} for {destination.get('name')}")
            except Exception as exc:
                logger.error(f"Failed to send alert to {destination.get('name')}: {exc}")
        

    def handle_unhealthy_service(self, service_name: str, service_data: Dict[str, Any], actions):
        status = service_data.get('status', 'unhealthy')
        message = f"{service_name} is {status}: {service_data.get('message', 'No details')}"
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
            elif action == 'recover':
                self.trigger_recovery(service_name, service_data)
        self.notify_destinations(service_name, service_data)
    
    def trigger_recovery(self, service_name: str, health_data: Dict[str, Any]):
        """Trigger recovery actions for degraded services"""
        try:
            if service_name == 'database':
                logger.info(f"Triggering database recovery for {service_name}")
                
                # Try Swarm service exec first, then fall back to container exec
                recovery_success = False
                
                # Method 1: Try Docker Swarm service execution
                if self._try_swarm_recovery(service_name):
                    recovery_success = True
                # Method 2: Fall back to direct container execution  
                elif self._try_container_recovery(service_name):
                    recovery_success = True
                # Method 3: Use HTTP endpoint if available
                elif self._try_http_recovery(service_name):
                    recovery_success = True
                else:
                    logger.error(f"All recovery methods failed for {service_name}")
                    
                if recovery_success:
                    logger.info(f"Database recovery completed successfully for {service_name}")
            else:
                logger.info(f"Recovery action for {service_name} - logging degraded state")
                warnings = health_data.get('warnings', [])
                logger.warning(f"Service {service_name} degraded: {', '.join(warnings)}")
        except Exception as e:
            logger.error(f"Recovery action failed for {service_name}: {e}")

    def _try_swarm_recovery(self, service_name: str) -> bool:
        """Try recovery using Docker Swarm service exec"""
        if not self.docker_client:
            return False
        docker_errors = self.docker_errors
        not_found_type = getattr(docker_errors, 'NotFound', None) if docker_errors else None
        service_full_name = f"{self.container_prefix}_{service_name}"
        try:
            services = self.docker_client.services.list(filters={'name': service_full_name})
            if not services:
                logger.debug(f"No Swarm service found for {service_full_name}")
                return False
            service = services[0]
            tasks = service.tasks(filters={'desired-state': 'running'})
            if not tasks:
                logger.debug(f"No running Swarm tasks for {service_full_name}")
                return False
            task = tasks[0]
            container_id = task['Status']['ContainerStatus']['ContainerID']
            container = self.docker_client.containers.get(container_id)
            exec_result = container.exec_run(
                'python3 /usr/local/bin/recovery_script.py',
                stdout=True,
                stderr=True
            )
            if exec_result.exit_code == 0:
                logger.info(f"Swarm recovery success: {exec_result.output.decode()}")
                return True
            logger.warning(f"Swarm recovery failed: {exec_result.output.decode()}")
            return False
        except Exception as exc:
            if not_found_type and isinstance(exc, not_found_type):
                logger.debug(f"No Swarm service found for {service_full_name}")
                return False
            logger.debug(f"Swarm recovery attempt failed: {exc}")
            return False

    def _try_container_recovery(self, service_name: str) -> bool:
        """Try recovery using direct container execution (Docker Compose)"""
        if not self.docker_client:
            return False
        docker_errors = self.docker_errors
        not_found_type = getattr(docker_errors, 'NotFound', None) if docker_errors else None
        possible_names = [
            f"{self.container_prefix}_{service_name}_1",
            f"{self.container_prefix}-{service_name}-1",
            f"{service_name}",
            "db",
        ]
        for container_name in possible_names:
            try:
                container = self.docker_client.containers.get(container_name)
                exec_result = container.exec_run(
                    'python3 /usr/local/bin/recovery_script.py',
                    stdout=True,
                    stderr=True
                )
                if exec_result.exit_code == 0:
                    logger.info(f"Container recovery success: {exec_result.output.decode()}")
                    return True
                logger.warning(f"Container recovery failed: {exec_result.output.decode()}")
                return False
            except Exception as exc:
                if not_found_type and isinstance(exc, not_found_type):
                    continue
                logger.debug(f"Container recovery attempt failed for {container_name}: {exc}")
        logger.debug(f"No containers found with names: {possible_names}")
        return False
            
    def _try_http_recovery(self, service_name: str) -> bool:
        """Try recovery using HTTP endpoint"""
        try:
            if service_name == 'database':
                # Use the database health endpoint's recovery feature
                recovery_url = f"http://db:8080/recover"
                response = requests.post(recovery_url, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"HTTP recovery success: {data.get('output', 'Recovery completed')}")
                    return True
                else:
                    data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    error = data.get('error', f'HTTP {response.status_code}')
                    logger.warning(f"HTTP recovery failed: {error}")
                    return False
            return False
        except requests.exceptions.RequestException as e:
            logger.debug(f"HTTP recovery attempt failed: {e}")
            return False
        except Exception as e:
            logger.debug(f"HTTP recovery attempt failed: {e}")
            return False

    def handle_status_change(self, service_name, health_response, actions):
        current_healthy = health_response['healthy']
        current_data = health_response.get('data', {})
        current_status = current_data.get('status', 'healthy' if current_healthy else 'unhealthy')
        
        status_changed = False
        previous_status = self.last_status.get(service_name, {})
        previous_healthy = previous_status.get('healthy') if isinstance(previous_status, dict) else previous_status
        previous_state = previous_status.get('status') if isinstance(previous_status, dict) else None
        
        if previous_healthy is None:
            logger.info(f"Initial health check for {service_name} - monitoring started")
            status_changed = True
        elif previous_healthy != current_healthy or previous_state != current_status:
            status_changed = True
            if current_healthy and current_status == 'healthy':
                logger.info(f"🎉 {service_name} recovered - healthy!")
            elif current_healthy and current_status == 'degraded':
                logger.warning(f"⚠️ {service_name} is degraded but functional")
                # Trigger recovery actions for degraded services
                if 'recover' not in actions:
                    actions = actions + ['recover']  # Add recovery action
            else:
                logger.error(f"🚨 {service_name} became unhealthy!")
        
        # Handle degraded status - trigger recovery actions
        if current_status == 'degraded' and status_changed:
            logger.info(f"Triggering recovery actions for degraded service: {service_name}")
            recovery_actions = [action for action in actions if action in ['recover', 'log']]
            if 'recover' in actions:
                self.trigger_recovery(service_name, current_data)
            if 'log' in recovery_actions:
                warnings = current_data.get('warnings', [])
                logger.warning(f"{service_name} degraded - warnings: {', '.join(warnings)}")
        
        # Only trigger actions on status change, not on every failed check
        if status_changed and not current_healthy and current_data:
            # If health endpoint returns per-service, use that, else just this service
            if 'services' in current_data:
                for sub_name, sub_data in current_data['services'].items():
                    if sub_data.get('status') == 'unhealthy':
                        self.handle_unhealthy_service(sub_name, sub_data, actions)
            else:
                self.handle_unhealthy_service(service_name, current_data, actions)
        
        # Store both healthy status and detailed status
        self.last_status[service_name] = {
            'healthy': current_healthy,
            'status': current_status,
            'timestamp': time.time()
        }
    


    def run(self):
        try:
            grace_env = os.getenv('WATCHDOG_STARTUP_GRACE_PERIOD', '60')
            # Handle case where environment variable is a template string
            if grace_env.startswith('{') and grace_env.endswith('}'):
                logger.warning(f"Environment variable appears to be a template: {grace_env}, using default value")
                grace = 60
            else:
                grace = int(grace_env)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid WATCHDOG_STARTUP_GRACE_PERIOD value: {os.getenv('WATCHDOG_STARTUP_GRACE_PERIOD')}, using default (60)")
            grace = 60
            
        if grace > 0:
            logger.info(f"Startup grace period: waiting {grace} seconds before monitoring...")
            time.sleep(grace)
        logger.info("RadMac Watchdog started - monitoring all configured services")
        self._sync_tracking_maps(time.time())
        app_health = None
        while True:
            now = time.time()
            self.refresh_from_api()
            self._sync_tracking_maps(now)
            app_config = self.services.get('app')
            # Always check app first if present
            if app_config and now >= self.next_check.get('app', 0) and now >= self.service_ready_at.get('app', 0):
                try:
                    app_health = self.check_health(app_config['health_url'])
                    if app_health:
                        self.handle_status_change('app', app_health, app_config['actions'])
                        if app_health['healthy']:
                            self.restart_attempts.clear()
                    else:
                        logger.error("No health response for app")
                        app_health = None  # Ensure it's None for other service checks
                except Exception as e:
                    logger.error(f"Watchdog error for app: {e}")
                    app_health = None  # Ensure it's None on error
                self.next_check['app'] = now + app_config['interval']
            # Now check other services
            for name, svc in self.services.items():
                if name == 'app':
                    continue
                if now < self.service_ready_at.get(name, 0):
                    continue
                if now >= self.next_check.get(name, 0):
                    # If this service uses app's /health, only act if app is healthy
                    if app_config and svc['health_url'] == app_config['health_url']:
                        if not (app_health and app_health['healthy'] and app_health.get('data')):
                            logger.info(f"Skipping {name} check: app is not healthy or /health unavailable")
                            self.next_check[name] = now + svc['interval']
                            continue
                        # Only act if /health reports this service as unhealthy
                        if 'services' in app_health['data'] and name in app_health['data']['services']:
                            sub_data = app_health['data']['services'][name]
                            if sub_data.get('status') == 'unhealthy':
                                self.handle_unhealthy_service(name, sub_data, svc['actions'])
                        # Otherwise, do nothing
                    else:
                        # Direct health check for this service
                        try:
                            health_response = self.check_health(svc['health_url'])
                            if health_response:
                                self.handle_status_change(name, health_response, svc['actions'])
                                if health_response['healthy']:
                                    self.restart_attempts.clear()
                            else:
                                logger.error(f"No health response for {name}")
                        except Exception as e:
                            logger.error(f"Watchdog error for {name}: {e}")
                    self.next_check[name] = now + svc['interval']
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Watchdog stopped by user")
                break

if __name__ == "__main__":
    watchdog = RadMacWatchdog()
    watchdog.run()

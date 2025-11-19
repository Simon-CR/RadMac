import os
import socket
import subprocess
from datetime import datetime

import mysql.connector
import requests

from db_interface import (
    get_monitor_check_by_name,
    record_monitor_check_status,
)

PING_CMD = os.getenv("PING_COMMAND", "ping")


def _resolve_host(hostname):
    try:
        info = socket.getaddrinfo(hostname, None)
        ips = sorted({entry[4][0] for entry in info if entry[4]})
        if not ips:
            return "fail", [], f"No IPs returned for {hostname}"
        return "ok", ips, None
    except socket.gaierror as exc:
        return "fail", [], str(exc)


def _ping_target(target_ip):
    try:
        result = subprocess.run(
            [PING_CMD, "-c", "1", "-W", "2", target_ip],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return "ok", result.stdout.strip()
        return "fail", result.stderr.strip() or result.stdout.strip()
    except FileNotFoundError:
        return "fail", "ping binary not available"
    except Exception as exc:
        return "fail", str(exc)


def _check_database_service(check):
    config = {
        "host": check.get("host") or os.getenv("DB_HOST", "db"),
        "port": check.get("port") or int(os.getenv("DB_PORT", 3306)),
        "user": os.getenv("DB_USER", "radiususer"),
        "password": os.getenv("DB_PASSWORD", "radiuspass"),
        "database": os.getenv("DB_NAME", "radius"),
        "connection_timeout": 5,
    }
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return "ok", "Database connection successful"
    except mysql.connector.Error as exc:
        return "fail", f"MySQL error: {exc}"
    except Exception as exc:
        return "fail", str(exc)


def _check_http_service(check):
    url = check.get("health_url")
    if not url:
        return "unknown", "Health URL not configured"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return "ok", f"HTTP {response.status_code}"
        return "fail", f"HTTP {response.status_code}: {response.text[:180]}"
    except requests.exceptions.RequestException as exc:
        return "fail", str(exc)


def _check_radius_service(check):
    # For now reuse HTTP health endpoint exposed by the radius container
    return _check_http_service(check)


def _evaluate_service(check):
    check_type = check.get("check_type", "http")
    if check_type == "database":
        return _check_database_service(check)
    if check_type == "radius":
        return _check_radius_service(check)
    return _check_http_service(check)


def run_monitor_check(service_name):
    check = get_monitor_check_by_name(service_name, include_disabled=True)
    if not check:
        return {
            "service_name": service_name,
            "error": "Service configuration not found",
        }

    host = check.get("host") or service_name
    result = {
        "service_name": service_name,
        "display_name": check.get("display_name", service_name.title()),
        "host": host,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    dns_status, ip_list, dns_error = _resolve_host(host)
    result["dns_status"] = dns_status
    result["dns_notes"] = dns_error
    resolved_ip = ip_list[0] if ip_list else None
    result["resolved_ip"] = resolved_ip
    result["ip_list"] = ip_list

    if dns_status != "ok" or not resolved_ip:
        ping_status = "fail"
        ping_details = dns_error or "DNS resolution failed"
    else:
        ping_status, ping_details = _ping_target(resolved_ip)
    result["ping_status"] = ping_status
    result["ping_details"] = ping_details

    if ping_status != "ok" and check.get("check_type") not in ("http", "nginx", "app"):
        service_status = "fail"
        service_details = "Ping failed; skipping service probe"
    else:
        service_status, service_details = _evaluate_service(check)
    result["service_status"] = service_status
    result["service_details"] = service_details

    # Persist latest status if we weren't just checking existence
    record_monitor_check_status(
        service_name,
        {
            "last_run": datetime.utcnow(),
            "dns_status": dns_status if dns_status in ("ok", "fail") else "unknown",
            "resolved_ip": resolved_ip,
            "ping_status": ping_status if ping_status in ("ok", "fail") else "unknown",
            "service_status": service_status if service_status in ("ok", "fail") else "unknown",
            "details": {
                "dns_notes": dns_error,
                "ping_details": ping_details,
                "service_details": service_details,
                "ip_list": ip_list,
            },
        },
    )

    return result

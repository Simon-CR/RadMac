import json
import smtplib
from datetime import datetime
from email.message import EmailMessage

import requests
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, current_app
from flask_login import login_required

from db_interface import (
    get_monitor_checks,
    update_monitor_check_settings,
    get_alert_destinations,
    add_alert_destination,
    update_alert_destination,
    delete_alert_destination,
    get_monitoring_config,
    get_smtp_settings,
    save_smtp_settings,
)
from monitoring_service import run_monitor_check

monitoring = Blueprint("monitoring", __name__, url_prefix="/monitoring")

ALERT_CONFIG_FIELDS = [
    "webhook_url",
    "email_to",
    "email_from",
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "use_tls",
    "use_ssl",
    "telegram_bot_token",
    "telegram_chat_id",
    "pushbullet_token",
    "pushbullet_device",
    "headers_json",
    "extra_payload",
]


def _coerce_bool(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return default if default is not None else False


def _parse_json_blob(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _build_test_payload(destination_name):
    return {
        "service": "monitoring-ui",
        "status": "test",
        "message": f"RadMac test alert routed via {destination_name}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def _send_test_email(destination, smtp_settings):
    config = destination.get("config") or {}
    smtp_defaults = smtp_settings or {}
    recipient = config.get("email_to")
    if not recipient:
        raise ValueError("Destination is missing an Email To address.")
    smtp_host = config.get("smtp_host") or smtp_defaults.get("host")
    if not smtp_host:
        raise ValueError("SMTP host is not configured for this destination or the defaults.")
    smtp_port = config.get("smtp_port") or smtp_defaults.get("port") or 587
    try:
        smtp_port = int(smtp_port)
    except (TypeError, ValueError):
        smtp_port = 587
    use_ssl = _coerce_bool(config.get("use_ssl"), _coerce_bool(smtp_defaults.get("use_ssl"), False)) or False
    use_tls_default = False if use_ssl else _coerce_bool(smtp_defaults.get("use_tls"), True)
    use_tls = _coerce_bool(config.get("use_tls"), use_tls_default) or False
    smtp_user = config.get("smtp_user") or smtp_defaults.get("username")
    smtp_password = config.get("smtp_password") or smtp_defaults.get("password")
    sender = config.get("email_from") or smtp_defaults.get("from_email") or smtp_user or "watchdog@radmac.local"

    msg = EmailMessage()
    msg["Subject"] = f"RadMac test alert: {destination.get('name')}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        "This is a RadMac monitoring test alert. If you received this message, the destination is wired correctly."
    )

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(smtp_host, smtp_port, timeout=15) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)


def _send_test_webhook(destination):
    config = destination.get("config") or {}
    url = config.get("webhook_url") or config.get("url")
    if not url:
        raise ValueError("Destination is missing a webhook URL.")
    headers = _parse_json_blob(config.get("headers_json")) or {}
    extra = _parse_json_blob(config.get("extra_payload")) or {}
    payload = {**_build_test_payload(destination.get("name")), **extra}
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    if response.status_code >= 400:
        raise ValueError(f"Webhook returned HTTP {response.status_code}")


def _send_test_telegram(destination):
    config = destination.get("config") or {}
    token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")
    if not token or not chat_id:
        raise ValueError("Telegram destination is missing a bot token or chat ID.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": _build_test_payload(destination.get("name"))["message"]}
    response = requests.post(url, data=payload, timeout=10)
    if response.status_code >= 300:
        raise ValueError(f"Telegram API returned HTTP {response.status_code}")


def _send_test_pushbullet(destination):
    config = destination.get("config") or {}
    token = config.get("pushbullet_token")
    if not token:
        raise ValueError("Pushbullet token is missing.")
    headers = {"Access-Token": token, "Content-Type": "application/json"}
    payload = {
        "type": "note",
        "title": f"RadMac test alert: {destination.get('name')}",
        "body": _build_test_payload(destination.get("name"))["message"],
    }
    if config.get("pushbullet_device"):
        payload["device_iden"] = config["pushbullet_device"]
    response = requests.post("https://api.pushbullet.com/v2/pushes", headers=headers, json=payload, timeout=10)
    if response.status_code >= 300:
        raise ValueError(f"Pushbullet API returned HTTP {response.status_code}")


def _send_test_destination(destination, smtp_settings):
    dtype = (destination.get("destination_type") or "").lower()
    if dtype in ("email", "smtp"):
        _send_test_email(destination, smtp_settings)
        return
    if dtype in ("webhook", "slack", "discord", "teams"):
        _send_test_webhook(destination)
        return
    if dtype == "telegram":
        _send_test_telegram(destination)
        return
    if dtype == "pushbullet":
        _send_test_pushbullet(destination)
        return
    raise ValueError(f"Destination type '{dtype or 'unknown'}' is not supported for test delivery.")


def _collect_alert_config(form):
    config = {}
    for field in ALERT_CONFIG_FIELDS:
        value = form.get(field)
        if value:
            if field in {"use_tls", "use_ssl"}:
                config[field] = value.lower() in ("1", "true", "on", "yes")
            else:
                config[field] = value
    return config


def _build_destination_config(form):
    config = _collect_alert_config(form)
    raw_payload = form.get("config_json_raw")
    if raw_payload:
        try:
            extra = json.loads(raw_payload)
            if isinstance(extra, dict):
                config.update(extra)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON payload: {exc}") from exc
    return config


@monitoring.route("/", methods=["GET"])
@login_required
def monitoring_page():
    checks = get_monitor_checks(include_disabled=True)
    destinations = get_alert_destinations(include_disabled=True)
    smtp_settings = get_smtp_settings() or {}
    return render_template(
        "monitoring.html",
        checks=checks,
        destinations=destinations,
        smtp_settings=smtp_settings,
        destination_types=[
            "email",
            "smtp",
            "discord",
            "pushbullet",
            "telegram",
            "slack",
            "teams",
            "webhook",
        ],
    )


@monitoring.route("/checks/<service_name>/settings", methods=["POST"])
@login_required
def save_check_settings(service_name):
    interval = int(request.form.get("interval_seconds", 30))
    startup_delay = int(request.form.get("startup_delay_seconds", 60))
    enabled = request.form.get("enabled") == "on"
    actions = request.form.getlist("actions") or ["log"]

    update_monitor_check_settings(
        service_name,
        interval_seconds=interval,
        startup_delay_seconds=startup_delay,
        enabled=enabled,
        actions=actions,
    )
    flash(f"Saved settings for {service_name}", "success")
    return redirect(url_for("monitoring.monitoring_page"))


@monitoring.route("/checks/<service_name>/run", methods=["POST"])
@login_required
def run_check(service_name):
    result = run_monitor_check(service_name)
    status = 200 if not result.get("error") else 400
    return jsonify(result), status


@monitoring.route("/destinations", methods=["POST"])
@login_required
def create_destination():
    name = request.form.get("name")
    destination_type = request.form.get("destination_type")
    enabled = request.form.get("enabled") == "on"
    try:
        config = _build_destination_config(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("monitoring.monitoring_page"))
    if not name or not destination_type:
        flash("Destination name and type are required.", "error")
        return redirect(url_for("monitoring.monitoring_page"))
    add_alert_destination(name, destination_type, config, enabled)
    flash("Alert destination created.", "success")
    return redirect(url_for("monitoring.monitoring_page"))


@monitoring.route("/destinations/<int:destination_id>", methods=["POST"])
@login_required
def edit_destination(destination_id):
    name = request.form.get("name")
    destination_type = request.form.get("destination_type")
    enabled = request.form.get("enabled") == "on"
    try:
        config = _build_destination_config(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("monitoring.monitoring_page"))
    update_alert_destination(
        destination_id,
        name=name,
        destination_type=destination_type,
        config=config,
        enabled=enabled,
    )
    flash("Alert destination updated.", "success")
    return redirect(url_for("monitoring.monitoring_page"))


@monitoring.route("/destinations/<int:destination_id>/delete", methods=["POST"])
@login_required
def remove_destination(destination_id):
    delete_alert_destination(destination_id)
    flash("Alert destination removed.", "success")
    return redirect(url_for("monitoring.monitoring_page"))


@monitoring.route("/destinations/<int:destination_id>/test", methods=["POST"])
@login_required
def test_destination(destination_id):
    destinations = get_alert_destinations(include_disabled=True)
    destination = next((dest for dest in destinations if dest["id"] == destination_id), None)
    if not destination:
        flash("Destination not found.", "error")
        return redirect(url_for("monitoring.monitoring_page"))
    smtp_settings = get_smtp_settings() or {}
    try:
        _send_test_destination(destination, smtp_settings)
        flash(f"Test alert sent via {destination['name']}.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        current_app.logger.exception("Destination test failed")
        flash(f"Failed to send test alert: {exc}", "error")
    return redirect(url_for("monitoring.monitoring_page"))


@monitoring.route("/smtp/settings", methods=["POST"])
@login_required
def update_smtp_settings_route():
    form = request.form
    data = {
        "host": form.get("smtp_host") or None,
        "port": form.get("smtp_port") or None,
        "username": form.get("smtp_username") or None,
        "from_email": form.get("smtp_from_email") or None,
        "use_tls": form.get("smtp_use_tls") == "on",
        "use_ssl": form.get("smtp_use_ssl") == "on",
    }
    password = form.get("smtp_password")
    if password:
        data["password"] = password
    try:
        save_smtp_settings(data)
        flash("SMTP settings saved.", "success")
    except Exception as exc:
        flash(f"Failed to save SMTP settings: {exc}", "error")
    return redirect(url_for("monitoring.monitoring_page"))


@monitoring.route("/smtp/test", methods=["POST"])
@login_required
def test_smtp_defaults():
    recipient = request.form.get("test_recipient")
    if not recipient:
        flash("Enter a recipient email to send a test.", "error")
        return redirect(url_for("monitoring.monitoring_page"))
    smtp_settings = get_smtp_settings() or {}
    if not smtp_settings.get("host"):
        flash("Configure SMTP defaults before sending a test email.", "error")
        return redirect(url_for("monitoring.monitoring_page"))
    destination = {
        "name": "SMTP Defaults",
        "destination_type": "email",
        "config": {
            "email_to": recipient,
            "email_from": smtp_settings.get("from_email"),
        },
    }
    try:
        _send_test_email(destination, smtp_settings)
        flash(f"Test email sent to {recipient}.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        current_app.logger.exception("SMTP defaults test failed")
        flash(f"Failed to send SMTP test email: {exc}", "error")
    return redirect(url_for("monitoring.monitoring_page"))


@monitoring.route("/api/watchdog-config", methods=["GET"])
def watchdog_config():
    expected_token = current_app.config.get("MONITORING_API_TOKEN")
    provided_token = request.headers.get("X-Watchdog-Token") or request.args.get("token")
    if not expected_token or provided_token != expected_token:
        return jsonify({"error": "unauthorized"}), 401

    include_disabled = request.args.get("includeDisabled") == "1"
    config = get_monitoring_config(include_disabled_destinations=include_disabled)
    services = []
    for check in config["checks"]:
        entry = {}
        for key, value in check.items():
            if key == "destinations":
                continue
            if isinstance(value, datetime):
                entry[key] = value.isoformat()
            else:
                entry[key] = value
        entry["destinations"] = []
        for dest in check.get("destinations", []):
            dest_copy = {}
            for d_key, d_value in dest.items():
                if isinstance(d_value, datetime):
                    dest_copy[d_key] = d_value.isoformat()
                else:
                    dest_copy[d_key] = d_value
            entry["destinations"].append(dest_copy)
        services.append(entry)

    destinations_payload = []
    for dest in config["destinations"]:
        dest_copy = {}
        for key, value in dest.items():
            if isinstance(value, datetime):
                dest_copy[key] = value.isoformat()
            else:
                dest_copy[key] = value
        destinations_payload.append(dest_copy)

    smtp_settings = config.get("smtp_settings") or {}
    if smtp_settings:
        for key, value in list(smtp_settings.items()):
            if isinstance(value, datetime):
                smtp_settings[key] = value.isoformat()

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "services": services,
        "destinations": destinations_payload,
        "smtp_settings": smtp_settings,
    }
    return jsonify(payload)

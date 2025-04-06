from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime
from db_interface import (
    get_connection,
    get_vendor_info,
    get_latest_auth_logs,
    get_all_groups,
    lookup_mac_verbose,
)
import pytz

index = Blueprint('index', __name__)

def time_ago(dt):
    if not dt:
        return "n/a"

    tz_name = current_app.config.get('APP_TIMEZONE', 'UTC')
    local_tz = pytz.timezone(tz_name)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)

    dt = dt.astimezone(local_tz)
    now = datetime.now(local_tz)
    diff = now - dt

    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m{seconds % 60}s ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60}m ago"
    else:
        return f"{seconds // 86400}d{(seconds % 86400) // 3600}h ago"

@index.route('/')
def homepage():
    total_users, total_groups = get_summary_counts()
    latest_accept = get_latest_auth_logs('Access-Accept', limit=5)
    latest_reject = get_latest_auth_logs('Access-Reject', limit=5)

    for row in latest_accept + latest_reject:
        row['ago'] = time_ago(row['timestamp'])

    return render_template('index.html',
                           total_users=total_users,
                           total_groups=total_groups,
                           latest_accept=latest_accept,
                           latest_reject=latest_reject)

@index.route('/lookup_mac', methods=['POST'])
def lookup_mac():
    mac = request.form.get('mac', '').strip()
    if not mac:
        return jsonify({"error": "MAC address is required"}), 400

    result = lookup_mac_verbose(mac)
    return jsonify({"mac": mac, "output": result})

def get_summary_counts():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS count FROM users")
    total_users = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) AS count FROM groups")
    total_groups = cursor.fetchone()['count']

    cursor.close()
    return total_users, total_groups

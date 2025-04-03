from flask import Blueprint, render_template, request, current_app, redirect, url_for
from db_interface import get_latest_auth_logs, get_all_groups, get_vendor_info, get_user_by_mac, add_user
import pytz
import humanize
from datetime import datetime, timezone, timedelta

stats = Blueprint('stats', __name__)

def get_time_filter_delta(time_range):
    return {
        "last_minute": timedelta(minutes=1),
        "last_5_minutes": timedelta(minutes=5),
        "last_10_minutes": timedelta(minutes=10),
        "last_hour": timedelta(hours=1),
        "last_6_hours": timedelta(hours=6),
        "last_12_hours": timedelta(hours=12),
        "last_day": timedelta(days=1),
        "last_30_days": timedelta(days=30),
    }.get(time_range)

@stats.route('/stats', methods=['GET', 'POST'])
def stats_page():
    time_range = request.form.get('time_range') or request.args.get('time_range') or 'last_minute'
    limit = 1000  # Fetch enough to allow filtering by time later

    # Timezone setup
    tz_name = current_app.config.get('APP_TIMEZONE', 'UTC')
    local_tz = pytz.timezone(tz_name)

    def is_within_selected_range(ts):
        if time_range == "all":
            return True
        delta = get_time_filter_delta(time_range)
        if not delta or not ts:
            return True
        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (now - ts) <= delta

    def enrich(entry):
        if entry.get('timestamp') and entry['timestamp'].tzinfo is None:
            entry['timestamp'] = entry['timestamp'].replace(tzinfo=timezone.utc)

        local_time = entry['timestamp'].astimezone(local_tz)
        entry['ago'] = humanize.naturaltime(datetime.now(local_tz) - local_time)

        vendor_info = get_vendor_info(entry['mac_address']) or {}
        entry['vendor'] = vendor_info.get('vendor', 'Unknown Vendor')

        user = get_user_by_mac(entry['mac_address'])
        entry['already_exists'] = user is not None
        entry['existing_vlan'] = user['vlan_id'] if user else None
        entry['description'] = user['description'] if user else None

        return entry

    # Get and enrich logs after filtering
    accept_entries = [enrich(e) for e in get_latest_auth_logs('Access-Accept', limit) if is_within_selected_range(e.get('timestamp'))]
    reject_entries = [enrich(e) for e in get_latest_auth_logs('Access-Reject', limit) if is_within_selected_range(e.get('timestamp'))]
    fallback_entries = [enrich(e) for e in get_latest_auth_logs('Accept-Fallback', limit) if is_within_selected_range(e.get('timestamp'))]

    available_groups = get_all_groups()

    return render_template(
        "stats.html",
        accept_entries=accept_entries,
        reject_entries=reject_entries,
        fallback_entries=fallback_entries,
        available_groups=available_groups,
        time_range=time_range
    )

@stats.route('/add', methods=['POST'])
def add():
    mac = request.form['mac_address']
    desc = request.form.get('description', '')
    group_id = request.form.get('group_id')  # keep as string since VARCHAR
    current_app.logger.info(f"Received MAC={mac}, DESC={desc}, VLAN={group_id}")

    add_user(mac, desc, group_id)
    return redirect(url_for('stats.stats_page'))

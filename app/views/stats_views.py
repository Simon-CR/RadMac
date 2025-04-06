from flask import Blueprint, render_template, request, current_app, redirect, url_for, jsonify
from db_interface import get_latest_auth_logs, count_auth_logs, get_all_groups, get_vendor_info, get_user_by_mac, add_user, get_known_mac_vendors
from math import ceil
import pytz
import humanize
from datetime import datetime, timezone, timedelta
from time import sleep
import threading

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

    # Per-card pagination values
    per_page = 25
    page_accept = int(request.args.get('page_accept', 1))
    page_reject = int(request.args.get('page_reject', 1))
    page_fallback = int(request.args.get('page_fallback', 1))

    # Timezone setup
    tz_name = current_app.config.get('APP_TIMEZONE', 'UTC')
    local_tz = pytz.timezone(tz_name)

    # Accept pagination
    total_accept = count_auth_logs('Access-Accept', time_range)
    total_pages_accept = ceil(total_accept / per_page)
    offset_accept = (page_accept - 1) * per_page
    accept_entries = get_latest_auth_logs('Access-Accept', per_page, time_range, offset_accept)

    # Reject pagination
    total_reject = count_auth_logs('Access-Reject', time_range)
    total_pages_reject = ceil(total_reject / per_page)
    offset_reject = (page_reject - 1) * per_page
    reject_entries = get_latest_auth_logs('Access-Reject', per_page, time_range, offset_reject)

    # Fallback pagination
    total_fallback = count_auth_logs('Accept-Fallback', time_range)
    total_pages_fallback = ceil(total_fallback / per_page)
    offset_fallback = (page_fallback - 1) * per_page
    fallback_entries = get_latest_auth_logs('Accept-Fallback', per_page, time_range, offset_fallback)

    def enrich(entry):
        ts = entry.get('timestamp')
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            local_time = ts.astimezone(local_tz)
            entry['ago'] = humanize.naturaltime(datetime.now(local_tz) - local_time)
        else:
            entry['ago'] = 'unknown'

        vendor_info = get_vendor_info(entry['mac_address'], insert_if_found=False)
        entry['vendor'] = vendor_info['vendor'] if vendor_info else None  # placeholder

        user = get_user_by_mac(entry['mac_address'])
        entry['already_exists'] = user is not None
        entry['existing_vlan'] = user['vlan_id'] if user else None
        entry['description'] = user['description'] if user else None

        return entry

    # Enrich entries
    accept_entries = [enrich(e) for e in accept_entries]
    reject_entries = [enrich(e) for e in reject_entries]
    fallback_entries = [enrich(e) for e in fallback_entries]

    available_groups = get_all_groups()

    return render_template(
        "stats.html",
        time_range=time_range,
        accept_entries=accept_entries,
        reject_entries=reject_entries,
        fallback_entries=fallback_entries,
        available_groups=available_groups,

        page_accept=page_accept,
        total_pages_accept=total_pages_accept,

        page_reject=page_reject,
        total_pages_reject=total_pages_reject,

        page_fallback=page_fallback,
        total_pages_fallback=total_pages_fallback
    )

@stats.route('/add', methods=['POST'])
def add():
    mac = request.form['mac_address']
    desc = request.form.get('description', '')
    group_id = request.form.get('group_id')  # keep as string since VARCHAR
    current_app.logger.info(f"Received MAC={mac}, DESC={desc}, VLAN={group_id}")

    add_user(mac, desc, group_id)
    return redirect(url_for('stats.stats_page'))

@stats.route('/lookup_mac_async', methods=['POST'])
def lookup_mac_async():
    data = request.get_json()
    macs = data.get('macs', [])
    results = {}

    rate_limit = int(current_app.config.get("OUI_API_LIMIT_PER_SEC", 2))
    delay = 1.0 / rate_limit if rate_limit > 0 else 0.5

    # Lowercase cleaned prefixes
    prefixes_to_lookup = {}
    for mac in macs:
        prefix = mac.lower().replace(":", "").replace("-", "")[:6]
        prefixes_to_lookup[prefix] = mac  # Use last MAC that used this prefix

    known_vendors = get_known_mac_vendors()  # local DB cache
    vendor_cache = {}  # cache during this request

    for prefix, mac in prefixes_to_lookup.items():
        if prefix in known_vendors:
            results[mac] = known_vendors[prefix]['vendor']
            continue

        if prefix in vendor_cache:
            print(f"→ Prefix {prefix} already queried in this request, skipping.")
            results[mac] = vendor_cache[prefix]
            continue

        info = get_vendor_info(mac)  # will insert into DB
        vendor_name = info.get('vendor', '')
        vendor_cache[prefix] = vendor_name
        results[mac] = vendor_name

        sleep(delay)  # throttle

    return jsonify(results)



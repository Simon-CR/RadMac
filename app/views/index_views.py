from flask import Blueprint, render_template, request, jsonify
from database import get_db
from datetime import datetime
import requests, pytz

index = Blueprint('index', __name__)
OUI_API_URL = 'https://api.maclookup.app/v2/macs/{}'


import pytz  # make sure it's imported if not already

def time_ago(dt):
    if not dt:
        return "n/a"

    tz_name = current_app.config.get('APP_TIMEZONE', 'UTC')
    local_tz = current_app.config.get('TZ', pytz.utc)

    # Only assign UTC tzinfo if naive
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)

    # Convert to app timezone
    dt = dt.astimezone(local_tz)
    now = datetime.now(local_tz)
    diff = now - dt

    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds//60}m{seconds%60}s ago"
    elif seconds < 86400:
        return f"{seconds//3600}h{(seconds%3600)//60}m ago"
    else:
        return f"{seconds//86400}d{(seconds%86400)//3600}h ago"



def lookup_vendor(mac):
    prefix = mac.replace(":", "").replace("-", "").upper()[:6]
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Try local DB first
    cursor.execute("SELECT vendor_name FROM mac_vendor_cache WHERE mac_prefix = %s", (prefix,))
    result = cursor.fetchone()

    if result and result['vendor_name'] != "Unknown Vendor":
        return {"source": "local", "prefix": prefix, "vendor": result['vendor_name']}

    # Try API fallback
    try:
        api_url = OUI_API_URL.format(mac)
        r = requests.get(api_url, timeout=3)
        if r.status_code == 200:
            data = r.json()
            vendor = data.get("company", "Unknown Vendor")

            # Save to DB
            cursor.execute("""
                INSERT INTO mac_vendor_cache (mac_prefix, vendor_name, last_updated)
                VALUES (%s, %s, NOW())
                ON DUPLICATE KEY UPDATE vendor_name = VALUES(vendor_name), last_updated = NOW()
            """, (prefix, vendor))
            db.commit()
            return {"source": "api", "prefix": prefix, "vendor": vendor, "raw": data}
        else:
            return {"source": "api", "prefix": prefix, "error": f"API returned status {r.status_code}", "raw": r.text}
    except Exception as e:
        return {"source": "api", "prefix": prefix, "error": str(e)}
    finally:
        cursor.close()


@index.route('/')
def homepage():
    db = get_db()
    latest_accept = []
    latest_reject = []
    total_users = 0
    total_groups = 0

    if db:
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS count FROM radcheck")
        total_users = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(DISTINCT groupname) AS count FROM radgroupcheck")
        total_groups = cursor.fetchone()['count']

        cursor.execute("""
            SELECT p.username, d.description, p.reply, p.authdate
            FROM radpostauth p
            LEFT JOIN rad_description d ON p.username = d.username
            WHERE p.reply = 'Access-Accept'
            ORDER BY p.authdate DESC LIMIT 5
        """)
        latest_accept = cursor.fetchall()
        for row in latest_accept:
            row['ago'] = time_ago(row['authdate'])

        cursor.execute("""
            SELECT p.username, d.description, p.reply, p.authdate
            FROM radpostauth p
            LEFT JOIN rad_description d ON p.username = d.username
            WHERE p.reply = 'Access-Reject'
            ORDER BY p.authdate DESC LIMIT 5
        """)
        latest_reject = cursor.fetchall()
        for row in latest_reject:
            row['ago'] = time_ago(row['authdate'])

        cursor.close()
        db.close()

    return render_template('index.html',
                           total_users=total_users,
                           total_groups=total_groups,
                           latest_accept=latest_accept,
                           latest_reject=latest_reject)


@index.route('/stats')
def stats():
    db = get_db()
    accept_entries = []
    reject_entries = []
    available_groups = []

    if db:
        cursor = db.cursor(dictionary=True)

        # Fetch available VLANs
        cursor.execute("SELECT DISTINCT groupname FROM radgroupcheck ORDER BY groupname")
        available_groups = [row['groupname'] for row in cursor.fetchall()]

        # Get existing users and map to group
        cursor.execute("""
            SELECT r.username, g.groupname
            FROM radcheck r
            LEFT JOIN radusergroup g ON r.username = g.username
        """)
        existing_user_map = {
            row['username'].replace(":", "").replace("-", "").upper(): row['groupname']
            for row in cursor.fetchall()
        }

        # Access-Reject entries
        cursor.execute("""
            SELECT p.username, d.description, p.reply, p.authdate
            FROM radpostauth p
            LEFT JOIN rad_description d ON p.username = d.username
            WHERE p.reply = 'Access-Reject'
            ORDER BY p.authdate DESC LIMIT 25
        """)
        reject_entries = cursor.fetchall()
        for row in reject_entries:
            normalized = row['username'].replace(":", "").replace("-", "").upper()
            row['vendor'] = lookup_vendor(row['username'])['vendor']
            row['ago'] = time_ago(row['authdate'])

            if normalized in existing_user_map:
                row['already_exists'] = True
                row['existing_vlan'] = existing_user_map[normalized]
            else:
                row['already_exists'] = False
                row['existing_vlan'] = None
                print(f"⚠ Not found in radcheck: {row['username']} → {normalized}")

        # Access-Accept entries
        cursor.execute("""
            SELECT p.username, d.description, p.reply, p.authdate
            FROM radpostauth p
            LEFT JOIN rad_description d ON p.username = d.username
            WHERE p.reply = 'Access-Accept'
            ORDER BY p.authdate DESC LIMIT 25
        """)
        accept_entries = cursor.fetchall()
        for row in accept_entries:
            row['vendor'] = lookup_vendor(row['username'])['vendor']
            row['ago'] = time_ago(row['authdate'])

        cursor.close()
        db.close()

    return render_template('stats.html',
                           accept_entries=accept_entries,
                           reject_entries=reject_entries,
                           available_groups=available_groups)





@index.route('/lookup_mac', methods=['POST'])
def lookup_mac():
    mac = request.form.get('mac', '').strip()
    if not mac:
        return jsonify({"error": "MAC address is required"}), 400

    return jsonify(lookup_vendor(mac))

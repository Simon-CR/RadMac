from flask import current_app
import mysql.connector
import datetime
import requests
import time
import os

def get_connection():
    return mysql.connector.connect(
        host=current_app.config['DB_HOST'],
        user=current_app.config['DB_USER'],
        password=current_app.config['DB_PASSWORD'],
        database=current_app.config['DB_NAME']
    )


def get_all_users():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.*, g.vlan_id AS group_vlan_id, g.description AS group_description,
            mv.vendor_name
        FROM users u
        LEFT JOIN groups g ON u.vlan_id = g.vlan_id
        LEFT JOIN mac_vendors mv
        ON SUBSTRING(REPLACE(REPLACE(u.mac_address, ':', ''), '-', ''), 1, 6) = mv.mac_prefix
    """)
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users



def get_all_groups():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT g.*, (
            SELECT COUNT(*) FROM users WHERE vlan_id = g.vlan_id
        ) AS user_count
        FROM groups g
        ORDER BY g.vlan_id
    """)
    groups = cursor.fetchall()
    cursor.close()
    conn.close()
    return groups



def get_group_by_name(name):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM groups WHERE name = %s", (name,))
    group = cursor.fetchone()
    cursor.close()
    conn.close()
    return group


def add_group(vlan_id, description):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO groups (vlan_id, description) VALUES (%s, %s)", (vlan_id, description))
    conn.commit()
    cursor.close()
    conn.close()


def update_group_description(vlan_id, description):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE groups SET description = %s WHERE id = %s", (description, vlan_id))
    conn.commit()
    cursor.close()
    conn.close()


def delete_group(vlan_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE id = %s", (vlan_id,))
    conn.commit()
    cursor.close()
    conn.close()


def duplicate_group(vlan_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT vlan_id, description FROM groups WHERE id = %s", (vlan_id,))
    group = cursor.fetchone()

    if group:
        new_vlan_id = int(group['vlan_id']) + 1  # Auto-increment logic
        new_description = f"{group['description']} Copy" if group['description'] else None
        cursor.execute("INSERT INTO groups (vlan_id, description) VALUES (%s, %s)", (new_vlan_id, new_description))
        conn.commit()

    cursor.close()
    conn.close()


def add_user(mac_address, description, vlan_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (mac_address, description, vlan_id) VALUES (%s, %s, %s)",
        (mac_address.lower(), description, vlan_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def update_user_description(mac_address, description):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET description = %s WHERE mac_address = %s", (description, mac_address.lower()))
    conn.commit()
    cursor.close()
    conn.close()


def update_user_vlan(mac_address, vlan_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET vlan_id = %s WHERE mac_address = %s", (vlan_id, mac_address.lower()))
    conn.commit()
    cursor.close()
    conn.close()


def delete_user(mac_address):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE mac_address = %s", (mac_address.lower(),))
    conn.commit()
    cursor.close()
    conn.close()


def get_latest_auth_logs(result, limit=10):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM auth_logs WHERE result = %s ORDER BY timestamp DESC LIMIT %s",
        (result, limit)
    )
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    return logs


def get_vendor_info(mac):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    prefix = mac.lower().replace(":", "").replace("-", "")[:6]

    cursor.execute("SELECT vendor FROM mac_vendors WHERE prefix = %s", (prefix,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    return row['vendor'] if row else "Unknown Vendor"


def get_summary_counts():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS count FROM users")
    total_users = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) AS count FROM groups")
    total_groups = cursor.fetchone()['count']

    cursor.close()
    conn.close()
    return total_users, total_groups

def update_description(mac_address, description):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET description = %s WHERE mac_address = %s",
        (description, mac_address.lower())
    )
    conn.commit()
    cursor.close()
    conn.close()

def update_vlan(mac_address, vlan_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET vlan_id = %s WHERE mac_address = %s",
        (vlan_id, mac_address.lower())
    )
    conn.commit()
    cursor.close()
    conn.close()

def refresh_vendors():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all MACs from users table that are missing vendor data
    cursor.execute("""
        SELECT DISTINCT SUBSTRING(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), 1, 6) AS mac_prefix
        FROM users
        WHERE NOT EXISTS (
            SELECT 1 FROM mac_vendors WHERE mac_prefix = SUBSTRING(REPLACE(REPLACE(users.mac_address, ':', ''), '-', ''), 1, 6)
        )
    """)
    prefixes = [row['mac_prefix'].lower() for row in cursor.fetchall()]
    cursor.close()

    if not prefixes:
        conn.close()
        return

    url_template = current_app.config.get("OUI_API_URL", "https://api.maclookup.app/v2/macs/{}")
    api_key = current_app.config.get("OUI_API_KEY", "")
    rate_limit = int(current_app.config.get("OUI_API_LIMIT_PER_SEC", 2))
    daily_limit = int(current_app.config.get("OUI_API_DAILY_LIMIT", 10000))

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    inserted = 0
    cursor = conn.cursor()

    for i, prefix in enumerate(prefixes):
        if inserted >= daily_limit:
            break

        try:
            url = url_template.format(prefix)
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                vendor_name = data.get("company", "not found")
                status = "found"
            elif response.status_code == 404:
                vendor_name = "not found"
                status = "not_found"
            else:
                print(f"Error {response.status_code} for {prefix}")
                continue  # skip insert on unexpected status

            cursor.execute("""
                INSERT INTO mac_vendors (mac_prefix, vendor_name, status, last_checked, last_updated)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    vendor_name = VALUES(vendor_name),
                    status = VALUES(status),
                    last_checked = NOW(),
                    last_updated = NOW()
            """, (prefix, vendor_name, status))
            conn.commit()
            inserted += 1

        except Exception as e:
            print(f"Error fetching vendor for {prefix}: {e}")
            continue

        time.sleep(1.0 / rate_limit)

    cursor.close()
    conn.close()

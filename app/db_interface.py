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
        SELECT 
            u.*, 
            g.vlan_id AS group_vlan_id, 
            g.description AS group_description,
            COALESCE(m.vendor_name, '...') AS vendor
        FROM users u
        LEFT JOIN groups g ON u.vlan_id = g.vlan_id
        LEFT JOIN mac_vendors m ON LOWER(REPLACE(REPLACE(u.mac_address, ':', ''), '-', '')) LIKE CONCAT(m.mac_prefix, '%')
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
    cursor.execute("UPDATE groups SET description = %s WHERE vlan_id = %s", (description, vlan_id))
    conn.commit()
    cursor.close()
    conn.close()


def delete_group(vlan_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE vlan_id = %s", (vlan_id,))
    conn.commit()
    cursor.close()
    conn.close()


def duplicate_group(vlan_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT vlan_id, description FROM groups WHERE vlan_id = %s", (vlan_id,))
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


def get_vendor_info(mac, insert_if_found=True):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    prefix = mac.lower().replace(":", "").replace("-", "")[:6]

    print(f">>> Looking up MAC: {mac} → Prefix: {prefix}")
    print("→ Searching in local database...")
    cursor.execute("SELECT vendor_name, status FROM mac_vendors WHERE mac_prefix = %s", (prefix,))
    row = cursor.fetchone()

    if row:
        print(f"✓ Found locally: {row['vendor_name']} (Status: {row['status']})")
        cursor.close()
        conn.close()
        return {
            "mac": mac,
            "vendor": row['vendor_name'],
            "source": "local",
            "status": row['status']
        }

    print("✗ Not found locally, querying API...")

    url_template = current_app.config.get("OUI_API_URL", "https://api.maclookup.app/v2/macs/{}")
    api_key = current_app.config.get("OUI_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        url = url_template.format(prefix)
        print(f"→ Querying API: {url}")
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            vendor = data.get("company", "").strip()
            if vendor:
                print(f"✓ Found from API: {vendor}")
                if insert_if_found:
                    cursor.execute("""
                        INSERT INTO mac_vendors (mac_prefix, vendor_name, status, last_checked, last_updated)
                        VALUES (%s, %s, 'found', NOW(), NOW())
                        ON DUPLICATE KEY UPDATE
                            vendor_name = VALUES(vendor_name),
                            status = 'found',
                            last_checked = NOW(),
                            last_updated = NOW()
                    """, (prefix, vendor))
                    conn.commit()
                    print("→ Inserted into database (found).")
                return {
                    "mac": mac,
                    "vendor": vendor,
                    "source": "api",
                    "status": "found"
                }

        elif response.status_code == 404:
            print("✗ API returned 404 - vendor not found.")
            if insert_if_found:
                cursor.execute("""
                    INSERT INTO mac_vendors (mac_prefix, vendor_name, status, last_checked, last_updated)
                    VALUES (%s, %s, 'not_found', NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        vendor_name = VALUES(vendor_name),
                        status = 'not_found',
                        last_checked = NOW(),
                        last_updated = NOW()
                """, (prefix, "not found"))
                conn.commit()
                print("→ Inserted into database (not_found).")
            return {
                "mac": mac,
                "vendor": "",
                "source": "api",
                "status": "not_found"
            }

        else:
            print(f"✗ API error: {response.status_code}")
            return {"mac": mac, "vendor": "", "error": f"API error: {response.status_code}"}

    except Exception as e:
        print(f"✗ Exception while querying API: {e}")
        return {"mac": mac, "vendor": "", "error": str(e)}

    finally:
        cursor.close()
        conn.close()

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
                vendor_name = data.get("company", "").strip()
                if vendor_name:
                    status = "found"
                else:
                    # Empty "company" field — skip insert
                    print(f"⚠️ Empty vendor for {prefix}, skipping.")
                    continue
            elif response.status_code == 404:
                vendor_name = "not found"
                status = "not_found"
            else:
                print(f"❌ API error {response.status_code} for {prefix}, skipping.")
                continue

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
            print(f"🚨 Exception fetching vendor for {prefix}: {e}")
            continue

        time.sleep(1.0 / rate_limit)

    cursor.close()
    conn.close()

def lookup_mac_verbose(mac):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    output = []
    prefix = mac.lower().replace(":", "").replace("-", "")[:6]

    output.append(f"🔍 Searching local database for prefix: {prefix}...")

    cursor.execute("SELECT vendor_name, status FROM mac_vendors WHERE mac_prefix = %s", (prefix,))
    row = cursor.fetchone()

    if row:
        output.append(f"✅ Found locally: {row['vendor_name']} (status: {row['status']})")
        cursor.close()
        conn.close()
        return "\n".join(output)

    output.append("❌ Not found locally.")
    output.append("🌐 Querying API...")

    url_template = current_app.config.get("OUI_API_URL", "https://api.maclookup.app/v2/macs/{}")
    api_key = current_app.config.get("OUI_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        url = url_template.format(prefix)
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            vendor_name = data.get("company", "").strip()
            if vendor_name:
                output.append(f"✅ Found via API: {vendor_name}")
                output.append("💾 Inserting into local database...")

                cursor.execute("""
                    INSERT INTO mac_vendors (mac_prefix, vendor_name, status, last_checked, last_updated)
                    VALUES (%s, %s, 'found', NOW(), NOW())
                """, (prefix, vendor_name))
                conn.commit()
            else:
                output.append("⚠️ API responded but no vendor name found. Not inserting.")
        elif response.status_code == 404:
            output.append("❌ Not found via API (404). Not inserting.")
        else:
            output.append(f"❌ API returned unexpected status: {response.status_code}")

    except Exception as e:
        output.append(f"🚨 Exception during API request: {e}")

    cursor.close()
    conn.close()
    return "\n".join(output)


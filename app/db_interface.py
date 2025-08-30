def count_auth_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM auth_users")
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count

def add_auth_user(username, password_hash):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO auth_users (username, password_hash) VALUES (%s, %s)", (username, password_hash))
    conn.commit()
    cursor.close()
    conn.close()

def update_auth_username(user_id, new_username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE auth_users SET username = %s WHERE id = %s", (new_username, user_id))
    conn.commit()
    cursor.close()
    conn.close()

def update_auth_password(user_id, new_password_hash):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE auth_users SET password_hash = %s WHERE id = %s", (new_password_hash, user_id))
    conn.commit()
    cursor.close()
    conn.close()
# ------------------------------
# Web UI Authentication Functions
# ------------------------------
def get_auth_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auth_users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def get_auth_user_by_username(username):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auth_users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user
from flask import current_app, request, redirect, url_for, flash
from db_connection import get_connection
from datetime import datetime, timedelta, timezone
import mysql.connector
import requests
import time
import os
import subprocess
import pytz
import shutil


# ------------------------------
# User Management Functions
# ------------------------------

def get_all_users():
    """Retrieve all users with associated group and vendor information."""
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

def get_user_by_mac(mac_address):
    """Retrieve a user record from the database by MAC address."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM users WHERE mac_address = %s
    """, (mac_address,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def get_users_by_vlan_id(vlan_id):
    """Fetch users assigned to a specific VLAN ID."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT mac_address, description FROM users WHERE vlan_id = %s", (vlan_id,))
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users

def add_user(mac_address, description, vlan_id):
    """Insert a new user with MAC address, description, and VLAN assignment."""
    print(f"→ Adding to DB: mac={mac_address}, desc={description}, vlan={vlan_id}")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (mac_address, description, vlan_id) VALUES (%s, %s, %s)",
        (mac_address.lower(), description, vlan_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

def update_user(mac_address, description, vlan_id):
    """Update both description and VLAN ID for a given MAC address."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET description = %s, vlan_id = %s WHERE mac_address = %s",
        (description, vlan_id, mac_address.lower())
    )
    conn.commit()
    cursor.close()
    conn.close()

def delete_user(mac_address):
    """Remove a user from the database by their MAC address."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE mac_address = %s", (mac_address.lower(),))
    conn.commit()
    cursor.close()
    conn.close()


# ------------------------------
# Group Management Functions
# ------------------------------

def get_all_groups():
    """Retrieve all groups along with user count for each group."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT g.*, (
            SELECT COUNT(*) FROM users WHERE vlan_id = g.vlan_id
        ) AS user_count
        FROM groups g
        ORDER BY g.vlan_id
    """)
    available_groups = cursor.fetchall()
    cursor.close()
    conn.close()
    return available_groups

def add_group(vlan_id, description):
    """Insert a new group with a specified VLAN ID and description."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO groups (vlan_id, description) VALUES (%s, %s)", (vlan_id, description))
    conn.commit()
    cursor.close()
    conn.close()

def update_group_description(vlan_id, description):
    """Update the description for a given MAC address in the users table."""
    # Docstring seems incorrect (mentions MAC address), but keeping original text.
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE groups SET description = %s WHERE vlan_id = %s", (description, vlan_id))
    conn.commit()
    cursor.close()
    conn.close()

def delete_group(vlan_id, force_delete=False):
    """Delete a group, and optionally its associated users if force_delete=True."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if force_delete:
            cursor.execute("DELETE FROM users WHERE vlan_id = %s", (vlan_id,))
        cursor.execute("DELETE FROM groups WHERE vlan_id = %s", (vlan_id,))
        conn.commit()
    except mysql.connector.IntegrityError as e:
        print(f"❌ Cannot delete group '{vlan_id}': it is still in use. Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def delete_group_route():
    """Handle deletion of a group and optionally its users via form POST."""
    # Note: This function interacts with Flask's request/flash/redirect.
    vlan_id = request.form.get("group_id")
    force = request.form.get("force_delete") == "true"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users WHERE vlan_id = %s", (vlan_id,))
    user_count = cursor.fetchone()[0]

    if user_count > 0 and not force:
        conn.close()
        flash("Group has users. Please confirm deletion or reassign users.", "error")
        # Assuming 'group.group_list' is a valid endpoint name
        return redirect(url_for("group.group_list")) 

    try:
        # Consider calling the delete_group() function here for consistency,
        # but keeping original structure as requested.
        if force:
            cursor.execute("DELETE FROM users WHERE vlan_id = %s", (vlan_id,))
        cursor.execute("DELETE FROM groups WHERE vlan_id = %s", (vlan_id,))
        conn.commit()
        flash(f"Group {vlan_id} and associated users deleted." if force else f"Group {vlan_id} deleted.", "success")
    except mysql.connector.IntegrityError as e:
        flash(f"Cannot delete group {vlan_id}: it is still in use. Error: {e}", "error")
    except Exception as e:
        flash(f"Error deleting group: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    
    # Assuming 'group.group_list' is a valid endpoint name
    return redirect(url_for("group.group_list"))


# ------------------------------
# MAC Vendor Functions
# ------------------------------

def get_known_mac_vendors():
    """Fetch all known MAC prefixes and their vendor info from the local database."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT mac_prefix, vendor_name, status FROM mac_vendors")
    entries = cursor.fetchall()
    cursor.close()
    conn.close()

    return {
        row['mac_prefix'].lower(): {
            'vendor': row['vendor_name'],
            'status': row['status']
        }
        for row in entries
    }

def get_vendor_info(mac, insert_if_found=True):
    """Get vendor info for a MAC address, optionally inserting into the database."""
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
        vendor_to_insert = "not found"
        status_to_insert = "not_found"
        result = { "mac": mac, "vendor": "", "source": "api", "status": "not_found" } # Default

        if response.status_code == 200:
            data = response.json()
            vendor = data.get("company", "").strip()

            if vendor:
                print(f"✓ Found from API: {vendor}")
                vendor_to_insert = vendor
                status_to_insert = "found"
                result = { "mac": mac, "vendor": vendor, "source": "api", "status": "found" }
            else:
                print("⚠️ API returned empty company field. Treating as not_found.")
                # vendor/status/result remain default 'not_found'
        elif response.status_code == 404:
            print("✗ API returned 404 - vendor not found.")
            # vendor/status/result remain default 'not_found'
        else:
            print(f"✗ API error: {response.status_code}")
            # Don't insert on other API errors
            result = {"mac": mac, "vendor": "", "error": f"API error: {response.status_code}"}
            # Skip insert logic below by returning early
            cursor.close()
            conn.close()
            return result
            
        # Insert/Update logic (Based on original code's comments, it always inserts/updates)
        # Using 'insert_if_found' flag is ignored as per original code's apparent behaviour
        cursor.execute("""
            INSERT INTO mac_vendors (mac_prefix, vendor_name, status, last_checked, last_updated)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                vendor_name = VALUES(vendor_name),
                status = VALUES(status),
                last_checked = NOW(),
                last_updated = NOW()
        """, (prefix, vendor_to_insert, status_to_insert))
        print(f"→ Inserted/Updated '{vendor_to_insert}' ({status_to_insert}) for {prefix} → rowcount: {cursor.rowcount}")
        conn.commit()
        return result

    except Exception as e:
        print(f"✗ Exception while querying API: {e}")
        return {"mac": mac, "vendor": "", "error": str(e)}

    finally:
        if conn and conn.is_connected():
             if cursor:
                 cursor.close()
             conn.close()

def lookup_mac_verbose(mac):
    """Look up vendor info for a MAC with verbose output, querying API if needed."""
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
        response = requests.get(url, headers=headers, timeout=10) # Add timeout

        if response.status_code == 200:
            data = response.json()
            vendor_name = data.get("company", "").strip()
            if vendor_name:
                output.append(f"✅ Found via API: {vendor_name}")
                output.append("💾 Inserting into local database...")

                # Original code here used simple INSERT, not INSERT...ON DUPLICATE KEY UPDATE
                # Consider changing to match get_vendor_info for consistency if desired.
                # Sticking to original code for now.
                cursor.execute("""
                    INSERT INTO mac_vendors (mac_prefix, vendor_name, status, last_checked, last_updated)
                    VALUES (%s, %s, 'found', NOW(), NOW())
                """, (prefix, vendor_name))
                conn.commit()
                output.append(f"  → Inserted '{vendor_name}' for {prefix} (rowcount: {cursor.rowcount})")
            else:
                output.append("⚠️ API responded but no vendor name found. Not inserting.")
                # Consider inserting 'not_found' status here for consistency? Original code doesn't.
        elif response.status_code == 404:
            output.append("❌ Not found via API (404). Not inserting.")
            # Consider inserting 'not_found' status here for consistency? Original code doesn't.
        else:
            output.append(f"❌ API returned unexpected status: {response.status_code}")

    except requests.exceptions.RequestException as e:
         output.append(f"🚨 Network/Request Exception during API request: {e}")
    except Exception as e:
        output.append(f"🚨 Unexpected Exception during API request: {e}")
        conn.rollback() # Rollback on general exception during DB interaction phase

    finally:
        if conn and conn.is_connected():
             if cursor:
                 cursor.close()
             conn.close()
             
    return "\n".join(output)

def refresh_vendors():
    """Fetch and cache vendor info for unknown MAC prefixes using the API."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all distinct 6-char prefixes from users table that are NOT in mac_vendors table
    cursor.execute("""
        SELECT DISTINCT SUBSTRING(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), 1, 6) AS mac_prefix
        FROM users
        WHERE SUBSTRING(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), 1, 6) NOT IN (
            SELECT mac_prefix FROM mac_vendors
        )
    """)
    prefixes = [row['mac_prefix'].lower() for row in cursor.fetchall() if row['mac_prefix']]
    cursor.close()

    if not prefixes:
        print("→ No unknown MAC prefixes found in users table to refresh.")
        conn.close()
        return

    print(f"→ Found {len(prefixes)} unknown prefixes to look up.")

    url_template = current_app.config.get("OUI_API_URL", "https://api.maclookup.app/v2/macs/{}")
    api_key = current_app.config.get("OUI_API_KEY", "")
    rate_limit = int(current_app.config.get("OUI_API_LIMIT_PER_SEC", 2))
    daily_limit = int(current_app.config.get("OUI_API_DAILY_LIMIT", 10000))

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    inserted_count = 0
    skipped_count = 0
    error_count = 0
    cursor = conn.cursor() # Use standard cursor for inserts

    for i, prefix in enumerate(prefixes):
        if inserted_count >= daily_limit:
            print(f"🛑 Reached daily API limit ({daily_limit}). Stopping refresh.")
            break

        print(f" ({i+1}/{len(prefixes)}) Looking up prefix: {prefix}")

        try:
            url = url_template.format(prefix)
            response = requests.get(url, headers=headers, timeout=10)

            vendor_name = "not found"
            status = "not_found"

            if response.status_code == 200:
                data = response.json()
                api_vendor = data.get("company", "").strip()
                if api_vendor:
                    vendor_name = api_vendor
                    status = "found"
                    print(f"  ✓ Found: {vendor_name}")
                else:
                    print(f"  ⚠️ API OK, but empty vendor for {prefix}. Marked as 'not found'.")
            elif response.status_code == 404:
                print(f"  ✗ Not found (404) for {prefix}.")
            else:
                print(f"  ❌ API error {response.status_code} for {prefix}, skipping insert.")
                error_count += 1
                time.sleep(1.0 / rate_limit)
                continue

            # Insert or Update logic matches get_vendor_info
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
            if cursor.rowcount > 0:
                 inserted_count += 1
                 print(f"  → Stored '{vendor_name}' ({status}) for {prefix}")
            else:
                 print(f"  → No change recorded for {prefix}.")
                 skipped_count +=1

        except requests.exceptions.RequestException as e:
            print(f"  🚨 Network/Request Exception fetching vendor for {prefix}: {e}")
            error_count += 1
        except Exception as e:
            print(f"  🚨 Unexpected Exception fetching vendor for {prefix}: {e}")
            error_count += 1
            conn.rollback()

        time.sleep(1.0 / rate_limit)

    print(f"→ Refresh finished. Inserted/Updated: {inserted_count}, Skipped/No change: {skipped_count}, Errors: {error_count}")
    cursor.close()
    conn.close()


# ------------------------------
# Authentication Log Functions
# ------------------------------

def get_latest_auth_logs(reply_type=None, limit=5, time_range=None, offset=0):
    """Retrieve recent authentication logs filtered by reply type and time range."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    tz_str = current_app.config.get('APP_TIMEZONE', 'UTC')
    try:
        app_tz = pytz.timezone(tz_str)
    except pytz.UnknownTimeZoneError:
        print(f"Warning: Unknown timezone '{tz_str}', falling back to UTC.")
        app_tz = pytz.utc
    now = datetime.now(app_tz)
    print(f"🕒 Using timezone: {tz_str} → Now: {now.isoformat()}")
    
    query_base = "SELECT * FROM auth_logs"
    filters = []
    params = []

    if reply_type == 'Accept-Fallback':
        filters.append("reply = 'Access-Accept'")
        filters.append("result LIKE %s")
        params.append('%Fallback%')
    elif reply_type is not None:
        filters.append("reply = %s")
        params.append(reply_type)

    time_filter_dt = None
    if time_range and time_range != 'all':
        delta = {
            'last_minute': timedelta(minutes=1),
            'last_5_minutes': timedelta(minutes=5),
            'last_10_minutes': timedelta(minutes=10),
            'last_hour': timedelta(hours=1),
            'last_6_hours': timedelta(hours=6),
            'last_12_hours': timedelta(hours=12),
            'last_day': timedelta(days=1),
            'last_30_days': timedelta(days=30)
        }.get(time_range)

        if delta:
            time_filter_dt = now - delta
            print(f"🕒 Filtering logs after: {time_filter_dt.isoformat()}")
            filters.append("timestamp >= %s")
            params.append(time_filter_dt)

    if filters:
        query_base += " WHERE " + " AND ".join(filters)

    query_base += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cursor.execute(query_base, tuple(params))
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    return logs

def count_auth_logs(reply_type=None, time_range=None):
    """Count the number of authentication logs matching a reply type and time."""
    conn = get_connection()
    cursor = conn.cursor()

    tz_str = current_app.config.get('APP_TIMEZONE', 'UTC')
    try:
        app_tz = pytz.timezone(tz_str)
    except pytz.UnknownTimeZoneError:
        print(f"Warning: Unknown timezone '{tz_str}', falling back to UTC.")
        app_tz = pytz.utc
    now = datetime.now(app_tz)
    print(f"🕒 Using timezone: {tz_str} → Now: {now.isoformat()}")
    
    query_base = "SELECT COUNT(*) FROM auth_logs"
    filters = []
    params = []

    if reply_type == 'Accept-Fallback':
        filters.append("reply = 'Access-Accept'")
        filters.append("result LIKE %s")
        params.append('%Fallback%')
    elif reply_type is not None:
        filters.append("reply = %s")
        params.append(reply_type)

    time_filter_dt = None
    if time_range and time_range != 'all':
        delta = {
            'last_minute': timedelta(minutes=1),
            'last_5_minutes': timedelta(minutes=5),
            'last_10_minutes': timedelta(minutes=10),
            'last_hour': timedelta(hours=1),
            'last_6_hours': timedelta(hours=6),
            'last_12_hours': timedelta(hours=12),
            'last_day': timedelta(days=1),
            'last_30_days': timedelta(days=30)
        }.get(time_range)

        if delta:
            time_filter_dt = now - delta
            print(f"🕒 Filtering logs after: {time_filter_dt.isoformat()}")
            filters.append("timestamp >= %s")
            params.append(time_filter_dt)

    if filters:
        query_base += " WHERE " + " AND ".join(filters)

    cursor.execute(query_base, tuple(params))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count


# ------------------------------
# Summary Functions
# ------------------------------

def get_summary_counts():
    """Return total counts of users and groups from the database."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    total_users = 0
    total_groups = 0

    try:
        cursor.execute("SELECT COUNT(*) AS count FROM users")
        result = cursor.fetchone()
        total_users = result['count'] if result else 0

        cursor.execute("SELECT COUNT(*) AS count FROM groups")
        result = cursor.fetchone()
        total_groups = result['count'] if result else 0

    except Exception as e:
        print(f"Error getting summary counts: {e}")
    finally:
        cursor.close()
        conn.close()

    return total_users, total_groups

def get_database_stats():
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    # Get total size of the database
    cursor.execute("""
        SELECT table_schema AS db_name,
               ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS total_mb
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        GROUP BY table_schema
    """)
    row = cursor.fetchone()
    stats["total_size_mb"] = row[1] if row else 0

    # Optional: count total rows in key tables
    cursor.execute("SELECT COUNT(*) FROM auth_logs")
    stats["auth_logs_count"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users")
    stats["users_count"] = cursor.fetchone()[0]

    conn.close()
    return stats

# ------------------------------
# Maintenance Functions
# ------------------------------

def clear_auth_logs():
    """Route to clear authentication logs."""
    from db_connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM auth_logs")
        conn.commit()
        flash("✅ Authentication logs cleared.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"❌ Error clearing logs: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("maintenance.maintenance_page"))

def backup_database():
    """Create a SQL backup of the entire database and return the path to the file."""
    conn = get_connection()
    db_name = conn.database
    user = conn.user
    password = conn._password
    host = conn.server_host if hasattr(conn, 'server_host') else 'localhost'
    conn.close()

    # Check if mysqldump exists
    if not shutil.which("mysqldump"):
        raise Exception("❌ 'mysqldump' command not found. Please install mariadb-client or mysql-client.")

    backup_file = "backup.sql"

    try:
        with open(backup_file, "w") as f:
            subprocess.run(
                ["mysqldump", "-h", host, "-u", user, f"-p{password}", db_name],
                stdout=f,
                check=True
            )
    except subprocess.CalledProcessError as e:
        raise Exception(f"❌ Backup failed: {e}")

    return backup_file

def restore_database(sql_content):
    """Restore the database from raw SQL content (as string)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for statement in sql_content.split(';'):
            stmt = statement.strip()
            if stmt:
                cursor.execute(stmt)
        conn.commit()
        flash("✅ Database restored successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"❌ Error restoring database: {e}", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("maintenance.maintenance_page"))

def get_table_stats():
    """Return a dictionary of table names and their row counts."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        stats = {}

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            count = cursor.fetchone()[0]
            stats[table] = count

        return stats
    except Exception as e:
        print(f"❌ Error retrieving table stats: {e}")
        return None
    finally:
        cursor.close()
        conn.close()
        


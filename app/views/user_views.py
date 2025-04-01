from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from database import get_db
import mysql.connector, os, time, requests

user = Blueprint('user', __name__)  # ✅ Blueprint name = "user"

@user.route('/user_list')
def user_list():
    db = get_db()
    if db is None:
        return "Database connection failed", 500

    cursor = db.cursor(dictionary=True)
    try:
        # Get user info
        cursor.execute("""
            SELECT
                r.username AS mac_address,
                rd.description AS description,
                ug.groupname AS vlan_id,
                mvc.vendor_name AS vendor
            FROM radcheck r
            LEFT JOIN radusergroup ug ON r.username = ug.username
            LEFT JOIN rad_description rd ON r.username = rd.username
            LEFT JOIN mac_vendor_cache mvc ON UPPER(REPLACE(REPLACE(r.username, ':', ''), '-', '')) LIKE CONCAT(mvc.mac_prefix, '%')
        """)
        results = cursor.fetchall()

        # Get available groups
        cursor.execute("SELECT groupname FROM radgroupcheck")
        groups = [{'groupname': row['groupname']} for row in cursor.fetchall()]

        cursor.close()
        db.close()
        return render_template('user_list.html', results=results, groups=groups)

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        cursor.close()
        db.close()
        return "Database error", 500


@user.route('/update_user', methods=['POST'])
def update_user():
    mac_address = request.form['mac_address']
    description = request.form['description']
    vlan_id = request.form['vlan_id']
    new_mac_address = request.form.get('new_mac_address')

    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            db.autocommit = False

            if new_mac_address and new_mac_address != mac_address:
                cursor.execute("""
                    UPDATE radcheck
                    SET username = %s, value = %s
                    WHERE username = %s
                """, (new_mac_address, new_mac_address, mac_address))

                cursor.execute("""
                    UPDATE rad_description
                    SET username = %s, description = %s
                    WHERE username = %s
                """, (new_mac_address, description, mac_address))

                cursor.execute("""
                    UPDATE radusergroup
                    SET username = %s, groupname = %s
                    WHERE username = %s
                """, (new_mac_address, vlan_id, mac_address))
            else:
                cursor.execute("""
                    UPDATE rad_description
                    SET description = %s
                    WHERE username = %s
                """, (description, mac_address))

                cursor.execute("""
                    UPDATE radusergroup
                    SET groupname = %s
                    WHERE username = %s
                """, (vlan_id, mac_address))

            db.commit()
            db.autocommit = True
            cursor.close()
            return "success"

        except Exception as e:
            db.rollback()
            db.autocommit = True
            cursor.close()
            return str(e)
        finally:
            db.close()
    return "Database Connection Failed"


@user.route('/delete_user/<mac_address>')
def delete_user(mac_address):
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            db.autocommit = False
            cursor.execute("DELETE FROM rad_description WHERE username = %s", (mac_address,))
            cursor.execute("DELETE FROM radcheck WHERE username = %s", (mac_address,))
            cursor.execute("DELETE FROM radusergroup WHERE username = %s", (mac_address,))
            db.commit()
            cursor.close()
            db.close()
            return redirect(url_for('user.user_list'))
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return redirect(url_for('user.user_list'))
    return "Database Connection Failed"


@user.route('/add_user', methods=['POST'])
def add_user():
    try:
        data = request.get_json()
        mac_address = data.get('mac_address')
        description = data.get('description')
        vlan_id = data.get('vlan_id')

        if not mac_address:
            return jsonify({'success': False, 'message': 'MAC Address is required'}), 400

        db = get_db()
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection failed'}), 500

        cursor = db.cursor()
        try:
            db.autocommit = False

            cursor.execute("SELECT username FROM radcheck WHERE username = %s", (mac_address,))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'User already exists'}), 400

            cursor.execute("""
                INSERT INTO radcheck (username, attribute, op, value)
                VALUES (%s, 'Cleartext-Password', ':=', %s)
            """, (mac_address, mac_address))

            cursor.execute("""
                INSERT INTO rad_description (username, description)
                VALUES (%s, %s)
            """, (mac_address, description))

            cursor.execute("""
                INSERT INTO radusergroup (username, groupname)
                VALUES (%s, %s)
            """, (mac_address, vlan_id))

            db.commit()
            db.autocommit = True
            cursor.close()
            db.close()
            return jsonify({'success': True, 'message': 'User added successfully'})

        except Exception as e:
            db.rollback()
            db.autocommit = True
            cursor.close()
            db.close()
            return jsonify({'success': False, 'message': str(e)}), 500
    except Exception:
        return jsonify({'success': False, 'message': 'Unknown error'}), 500

@user.route('/add_from_reject', methods=['POST'])
def add_from_reject():
    username = request.form.get('username')
    groupname = request.form.get('groupname')

    if not username or not groupname:
        flash("Missing MAC address or group", "error")
        return redirect(url_for('index.stats'))

    db = get_db()
    cursor = db.cursor()
    try:
        db.autocommit = False

        # Check if already exists
        cursor.execute("SELECT username FROM radcheck WHERE username = %s", (username,))
        if cursor.fetchone():
            flash(f"{username} already exists", "info")
        else:
            cursor.execute("""
                INSERT INTO radcheck (username, attribute, op, value)
                VALUES (%s, 'Cleartext-Password', ':=', %s)
            """, (username, username))

            cursor.execute("""
                INSERT INTO rad_description (username, description)
                VALUES (%s, '')
            """, (username,))

            cursor.execute("""
                INSERT INTO radusergroup (username, groupname)
                VALUES (%s, %s)
            """, (username, groupname))

            db.commit()
            flash(f"{username} added to group {groupname}", "success")

    except Exception as e:
        db.rollback()
        flash(f"Error: {str(e)}", "error")
    finally:
        db.autocommit = True
        cursor.close()
        db.close()

    return redirect(url_for('index.stats'))

@user.route('/refresh_vendors', methods=['POST'])
def refresh_vendors():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    api_url = os.getenv('OUI_API_API_URL', 'https://api.maclookup.app/v2/macs/{}').strip('"')
    api_key = os.getenv('OUI_API_API_KEY', '').strip('"')
    limit = int(os.getenv('OUI_API_RATE_LIMIT', 2))
    headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}

    cursor.execute("""
        SELECT r.username
        FROM radcheck r
        LEFT JOIN mac_vendor_cache m ON UPPER(REPLACE(REPLACE(r.username, ':', ''), '-', '')) LIKE CONCAT(m.mac_prefix, '%')
        WHERE m.vendor_name IS NULL OR m.vendor_name = 'Unknown Vendor'
        LIMIT 5
    """)
    entries = cursor.fetchall()

    if not entries:
        cursor.close()
        db.close()
        return jsonify({"success": True, "updated": 0, "remaining": False})

    updated = 0
    for entry in entries:
        mac = entry['username']
        prefix = mac.replace(':', '').replace('-', '').upper()[:6]

        try:
            r = requests.get(api_url.format(mac), headers=headers, timeout=3)
            if r.status_code == 200:
                data = r.json()
                vendor = data.get("company", "not found")

                cursor.execute("""
                    INSERT INTO mac_vendor_cache (mac_prefix, vendor_name, last_updated)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE vendor_name = VALUES(vendor_name), last_updated = NOW()
                """, (prefix, vendor))
                db.commit()
                updated += 1
        except Exception as e:
            print(f"Error for {mac}: {e}")

        time.sleep(1 / limit)

    cursor.close()
    db.close()

    return jsonify({"success": True, "updated": updated, "remaining": True})

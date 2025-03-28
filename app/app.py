from flask import Flask, render_template, request, redirect, url_for, jsonify
import mysql.connector
import json

app = Flask(__name__)

DB_CONFIG = {
    'host': '192.168.60.150',
    'user': 'user_92z0Kj',
    'password': '5B3UXZV8vyrB',
    'database': 'radius_NIaIuT'
}

def get_db():
    try:
        db = mysql.connector.connect(**DB_CONFIG)
        return db
    except mysql.connector.Error as err:
        print(f"Database Connection Error: {err}")
        return None

@app.route('/', methods=['GET', 'POST'])
def index():
    sql_results = None
    sql_error = None
    total_users = 0
    total_groups = 0

    db = get_db()
    if db:
        cursor = db.cursor(dictionary=True)
        try:
            # Count total users
            cursor.execute("SELECT COUNT(DISTINCT username) as total FROM radcheck;")
            total_users = cursor.fetchone()['total']

            # Count total groups
            cursor.execute("SELECT COUNT(DISTINCT groupname) as total FROM radgroupreply;")
            total_groups = cursor.fetchone()['total']

        except mysql.connector.Error as err:
            print(f"Error fetching counts: {err}")

        cursor.close()
        db.close()

    return render_template('index.html', total_users=total_users, total_groups=total_groups, sql_results=sql_results, sql_error=sql_error)

@app.route('/sql', methods=['POST'])
def sql():
    sql_results = None
    sql_error = None
    sql_query = request.form['query']

    db = get_db()
    if db:
        try:
            cursor = db.cursor(dictionary=True)
            cursor.execute(sql_query)
            sql_results = cursor.fetchall()
            cursor.close()
            db.close()
        except mysql.connector.Error as err:
            sql_error = str(err)
        except Exception as e:
            sql_error = str(e)

    total_users = 0
    total_groups = 0

    db = get_db()
    if db:
        cursor = db.cursor(dictionary=True)
        try:
            # Count total users
            cursor.execute("SELECT COUNT(DISTINCT username) as total FROM radcheck;")
            total_users = cursor.fetchone()['total']

            # Count total groups
            cursor.execute("SELECT COUNT(DISTINCT groupname) as total FROM radgroupreply;")
            total_groups = cursor.fetchone()['total']

        except mysql.connector.Error as err:
            print(f"Error fetching counts: {err}")

        cursor.close()
        db.close()

    return render_template('index.html', total_users=total_users, total_groups=total_groups, sql_results=sql_results, sql_error=sql_error)

@app.route('/user_list')
def user_list():
    """Displays the user list with VLAN IDs."""
    db = get_db()
    if db is None:
        return "Database connection failed", 500

    cursor = db.cursor(dictionary=True)
    try:
        # Fetch users and their group assignments
        cursor.execute("""
            SELECT r.username AS mac_address, r.value AS description, ug.groupname AS vlan_id
            FROM radcheck r
            LEFT JOIN radusergroup ug ON r.username = ug.username
            WHERE r.attribute = 'User-Description'
        """)
        results = cursor.fetchall()

        # Fetch all group names for the dropdown
        cursor.execute("SELECT groupname FROM radgroupcheck")
        groups = cursor.fetchall()
        groups = [{'groupname': row['groupname']} for row in groups] # changed

        cursor.close()
        db.close()
        return render_template('user_list_inline_edit.html', results=results, groups=groups) # added groups
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        cursor.close()
        db.close()
        return "Database error", 500

@app.route('/update_user', methods=['POST'])
def update_user():
    mac_address = request.form['mac_address']
    description = request.form['description']
    vlan_id = request.form['vlan_id']

    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            db.autocommit = False

            cursor.execute("""
                UPDATE radcheck
                SET value = %s
                WHERE username = %s AND attribute = 'User-Description'
            """, (description, mac_address))

            cursor.execute("""
                UPDATE radgroupreply rgr
                SET value = %s
                WHERE rgr.groupname = (SELECT groupname FROM radusergroup rug WHERE rug.username = %s LIMIT 1)
                AND rgr.attribute = 'Tunnel-Private-Group-Id'
            """, (vlan_id, mac_address))

            db.commit()
            db.autocommit = True
            cursor.close()
            return "success"
        except mysql.connector.Error as err:
            db.rollback()
            db.autocommit = True
            cursor.close()
            return str(err)
        except Exception as e:
            db.rollback()
            db.autocommit = True
            cursor.close()
            return str(e)
        finally:
            db.close()
    return "Database Connection Failed"

@app.route('/delete_user/<mac_address>')
def delete_user(mac_address):
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("DELETE FROM radcheck WHERE username = %s", (mac_address,))
            db.commit()
            cursor.close()
            db.close()
            return redirect(url_for('user_list'))
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return redirect(url_for('user_list'))
    return "Database Connection Failed"

@app.route('/edit_user/<mac_address>', methods=['GET', 'POST'])
def edit_user(mac_address):
    db = get_db()
    if db:
        cursor = db.cursor(dictionary=True)

        if request.method == 'POST':
            description = request.form['description']
            vlan_id = request.form['vlan_id']

            cursor.execute("""
                UPDATE radcheck
                SET value = %s
                WHERE username = %s AND attribute = 'User-Description'
            """, (description, mac_address))

            cursor.execute("""
                UPDATE radgroupreply rgr
                SET value = %s
                WHERE rgr.groupname = (SELECT groupname FROM radusergroup rug WHERE rug.username = %s LIMIT 1)
                AND rgr.attribute = 'Tunnel-Private-Group-Id'
            """, (vlan_id, mac_address))

            db.commit()
            cursor.close()
            db.close()
            return redirect(url_for('user_list'))

        else:
            cursor.execute("""
                SELECT
                    rc.username AS mac_address,
                    IFNULL((SELECT value FROM radgroupreply rgr
                             WHERE rgr.groupname = (SELECT groupname FROM radusergroup rug WHERE rug.username = rc.username LIMIT 1)
                             AND rgr.attribute = 'Tunnel-Private-Group-Id' LIMIT 1), 'N/A') AS vlan_id,
                    IFNULL((SELECT value FROM radcheck rch
                             WHERE rch.username = rc.username AND rch.attribute = 'User-Description' LIMIT 1), 'N/A') AS description
                FROM radcheck rc
                WHERE rc.username = %s
                GROUP BY rc.username;
            """, (mac_address,))
            user = cursor.fetchone()
            cursor.close()
            db.close()
            return render_template('edit_user.html', user=user)
    return "Database Connection Failed"

@app.route('/groups')
def groups():
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            # Fetch group names from radgroupcheck
            cursor.execute("SELECT DISTINCT groupname FROM radgroupcheck")
            group_names = [row[0] for row in cursor.fetchall()]

            grouped_results = {}
            for groupname in group_names:
                # Fetch attributes for each group from radgroupreply
                cursor.execute("SELECT id, attribute, op, value FROM radgroupreply WHERE groupname = %s", (groupname,))
                attributes = cursor.fetchall()
                grouped_results[groupname] = [{'id': row[0], 'attribute': row[1], 'op': row[2], 'value': row[3]} for row in attributes]

            cursor.close()
            db.close()
            return render_template('group_list_nested.html', grouped_results=grouped_results)
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            cursor.close()
            db.close()
            return render_template('group_list_nested.html', grouped_results={})
    return "Database Connection Failed"

@app.route('/edit_groupname/<old_groupname>', methods=['GET', 'POST'])
def edit_groupname(old_groupname):
    db = get_db()
    if db:
        cursor = db.cursor(dictionary=True)

        if request.method == 'POST':
            new_groupname = request.form['groupname']
            try:
                db.autocommit = False
                cursor.execute("""
                    UPDATE radgroupreply
                    SET groupname = %s
                    WHERE groupname = %s
                """, (new_groupname, old_groupname))

                cursor.execute("""
                    UPDATE radusergroup
                    SET groupname = %s
                    WHERE groupname = %s
                """, (new_groupname, old_groupname))

                db.commit()
                db.autocommit = True
                cursor.close()
                db.close()
                return redirect(url_for('groups'))
            except mysql.connector.Error as err:
                db.rollback()
                db.autocommit = True
                cursor.close()
                db.close()
                return f"Database Error: {err}"
        else:
            return render_template('edit_groupname.html', old_groupname=old_groupname)
    return "Database Connection Failed"

@app.route('/update_attribute', methods=['POST'])
def update_attribute():
    group_id = request.form['group_id']
    attribute = request.form['attribute']
    op = request.form['op']
    value = request.form['value']

    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            db.autocommit = False
            cursor.execute("""
                UPDATE radgroupreply
                SET attribute = %s, op = %s, value = %s
                WHERE id = %s
            """, (attribute, op, value, group_id))
            db.commit()
            db.autocommit = True
            cursor.close()
            return "success"
        except mysql.connector.Error as err:
            db.rollback()
            db.autocommit = True
            cursor.close()
            return str(err)
        except Exception as e:
            db.rollback()
            db.autocommit = True
            cursor.close()
            return str(e)
        finally:
            db.close()
    return "Database Connection Failed"

@app.route('/add_attribute', methods=['POST'])
def add_attribute():
    groupname = request.form['groupname']
    attribute = request.form['attribute']
    op = request.form['op']
    value = request.form['value']

    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("""
                INSERT INTO radgroupreply (groupname, attribute, op, value)
                VALUES (%s, %s, %s, %s)
            """, (groupname, attribute, op, value))
            db.commit()
            cursor.close()
            db.close()
            return "success"
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return str(err)
    return "Database Connection Failed"

@app.route('/edit_attribute/<group_id>', methods=['GET', 'POST'])
def edit_attribute(group_id):
    db = get_db()
    if db:
        cursor = db.cursor(dictionary=True)

        if request.method == 'POST':
            attribute = request.form['attribute']
            op = request.form['op']
            value = request.form['value']

            try:
                db.autocommit = False
                cursor.execute("""
                    UPDATE radgroupreply
                    SET attribute = %s, op = %s, value = %s
                    WHERE id = %s
                """, (attribute, op, value, group_id))
                db.commit()
                db.autocommit = True
                cursor.close()
                db.close()
                return redirect(url_for('groups'))
            except mysql.connector.Error as err:
                db.rollback()
                db.autocommit = True
                cursor.close()
                db.close()
                return f"Database Error: {err}"

        else:
            cursor.execute("SELECT * FROM radgroupreply WHERE id = %s", (group_id,))
            attribute_data = cursor.fetchone()
            cursor.close()
            db.close()
            return render_template('edit_attribute.html', attribute_data=attribute_data)
    return "Database Connection Failed"

@app.route('/add_group', methods=['POST'])
def add_group():
    groupname = request.form['groupname']

    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES (%s, '', '', '')", (groupname,))
            cursor.execute("INSERT INTO radusergroup (groupname, username) VALUES (%s, '')", (groupname,))
            # Add default values for radgroupcheck
            cursor.execute("INSERT INTO radgroupcheck (groupname, attribute, op, value) VALUES (%s, 'Auth-Type', ':=', 'Accept')", (groupname,))
            db.commit()
            cursor.close()
            db.close()
            return "success"
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return str(err)
    return "Database Connection Failed"

@app.route('/delete_group_rows/<groupname>')
def delete_group_rows(groupname):
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))
            cursor.execute("DELETE FROM radusergroup WHERE groupname = %s", (groupname,))
            cursor.execute("DELETE FROM radgroupcheck WHERE groupname = %s", (groupname,))
            db.commit()
            cursor.close()
            db.close()
            return redirect(url_for('groups'))
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return redirect(url_for('groups'))
    return "Database Connection Failed"

@app.route('/delete_group/<int:group_id>')
def delete_group(group_id):
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("DELETE FROM radgroupreply WHERE id = %s", (group_id,))
            cursor.execute("DELETE FROM radgroupcheck WHERE id = %s", (group_id,)) # Delete from radgroupcheck
            db.commit()
            cursor.close()
            db.close()
            return redirect(url_for('groups'))
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return redirect(url_for('groups'))
    return "Database Connection Failed"

@app.route('/duplicate_group', methods=['POST'])
def duplicate_group():
    groupname = request.form['groupname']
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("SELECT attribute, op, value FROM radgroupreply WHERE groupname = %s", (groupname,))
            attributes = [{'attribute': row[0], 'op': row[1], 'value': row[2]} for row in cursor.fetchall()]
            cursor.close()
            db.close()
            return jsonify(attributes)
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            cursor.close()
            db.close()
            return jsonify([])
    return jsonify([])

@app.route('/save_duplicated_group', methods=['POST'])
def save_duplicated_group():
    data = json.loads(request.data)
    groupname = data['groupname']
    attributes = data['attributes']
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("INSERT INTO radgroupcheck (groupname, attribute, op, value) VALUES (%s, 'Auth-Type', ':=', 'Accept')", (groupname,))
            cursor.execute("INSERT INTO radusergroup (groupname, username) VALUES (%s, '')", (groupname,))
            for attribute in attributes:
                cursor.execute("INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES (%s, %s, %s, %s)", (groupname, attribute['attribute'], attribute['op'], attribute['value']))
            db.commit()
            cursor.close()
            db.close()
            return "success"
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return str(err)
    return "Database Connection Failed"

@app.route('/add_user', methods=['POST'])
def add_user():
    """Adds a new user to the database."""
    try:
        data = request.get_json()  # Get the JSON data from the request
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
            # Check if user already exists
            cursor.execute("SELECT username FROM radcheck WHERE username = %s", (mac_address,))
            if cursor.fetchone():
                cursor.close()
                db.close()
                return jsonify({'success': False, 'message': 'User with this MAC Address already exists'}), 400

            # Insert into radcheck, setting password to MAC address
            cursor.execute("""
                INSERT INTO radcheck (username, attribute, op, value)
                VALUES (%s, 'Cleartext-Password', ':=', %s),
                       (%s, 'User-Description', ':=', %s)
            """, (mac_address, mac_address, mac_address, description)) # Use mac_address for both username and password

            # Insert into radusergroup with the selected group
            cursor.execute("""
                INSERT INTO radusergroup (username, groupname)
                VALUES (%s, %s)
                """, (mac_address, vlan_id))  # Use vlan_id

            db.commit()
            cursor.close()
            db.close()
            return jsonify({'success': True, 'message': 'User added successfully'})

        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            db.rollback()
            cursor.close()
            db.close()
            return jsonify({'success': False, 'message': f"Database error: {err}"}), 500

        except Exception as e:
            print(f"Error adding user: {e}")
            db.rollback()
            cursor.close()
            db.close()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': 'Unknown error'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)

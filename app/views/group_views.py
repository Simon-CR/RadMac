from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from database import get_db
import mysql.connector

group = Blueprint('group', __name__)

@group.route('/groups')
def groups():
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("SELECT DISTINCT groupname FROM radgroupcheck")
            group_names = [row[0] for row in cursor.fetchall()]
            grouped_results = {}

            for groupname in group_names:
                cursor.execute("SELECT id, attribute, op, value FROM radgroupreply WHERE groupname = %s", (groupname,))
                attributes = cursor.fetchall()
                grouped_results[groupname] = [
                    {'id': row[0], 'attribute': row[1], 'op': row[2], 'value': row[3]}
                    for row in attributes
                ]

            cursor.close()
            db.close()
            return render_template('group_list.html', grouped_results=grouped_results)

        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            cursor.close()
            db.close()
            return render_template('group_list.html', grouped_results={})
    return "Database Connection Failed"

@group.route('/save_group', methods=['POST'])
def save_group():
    data = request.get_json()
    groupname = data.get('groupname')
    attributes = data.get('attributes')

    if not groupname or not attributes:
        return jsonify({'error': 'Group name and attributes are required'}), 400

    db = get_db()
    cursor = db.cursor()

    try:
        # Prevent duplicates
        cursor.execute("SELECT 1 FROM radgroupcheck WHERE groupname = %s", (groupname,))
        if cursor.fetchone():
            return jsonify({'error': f'Group name "{groupname}" already exists'}), 400

        # Insert baseline group rule
        cursor.execute("""
            INSERT INTO radgroupcheck (groupname, attribute, op, value)
            VALUES (%s, 'Auth-Type', ':=', 'Accept')
        """, (groupname,))

        # Insert attributes
        for attr in attributes:
            cursor.execute("""
                INSERT INTO radgroupreply (groupname, attribute, op, value)
                VALUES (%s, %s, %s, %s)
            """, (groupname, attr['attribute'], attr['op'], attr['value']))

        db.commit()
        cursor.close()
        db.close()
        return jsonify({'success': True})

    except Exception as e:
        db.rollback()
        cursor.close()
        db.close()
        return jsonify({'error': str(e)}), 500

@group.route('/update_group_name', methods=['POST'])
def update_group_name():
    old_groupname = request.form.get('oldGroupName')
    new_groupname = request.form.get('newGroupName')

    if not old_groupname or not new_groupname:
        return jsonify({'error': 'Both old and new group names are required'}), 400

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE radgroupcheck SET groupname=%s WHERE groupname=%s", (new_groupname, old_groupname))
        cursor.execute("UPDATE radgroupreply SET groupname=%s WHERE groupname=%s", (new_groupname, old_groupname))
        cursor.execute("UPDATE radusergroup SET groupname=%s WHERE groupname=%s", (new_groupname, old_groupname))
        db.commit()
        cursor.close()
        db.close()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.rollback()
        cursor.close()
        db.close()
        return jsonify({'error': str(e)}), 500

@group.route('/update_attribute', methods=['POST'])
def update_attribute():
    attribute_id = request.form.get('attributeId')
    attribute = request.form.get('attribute')
    op = request.form.get('op')
    value = request.form.get('value')

    if not attribute_id or not attribute or not op or not value:
        return jsonify({'error': 'All fields are required'}), 400

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE radgroupreply
            SET attribute=%s, op=%s, value=%s
            WHERE id=%s
        """, (attribute, op, value, attribute_id))
        db.commit()
        cursor.close()
        db.close()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.rollback()
        cursor.close()
        db.close()
        return jsonify({'error': str(e)}), 500

@group.route('/delete_group_rows/<groupname>')
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
            return redirect(url_for('group.groups'))
        except mysql.connector.Error as err:
            db.rollback()
            cursor.close()
            db.close()
            return redirect(url_for('group.groups'))
    return "Database Connection Failed"

@group.route('/delete_group/<int:group_id>')
def delete_group(group_id):
    db = get_db()
    if db:
        cursor = db.cursor()
        try:
            cursor.execute("DELETE FROM radgroupreply WHERE id = %s", (group_id,))
            cursor.execute("DELETE FROM radgroupcheck WHERE id = %s", (group_id,))
            db.commit()
            cursor.close()
            db.close()
            return redirect(url_for('group.groups'))
        except mysql.connector.Error as err:
            db.rollback()
            cursor.close()
            db.close()
            return redirect(url_for('group.groups'))
    return "Database Connection Failed"

@group.route('/duplicate_group', methods=['POST'])
def duplicate_group():
    groupname = request.form.get('groupname')
    if not groupname:
        return jsonify({'error': 'Group name is required'}), 400

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT attribute, op, value FROM radgroupreply WHERE groupname = %s", (groupname,))
        attributes = cursor.fetchall()
        if not attributes:
            return jsonify({'error': f'Group "{groupname}" not found or has no attributes'}), 404

        new_groupname = f"Copy of {groupname}"
        count = 1
        while True:
            cursor.execute("SELECT 1 FROM radgroupcheck WHERE groupname = %s", (new_groupname,))
            if not cursor.fetchone():
                break
            count += 1
            new_groupname = f"Copy of {groupname} ({count})"

        attr_list = [{'attribute': row[0], 'op': row[1], 'value': row[2]} for row in attributes]
        cursor.close()
        db.close()
        return jsonify({'new_groupname': new_groupname, 'attributes': attr_list})

    except Exception as e:
        cursor.close()
        db.close()
        return jsonify({'error': str(e)}), 500

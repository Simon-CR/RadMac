from flask import Blueprint, render_template, request, send_file
import mysql.connector
import os
from db_interface import clear_auth_logs, backup_database, restore_database, get_table_stats # Import the functions from db_interface.py


maintenance = Blueprint('maintenance', __name__, url_prefix='/maintenance')

@maintenance.route('/')
def maintenance_page():
    """Renders the maintenance page."""
    table_stats = get_table_stats()
    return render_template('maintenance.html', table_stats=table_stats)

@maintenance.route('/clear_auth_logs', methods=['POST'])
def clear_auth_logs_route():
    """Route to clear authentication logs."""
    return clear_auth_logs()

@maintenance.route('/backup_database', methods=['GET'])
def backup_database_route():
    """Route to backup the database."""
    try:
        backup_file = backup_database()
        return send_file(backup_file, as_attachment=True, download_name='database_backup.sql')
    except Exception as e:
        return str(e), 500
    finally:
        if os.path.exists('backup.sql'):
            os.remove('backup.sql')

@maintenance.route('/restore_database', methods=['POST'])
def restore_database_route():
    """Route to restore the database."""
    if 'file' not in request.files:
        return "No file provided", 400

    sql_file = request.files['file']
    if sql_file.filename == '':
        return "No file selected", 400

    if not sql_file.filename.endswith('.sql'):
        return "Invalid file type.  Only .sql files are allowed.", 400

    try:
        sql_content = sql_file.read().decode('utf-8')
        message = restore_database(sql_content)
        return message
    except Exception as e:
        return str(e), 500

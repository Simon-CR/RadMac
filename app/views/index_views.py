from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime
from db_interface import (
    get_connection,
    get_vendor_info,
    get_latest_auth_logs,
    get_all_groups,
    lookup_mac_verbose,
)
import pytz
from pyrad.client import Client
from pyrad.dictionary import Dictionary
from pyrad.packet import AccessRequest
import os
import traceback

index = Blueprint('index', __name__)

def time_ago(dt):
    if not dt:
        return "n/a"

    tz_name = current_app.config.get('APP_TIMEZONE', 'UTC')
    local_tz = pytz.timezone(tz_name)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)

    dt = dt.astimezone(local_tz)
    now = datetime.now(local_tz)
    diff = now - dt

    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m{seconds % 60}s ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60}m ago"
    else:
        return f"{seconds // 86400}d{(seconds % 86400) // 3600}h ago"

@index.route('/')
def homepage():
    total_users, total_groups = get_summary_counts()
    latest_accept = get_latest_auth_logs('Access-Accept', limit=5)
    latest_reject = get_latest_auth_logs('Access-Reject', limit=5)

    for row in latest_accept + latest_reject:
        row['ago'] = time_ago(row['timestamp'])

    return render_template('index.html',
                           total_users=total_users,
                           total_groups=total_groups,
                           latest_accept=latest_accept,
                           latest_reject=latest_reject)

@index.route('/lookup_mac', methods=['POST'])
def lookup_mac():
    mac = request.form.get('mac', '').strip()
    if not mac:
        return jsonify({"error": "MAC address is required"}), 400

    result = lookup_mac_verbose(mac)
    return jsonify({"mac": mac, "output": result})

@index.route('/test_radius', methods=['POST'])
def test_radius():
    """Test RADIUS authentication for a given MAC address"""
    mac = request.form.get('mac', '').strip()
    if not mac:
        return jsonify({"error": "MAC address is required"}), 400

    try:
        # Get RADIUS configuration
        radius_host = current_app.config.get('RADIUS_HOST', 'radius')
        radius_port = current_app.config.get('RADIUS_PORT', 1812)
        radius_secret = current_app.config.get('RADIUS_SECRET', 'testing123')

        # Use the existing dictionary file from the radius service
        dict_path = os.path.join(os.path.dirname(__file__), '../../radius/dictionary')
        
        if not os.path.exists(dict_path):
            return jsonify({"error": "RADIUS dictionary file not found"}), 500

        # Create a RADIUS client
        srv = Client(server=radius_host, 
                    secret=radius_secret.encode(),
                    dict=Dictionary(dict_path))

        # Create an authentication request
        req = srv.CreateAuthPacket(code=AccessRequest)
        req["User-Name"] = mac.upper()
        req["User-Password"] = req.PwCrypt(mac.upper())
        
        # Get local IP for display purposes
        import socket
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except:
            local_ip = "127.0.0.1"

        # Send the request
        reply = srv.SendPacket(req)

        # Format the output similar to radtest
        output_lines = []
        
        if reply.code == 2:  # Access-Accept
            output_lines.append(f"Received Access-Accept Id {reply.id} from {radius_host}:{radius_port} to {local_ip}:0 length {len(reply.raw_packet)}")
            
            # Parse and display attributes
            for attr in reply.keys():
                if attr in ['Tunnel-Type', 'Tunnel-Medium-Type', 'Tunnel-Private-Group-Id']:
                    value = reply[attr]
                    if isinstance(value, list):
                        for i, v in enumerate(value):
                            if attr == 'Tunnel-Type':
                                output_lines.append(f"\t{attr}:{i} = VLAN")
                            elif attr == 'Tunnel-Medium-Type':
                                output_lines.append(f"\t{attr}:{i} = IEEE-802")
                            elif attr == 'Tunnel-Private-Group-Id':
                                if isinstance(v, bytes):
                                    v = v.decode('utf-8')
                                output_lines.append(f'\t{attr}:{i} = "{v}"')
                    else:
                        if attr == 'Tunnel-Type':
                            output_lines.append(f"\t{attr}:0 = VLAN")
                        elif attr == 'Tunnel-Medium-Type':
                            output_lines.append(f"\t{attr}:0 = IEEE-802")
                        elif attr == 'Tunnel-Private-Group-Id':
                            if isinstance(value, bytes):
                                value = value.decode('utf-8')
                            output_lines.append(f'\t{attr}:0 = "{value}"')
        
        elif reply.code == 3:  # Access-Reject
            output_lines.append(f"Received Access-Reject Id {reply.id} from {radius_host}:{radius_port} to {local_ip}:0 length {len(reply.raw_packet)}")
            output_lines.append(f"(0) -: Expected Access-Accept got Access-Reject")
        
        else:
            output_lines.append(f"Received unexpected response code: {reply.code}")

        result = "\n".join(output_lines)
        return jsonify({"mac": mac, "output": result})

    except Exception as e:
        error_msg = f"Error testing RADIUS: {str(e)}\n{traceback.format_exc()}"
        current_app.logger.error(error_msg)
        return jsonify({"error": str(e), "output": error_msg}), 500

def get_summary_counts():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS count FROM users")
    total_users = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) AS count FROM groups")
    total_groups = cursor.fetchone()['count']

    cursor.close()
    return total_users, total_groups

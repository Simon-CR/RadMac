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

        # Create a RADIUS client
        # We need to find or create a dictionary file
        dict_path = os.path.join(os.path.dirname(__file__), '../../radius/dictionary')
        if not os.path.exists(dict_path):
            # Fallback to creating a minimal dictionary in memory
            dict_path = '/tmp/radius_dict'
            with open(dict_path, 'w') as f:
                f.write("""
ATTRIBUTE User-Name 1 string
ATTRIBUTE User-Password 2 string
ATTRIBUTE NAS-IP-Address 4 ipaddr
ATTRIBUTE NAS-Port 5 integer
ATTRIBUTE Service-Type 6 integer
ATTRIBUTE Framed-Protocol 7 integer
ATTRIBUTE Framed-IP-Address 8 ipaddr
ATTRIBUTE Framed-IP-Netmask 9 ipaddr
ATTRIBUTE Framed-Routing 10 integer
ATTRIBUTE Filter-Id 11 string
ATTRIBUTE Framed-MTU 12 integer
ATTRIBUTE Framed-Compression 13 integer
ATTRIBUTE Reply-Message 18 string
ATTRIBUTE State 24 octets
ATTRIBUTE Class 25 octets
ATTRIBUTE Vendor-Specific 26 octets
ATTRIBUTE Session-Timeout 27 integer
ATTRIBUTE Idle-Timeout 28 integer
ATTRIBUTE Termination-Action 29 integer
ATTRIBUTE Called-Station-Id 30 string
ATTRIBUTE Calling-Station-Id 31 string
ATTRIBUTE NAS-Identifier 32 string
ATTRIBUTE Proxy-State 33 octets
ATTRIBUTE Acct-Status-Type 40 integer
ATTRIBUTE Acct-Delay-Time 41 integer
ATTRIBUTE Acct-Input-Octets 42 integer
ATTRIBUTE Acct-Output-Octets 43 integer
ATTRIBUTE Acct-Session-Id 44 string
ATTRIBUTE Acct-Authentic 45 integer
ATTRIBUTE Acct-Session-Time 46 integer
ATTRIBUTE Acct-Input-Packets 47 integer
ATTRIBUTE Acct-Output-Packets 48 integer
ATTRIBUTE Acct-Terminate-Cause 49 integer
ATTRIBUTE Event-Timestamp 55 integer
ATTRIBUTE Tunnel-Type 64 integer
ATTRIBUTE Tunnel-Medium-Type 65 integer
ATTRIBUTE Tunnel-Private-Group-Id 81 string
ATTRIBUTE NAS-Port-Type 61 integer
ATTRIBUTE Port-Limit 62 integer

VALUE Service-Type Login-User 1
VALUE Service-Type Framed-User 2
VALUE Service-Type Callback-Login-User 3
VALUE Service-Type Callback-Framed-User 4
VALUE Service-Type Outbound-User 5
VALUE Service-Type Administrative-User 6
VALUE Service-Type NAS-Prompt-User 7
VALUE Service-Type Authenticate-Only 8
VALUE Service-Type Callback-NAS-Prompt 9

VALUE Framed-Protocol PPP 1
VALUE Framed-Protocol SLIP 2

VALUE Tunnel-Type VLAN 13
VALUE Tunnel-Medium-Type IEEE-802 6
""")

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

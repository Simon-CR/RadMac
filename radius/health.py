from flask import Flask, jsonify
import mysql.connector
import os
import socket

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    # Check DB connection
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'db'),
            port=int(os.getenv('DB_PORT', 3306)),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
        )
        conn.close()
        db_status = {"status": "healthy", "message": "Database connection successful"}
        db_healthy = True
    except Exception as e:
        db_status = {"status": "unhealthy", "message": f"Database connection failed: {str(e)}"}
        db_healthy = False

    # Check RADIUS UDP port by sending a real packet
    try:
        radius_port = int(os.getenv('RADIUS_PORT', 1812))
        radius_secret = os.getenv('RADIUS_SECRET', 'testing123').encode()
        
        # We need to resolve the dictionary path just like the main server does
        from pathlib import Path
        import traceback
        
        candidates = [
            Path("/app/dictionary"),
            Path("/app/radius/dictionary"),
            Path(__file__).resolve().parent / "dictionary"
        ]
        
        dict_path = None
        for candidate in candidates:
            if candidate.is_file():
                dict_path = str(candidate)
                break
                
        if not dict_path:
            raise FileNotFoundError("Could not find RADIUS dictionary for health check")
            
        from pyrad.client import Client, Timeout
        from pyrad.dictionary import Dictionary
        
        # Create a pyrad client pointed at localhost
        client = Client(server="127.0.0.1", secret=radius_secret, dict=Dictionary(dict_path))
        client.timeout = 2
        client.retries = 1
        
        # Construct a dummy Access-Request
        # MAC address must be exactly 12 chars to avoid SQL DataError in the radius server logs
        req = client.CreateAuthPacket(code=1, User_Name="001122334455")
        
        # Send the packet and wait for response (Accept or Reject doesn't matter, just need a protocol response)
        try:
            reply = client.SendPacket(req)
            port_status = {"status": "healthy", "message": f"RADIUS server responded successfully on port {radius_port}"}
            port_healthy = True
        except Timeout:
            port_status = {"status": "unhealthy", "message": f"RADIUS server did not respond (timeout) on port {radius_port}"}
            port_healthy = False
            
    except Exception as e:
        # Traceback can be helpful for debugging dictionary issues in the container
        port_status = {"status": "unhealthy", "message": f"RADIUS health ping failed: {str(e)}"}
        port_healthy = False

    overall_healthy = db_healthy and port_healthy
    status = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "database": db_status,
        "udp_port": port_status
    }
    return jsonify(status), 200 if overall_healthy else 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

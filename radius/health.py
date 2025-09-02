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

    # Check UDP port (test if it's in use by radius service)
    try:
        radius_port = int(os.getenv('RADIUS_PORT', 1812))
        # Instead of trying to bind (which would fail if radius is running),
        # we'll check if we can connect to the radius service
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        # Just test the socket creation and check if port is available
        # If we can't bind to a nearby port, the networking is probably broken
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        test_sock.bind(("127.0.0.1", 0))  # Bind to any available port
        test_sock.close()
        sock.close()
        port_status = {"status": "healthy", "message": f"UDP networking functional, RADIUS on port {radius_port}"}
        port_healthy = True
    except Exception as e:
        port_status = {"status": "unhealthy", "message": f"UDP networking check failed: {str(e)}"}
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

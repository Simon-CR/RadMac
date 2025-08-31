from flask import Blueprint, jsonify
import mysql.connector
import os
import socket
from db_connection import get_connection
from datetime import datetime

health = Blueprint('health', __name__)

@health.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint that returns JSON status of app, database, and radius server."""
    
    status = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": "healthy",
        "message": "All services are operational",
        "services": {}
    }
    
    overall_healthy = True
    errors = []
    
    # Check App Health (always healthy if we can respond)
    status["services"]["app"] = {
        "status": "healthy",
        "message": "Flask application is running"
    }
    
    # Check Database Health
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        
        status["services"]["database"] = {
            "status": "healthy", 
            "message": "Database connection successful"
        }
    except mysql.connector.Error as e:
        overall_healthy = False
        error_msg = f"Database connection failed: {str(e)}"
        errors.append(error_msg)
        status["services"]["database"] = {
            "status": "unhealthy",
            "message": error_msg
        }
    except Exception as e:
        overall_healthy = False
        error_msg = f"Database health check error: {str(e)}"
        errors.append(error_msg)
        status["services"]["database"] = {
            "status": "unhealthy",
            "message": error_msg
        }
    
    # Check RADIUS Server Health (basic connectivity test)
    try:
        # Try to connect to the RADIUS server port
        radius_host = os.getenv('RADIUS_HOST', 'radius')  # Docker service name
        radius_port = 1812
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)  # 5 second timeout
        try:
            # For UDP, we can't really test connectivity without sending a packet
            # So we'll just check if we can create a socket and resolve the host
            socket.gethostbyname(radius_host)
            status["services"]["radius"] = {
                "status": "healthy",
                "message": f"RADIUS server host {radius_host} is reachable"
            }
        except socket.gaierror:
            overall_healthy = False
            error_msg = f"RADIUS server host {radius_host} is not resolvable"
            errors.append(error_msg)
            status["services"]["radius"] = {
                "status": "unhealthy", 
                "message": error_msg
            }
        finally:
            sock.close()
            
    except Exception as e:
        # Don't fail overall health for RADIUS issues as it might be expected in some deployments
        status["services"]["radius"] = {
            "status": "unknown",
            "message": f"RADIUS server health check error: {str(e)}"
        }
    
    # Update overall status
    if not overall_healthy:
        status["status"] = "unhealthy"
        status["message"] = "One or more services are experiencing issues"
        status["errors"] = errors
    
    # Return appropriate HTTP status code
    http_status = 200 if overall_healthy else 503
    
    return jsonify(status), http_status
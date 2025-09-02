#!/usr/bin/env python3
"""
Simple HTTP health proxy for MariaDB
Translates MariaDB health checks to HTTP endpoints for monitoring
"""
from flask import Flask, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Use mariadb-admin ping to check database health
        root_password = os.getenv('MARIADB_ROOT_PASSWORD', '')
        
        # Run the same health check as Docker
        result = subprocess.run([
            'mariadb-admin', 'ping', 
            '-h', 'localhost', 
            '-u', 'root', 
            f'-p{root_password}'
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            return jsonify({
                "status": "healthy",
                "message": "Database is responding",
                "service": "mariadb"
            }), 200
        else:
            return jsonify({
                "status": "unhealthy",
                "message": f"Database ping failed: {result.stderr}",
                "service": "mariadb"
            }), 503
            
    except subprocess.TimeoutExpired:
        return jsonify({
            "status": "unhealthy",
            "message": "Database ping timed out",
            "service": "mariadb"
        }), 503
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "message": f"Health check error: {str(e)}",
            "service": "mariadb"
        }), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

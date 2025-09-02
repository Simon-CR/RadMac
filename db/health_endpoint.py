#!/usr/bin/env python3
"""
Simple HTTP Health Endpoint for MariaDB (no Flask dependency)
"""
import http.server
import socketserver
import subprocess
import json
import os
import time
import socket
import threading

def check_mariadb():
    """Check MariaDB health using mariadb-admin ping"""
    try:
        root_password = os.getenv('MARIADB_ROOT_PASSWORD', '')
        result = subprocess.run([
            'mariadb-admin', 'ping', 
            '-h', 'localhost', 
            '-u', 'root', 
            f'-p{root_password}'
        ], capture_output=True, text=True, timeout=5)
        
        return result.returncode == 0, result.stderr if result.returncode != 0 else None
    except subprocess.TimeoutExpired:
        return False, "Database ping timed out"
    except Exception as e:
        return False, f"Health check error: {str(e)}"

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.health_check()
        elif self.path == '/ping':
            self.ping()
        else:
            self.send_response(404)
            self.end_headers()
            
    def health_check(self):
        healthy, error = check_mariadb()
        
        response = {
            "status": "healthy" if healthy else "unhealthy",
            "service": "mariadb",
            "timestamp": time.time(),
            "container": socket.gethostname()
        }
        
        if error:
            response["error"] = error
            
        self.send_response(200 if healthy else 503)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
        
    def ping(self):
        response = {"status": "ok", "service": "mariadb-health-endpoint"}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        # Suppress default logging
        pass

if __name__ == '__main__':
    PORT = 8080
    Handler = HealthHandler
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Health endpoint serving on port {PORT}")
        httpd.serve_forever()

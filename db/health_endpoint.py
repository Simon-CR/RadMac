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
    """Comprehensive MariaDB health check including connection handling"""
    try:
        root_password = os.getenv('MARIADB_ROOT_PASSWORD', '')
        
        # Basic ping test
        ping_result = subprocess.run([
            'mariadb-admin', 'ping', 
            '-h', 'localhost', 
            '-u', 'root', 
            f'-p{root_password}'
        ], capture_output=True, text=True, timeout=3)
        
        if ping_result.returncode != 0:
            return False, f"Database ping failed: {ping_result.stderr}"
        
        # Test actual connection and query execution
        query_result = subprocess.run([
            'mariadb', '-h', 'localhost', '-u', 'root', f'-p{root_password}',
            '-e', 'SELECT 1 as health_check; SHOW STATUS LIKE "Threads_connected";'
        ], capture_output=True, text=True, timeout=5)
        
        if query_result.returncode != 0:
            return False, f"Database query failed: {query_result.stderr}"
        
        # Check for connection issues in recent logs
        processlist_result = subprocess.run([
            'mariadb', '-h', 'localhost', '-u', 'root', f'-p{root_password}',
            '-e', 'SHOW STATUS LIKE "Aborted_connects"; SHOW STATUS LIKE "Threads_connected";'
        ], capture_output=True, text=True, timeout=3)
        
        if processlist_result.returncode != 0:
            return False, f"Connection status check failed: {processlist_result.stderr}"
            
        # Parse connection metrics
        output_lines = processlist_result.stdout.strip().split('\n')
        metrics = {}
        for line in output_lines:
            if '\t' in line:
                parts = line.split('\t')
                if len(parts) >= 2:
                    metrics[parts[0]] = parts[1]
        
        # Check if we have excessive aborted connections or high thread count
        aborted_connects = int(metrics.get('Aborted_connects', '0'))
        threads_connected = int(metrics.get('Threads_connected', '0'))
        
        warnings = []
        if threads_connected > 100:
            warnings.append(f"High connection count: {threads_connected}")
        if aborted_connects > 50:  # Configurable threshold
            warnings.append(f"High aborted connections: {aborted_connects}")
        
        return True, warnings if warnings else None
        
    except subprocess.TimeoutExpired:
        return False, "Database health check timed out"
    except ValueError as e:
        return False, f"Metrics parsing error: {str(e)}"
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
    
    def do_POST(self):
        if self.path == '/recover':
            self.trigger_recovery()
        else:
            self.send_response(404)
            self.end_headers()
            
    def health_check(self):
        healthy, error_or_warnings = check_mariadb()
        
        response = {
            "status": "healthy" if healthy else "unhealthy",
            "service": "mariadb",
            "timestamp": time.time(),
            "container": socket.gethostname()
        }
        
        if not healthy:
            response["error"] = error_or_warnings
        elif error_or_warnings:  # Warnings for healthy but concerning state
            response["warnings"] = error_or_warnings
            response["status"] = "degraded"  # New status for issues but still functional
            
        # Return 503 for unhealthy, 200 for healthy/degraded
        status_code = 503 if not healthy else 200
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
        
    def ping(self):
        response = {"status": "ok", "service": "mariadb-health-endpoint"}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
        
    def trigger_recovery(self):
        """HTTP endpoint for triggering database recovery"""
        try:
            # Execute the recovery script
            result = subprocess.run([
                'python3', '/usr/local/bin/recovery_script.py'
            ], capture_output=True, text=True, timeout=30)
            
            response = {
                "status": "completed" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "timestamp": time.time()
            }
            
            status_code = 200 if result.returncode == 0 else 500
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except subprocess.TimeoutExpired:
            response = {
                "status": "failed",
                "error": "Recovery script timed out",
                "timestamp": time.time()
            }
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        except Exception as e:
            response = {
                "status": "failed", 
                "error": f"Recovery execution failed: {str(e)}",
                "timestamp": time.time()
            }
            self.send_response(500)
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

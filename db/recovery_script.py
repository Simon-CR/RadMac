#!/usr/bin/env python3
"""
Database Recovery Script for Connection Issues
Cleans up stale connections and resets connection pools
"""
import subprocess
import os
import sys
import time

def run_mariadb_command(command, timeout=10):
    """Execute a MariaDB command safely"""
    try:
        root_password = os.getenv('MARIADB_ROOT_PASSWORD', '')
        result = subprocess.run([
            'mariadb', '-h', 'localhost', '-u', 'root', f'-p{root_password}',
            '-e', command
        ], capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def kill_stale_connections():
    """Kill connections that have been sleeping for too long"""
    print("Checking for stale connections...")
    
    # Get list of sleeping connections older than 5 minutes
    success, output, error = run_mariadb_command(
        "SELECT ID, USER, HOST, DB, TIME FROM information_schema.PROCESSLIST "
        "WHERE COMMAND = 'Sleep' AND TIME > 300 AND USER != 'root';"
    )
    
    if not success:
        print(f"Failed to get processlist: {error}")
        return False
    
    killed_count = 0
    for line in output.strip().split('\n')[1:]:  # Skip header
        if line.strip():
            parts = line.split('\t')
            if len(parts) >= 1:
                connection_id = parts[0]
                print(f"Killing stale connection {connection_id}")
                kill_success, _, kill_error = run_mariadb_command(f"KILL {connection_id};")
                if kill_success:
                    killed_count += 1
                else:
                    print(f"Failed to kill connection {connection_id}: {kill_error}")
    
    print(f"Killed {killed_count} stale connections")
    return True

def flush_privileges_and_status():
    """Flush privileges and reset status counters"""
    print("Flushing privileges and status...")
    
    commands = [
        "FLUSH PRIVILEGES;",
        "FLUSH STATUS;",
        "FLUSH HOSTS;",
    ]
    
    for cmd in commands:
        success, output, error = run_mariadb_command(cmd)
        if not success:
            print(f"Failed to execute {cmd}: {error}")
            return False
        print(f"Executed: {cmd}")
    
    return True

def get_connection_stats():
    """Get current connection statistics"""
    success, output, error = run_mariadb_command(
        "SHOW STATUS WHERE Variable_name IN ('Threads_connected', 'Threads_running', "
        "'Aborted_connects', 'Aborted_clients', 'Max_used_connections');"
    )
    
    if success:
        print("Current connection statistics:")
        for line in output.strip().split('\n'):
            if '\t' in line:
                print(f"  {line.replace(chr(9), ': ')}")
    else:
        print(f"Failed to get connection stats: {error}")

def main():
    print("Starting database recovery process...")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show current stats
    get_connection_stats()
    
    # Kill stale connections
    if not kill_stale_connections():
        print("Failed to clean up stale connections")
        sys.exit(1)
    
    # Flush privileges and status
    if not flush_privileges_and_status():
        print("Failed to flush privileges/status")
        sys.exit(1)
    
    # Show stats after cleanup
    print("\nAfter cleanup:")
    get_connection_stats()
    
    print("Database recovery completed successfully")

if __name__ == '__main__':
    main()
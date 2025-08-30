"""
Database migration script for RadMac: ensures auth_users table exists.
Run this at container startup before launching the app.
"""
from db_connection import get_connection
import os
import subprocess
from datetime import datetime

CREATE_AUTH_USERS_SQL = """
CREATE TABLE IF NOT EXISTS auth_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def backup_database():
    """Create a backup of the database before migration."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"/app/logs/db_backup_pre_migration_{timestamp}.sql"
        
        # Ensure logs directory exists
        os.makedirs("/app/logs", exist_ok=True)
        
        # Get database connection details from environment
        db_host = os.environ.get('MYSQL_HOST', 'localhost')
        db_user = os.environ.get('MYSQL_USER', 'root')
        db_password = os.environ.get('MYSQL_PASSWORD', '')
        db_name = os.environ.get('MYSQL_DATABASE', 'radmac')
        
        # Create mysqldump command
        cmd = [
            'mysqldump',
            f'--host={db_host}',
            f'--user={db_user}',
            f'--password={db_password}',
            '--single-transaction',
            '--routines',
            '--triggers',
            db_name
        ]
        
        # Execute backup
        with open(backup_filename, 'w') as backup_file:
            result = subprocess.run(cmd, stdout=backup_file, stderr=subprocess.PIPE, text=True)
            
        if result.returncode == 0:
            print(f"[DB BACKUP] Database backup created: {backup_filename}")
            return True
        else:
            print(f"[DB BACKUP] Warning: Backup failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[DB BACKUP] Warning: Could not create backup: {e}")
        return False

def migrate():
    # Create backup before migration
    backup_database()
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_AUTH_USERS_SQL)
    
    # Also update existing column if it's too small
    try:
        cursor.execute("ALTER TABLE auth_users MODIFY COLUMN password_hash VARCHAR(255) NOT NULL")
        print("[DB MIGRATION] auth_users.password_hash column updated to VARCHAR(255).")
    except Exception as e:
        # Column might already be correct size or table might not exist yet
        pass
    
    conn.commit()
    cursor.close()
    conn.close()
    print("[DB MIGRATION] auth_users table ensured.")

if __name__ == "__main__":
    migrate()

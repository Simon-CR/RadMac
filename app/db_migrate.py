"""
Database migration script for RadMac: ensures auth_users table exists.
Run this at container startup before launching the app.
"""
from db_connection import get_connection
import os
import subprocess
from datetime import datetime

CREATE_SCHEMA_VERSION_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_AUTH_USERS_SQL = """
CREATE TABLE IF NOT EXISTS auth_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def get_current_schema_version(cursor):
    """Get the current schema version from the database."""
    try:
        cursor.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception:
        # schema_version table doesn't exist yet
        return 0

def set_schema_version(cursor, version):
    """Set the current schema version in the database."""
    cursor.execute("INSERT INTO schema_version (version) VALUES (%s)", (version,))

def backup_database():
    """Create a backup of the database before migration."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"/app/logs/db_backup_pre_migration_{timestamp}.sql"
        
        # Ensure logs directory exists
        os.makedirs("/app/logs", exist_ok=True)
        
        # Get database connection details from environment
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_user = os.environ.get('DB_USER', 'root')
        db_password = os.environ.get('DB_PASSWORD', '')
        db_name = os.environ.get('DB_NAME', 'radmac')
        
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
    # Define the current schema version
    CURRENT_VERSION = 1
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Ensure schema_version table exists first
        cursor.execute(CREATE_SCHEMA_VERSION_SQL)
        conn.commit()
        
        # Check current version
        current_version = get_current_schema_version(cursor)
        print(f"[DB MIGRATION] Current schema version: {current_version}")
        
        if current_version >= CURRENT_VERSION:
            print(f"[DB MIGRATION] Schema is up to date (version {current_version}). No migration needed.")
            cursor.close()
            conn.close()
            return
        
        # Create backup before migration
        print(f"[DB MIGRATION] Upgrading schema from version {current_version} to {CURRENT_VERSION}")
        backup_database()
        
        # Apply migrations based on current version
        if current_version < 1:
            # Migration to version 1: ensure auth_users table and column size
            cursor.execute(CREATE_AUTH_USERS_SQL)
            try:
                cursor.execute("ALTER TABLE auth_users MODIFY COLUMN password_hash VARCHAR(255) NOT NULL")
                print("[DB MIGRATION] auth_users.password_hash column updated to VARCHAR(255).")
            except Exception as e:
                # Column might already be correct size or table might not exist yet
                pass
            
            set_schema_version(cursor, 1)
            print("[DB MIGRATION] Upgraded to schema version 1.")
        
        # Future migrations would go here:
        # if current_version < 2:
        #     # Migration to version 2
        #     cursor.execute("ALTER TABLE users ADD COLUMN new_field VARCHAR(255)")
        #     set_schema_version(cursor, 2)
        #     print("[DB MIGRATION] Upgraded to schema version 2.")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("[DB MIGRATION] Migration completed successfully.")
        
    except Exception as e:
        print(f"[DB MIGRATION] Warning: Could not connect to database: {e}")
        print("[DB MIGRATION] Skipping migration - database may not be ready yet.")
        # Don't exit with error code, let the app start anyway

if __name__ == "__main__":
    migrate()

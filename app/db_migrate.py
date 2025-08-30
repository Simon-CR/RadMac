"""
Database migration script for RadMac: ensures auth_users table exists.
Run this at container startup before launching the app.
"""
from db_connection import get_connection

CREATE_AUTH_USERS_SQL = """
CREATE TABLE IF NOT EXISTS auth_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def migrate():
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

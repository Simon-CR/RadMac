import mysql.connector
from mysql.connector import pooling
import os
import time

# Create connection pool for better reliability
_connection_pool = None

def init_connection_pool():
    """Initialize the database connection pool"""
    global _connection_pool
    if _connection_pool is None:
        try:
            db_config = {
                'host': os.getenv('DB_HOST'),
                'port': int(os.getenv('DB_PORT', 3306)),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'database': os.getenv('DB_NAME'),
                'autocommit': True,
                'pool_name': 'app_pool',
                'pool_size': 10,
                'pool_reset_session': True,
                'connect_timeout': 20,  # Increased from 10
                'charset': 'utf8mb4',
                'collation': 'utf8mb4_unicode_ci',
                # Additional settings to handle network issues better
                'connection_timeout': 20,
                'sql_mode': '',
                'raise_on_warnings': False,
                'use_unicode': True,
                # Network resilience settings
                'net_read_timeout': 60,
                'net_write_timeout': 60
            }
            
            _connection_pool = mysql.connector.pooling.MySQLConnectionPool(**db_config)
            print("✅ App database connection pool initialized successfully")
            
        except Exception as e:
            print(f"❌ Failed to initialize app database connection pool: {e}")
            raise

def get_connection():
    """Get a database connection with automatic retry and better error handling"""
    global _connection_pool
    
    # Initialize pool if needed
    if _connection_pool is None:
        init_connection_pool()
    
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            conn = _connection_pool.get_connection()
            conn.ping(reconnect=True)
            return conn
            
        except mysql.connector.Error as e:
            print(f"❌ Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print("❌ All database connection attempts failed")
                raise
        except Exception as e:
            print(f"❌ Unexpected error getting database connection: {e}")
            raise

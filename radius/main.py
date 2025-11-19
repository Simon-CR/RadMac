from pyrad.server import Server, RemoteHost
from pyrad.dictionary import Dictionary
from pyrad.packet import AccessAccept, AccessReject
from datetime import datetime, timezone
import mysql.connector
from mysql.connector import pooling
import os
import traceback
import logging
import time
from pathlib import Path

DEFAULT_VLAN_ID = os.getenv("DEFAULT_VLAN", "505")
DENIED_VLAN = os.getenv("DENIED_VLAN", "999")

class MacRadiusServer(Server):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create connection pool instead of single connection
        try:
            self.db_config = {
                'host': os.getenv('DB_HOST'),
                'port': int(os.getenv('DB_PORT', 3306)),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'database': os.getenv('DB_NAME'),
                'autocommit': True,
                'pool_name': 'radius_pool',
                'pool_size': 5,
                'pool_reset_session': True,
                'connect_timeout': 20,  # Increased from 10
                'charset': 'utf8mb4',
                'collation': 'utf8mb4_unicode_ci',
                # Additional network resilience settings
                'connection_timeout': 20,
                'sql_mode': '',
                'raise_on_warnings': False,
                'use_unicode': True
            }
            
            self.connection_pool = mysql.connector.pooling.MySQLConnectionPool(**self.db_config)
            
            # Test the connection pool
            test_conn = self.connection_pool.get_connection()
            test_conn.ping(reconnect=True)
            test_conn.close()
            print("✅ Successfully created database connection pool.")
            
        except Exception as e:
            print("❌ Failed to create database connection pool.")
            traceback.print_exc()
            raise
    
    def get_db_connection(self):
        """Get a database connection from the pool with improved error handling."""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                connection = self.connection_pool.get_connection()
                if connection.is_connected():
                    # Ensure connection is in autocommit mode for consistency
                    connection.autocommit = True
                    return connection
                else:
                    connection.close()
                    raise mysql.connector.Error("Connection not active")
            except mysql.connector.Error as e:
                logging.warning(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    # Try to reset the pool on failure
                    try:
                        if hasattr(self, 'connection_pool'):
                            # Create a new pool connection to test
                            test_conn = mysql.connector.connect(**self.db_config)
                            test_conn.close()
                    except:
                        pass
                else:
                    logging.error(f"Failed to get database connection after {max_retries} attempts")
                    raise
        
        return None

    def HandleAuthPacket(self, pkt):
        print(f"\n📡 Received RADIUS Auth Request")
        connection = None
        cursor = None
        
        try:
            username = pkt['User-Name'][0].upper()
            print(f"→ Parsed MAC: {username}")
            print(f"→ Attributes: {[f'{k}={v}' for k, v in pkt.items()]}")

            # Get connection from pool
            connection = self.get_db_connection()
            cursor = connection.cursor(dictionary=True)
            now_utc = datetime.now(timezone.utc)

            cursor.execute("SELECT vlan_id FROM users WHERE mac_address = %s", (username,))
            result = cursor.fetchone()

            reply = self.CreateReplyPacket(pkt)

            if result:
                vlan_id = result['vlan_id']
                denied_vlan = os.getenv("DENIED_VLAN", "999")

                if vlan_id == denied_vlan:
                    print(f"🚫 MAC {username} found, but on denied VLAN {vlan_id}")
                    reply.code = AccessReject
                    cursor.execute("""
                        INSERT INTO auth_logs (mac_address, reply, result, timestamp)
                        VALUES (%s, %s, %s, %s)
                    """, (username, "Access-Reject", f"Denied due to VLAN {denied_vlan}", now_utc))
                else:
                    print(f"✅ MAC {username} found, assigning VLAN {vlan_id}")
                    reply.code = AccessAccept
                    reply.AddAttribute("Tunnel-Type", 13)
                    reply.AddAttribute("Tunnel-Medium-Type", 6)
                    reply.AddAttribute("Tunnel-Private-Group-Id", vlan_id)
                    cursor.execute("""
                        INSERT INTO auth_logs (mac_address, reply, result, timestamp)
                        VALUES (%s, %s, %s, %s)
                    """, (username, "Access-Accept", f"Assigned to VLAN {vlan_id}", now_utc))
            else:
                print(f"⚠️ MAC {username} not found, assigning fallback VLAN {DEFAULT_VLAN_ID}")
                reply.code = AccessAccept
                reply["Tunnel-Type"] = 13
                reply["Tunnel-Medium-Type"] = 6
                reply["Tunnel-Private-Group-Id"] = DEFAULT_VLAN_ID
                cursor.execute("""
                    INSERT INTO auth_logs (mac_address, reply, result, timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (username, "Access-Accept", f"Assigned to fallback VLAN {DEFAULT_VLAN_ID}", now_utc))

            # Commit the transaction
            connection.commit()
            
            self.SendReplyPacket(pkt.fd, reply)
            print(f"📤 Response sent: {'Access-Accept' if reply.code == AccessAccept else 'Access-Reject'}\n")

        except Exception as e:
            print("❌ Error processing request:")
            traceback.print_exc()
            # Rollback on error
            if connection:
                try:
                    connection.rollback()
                except:
                    pass

        finally:
            # Always clean up resources
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if connection:
                try:
                    connection.close()  # Return connection to pool
                except:
                    pass

def resolve_dictionary_path():
    """Resolve the RADIUS dictionary path across Docker/local environments."""
    candidates = []

    env_path = os.getenv("RADIUS_DICTIONARY_PATH")
    if env_path:
        candidates.append(Path(env_path))

    script_dir = Path(__file__).resolve().parent
    candidates.extend([
        script_dir / "dictionary",
        script_dir / "radius" / "dictionary",
        Path("/app/dictionary"),
        Path("/app/radius/dictionary")
    ])

    # Walk the script directory to find any file literally named "dictionary"
    for root, _, files in os.walk(script_dir):
        if "dictionary" in files:
            candidates.append(Path(root) / "dictionary")

    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            print(f"📚 Using RADIUS dictionary at: {candidate}")
            return str(candidate)

    raise FileNotFoundError(
        "RADIUS dictionary file not found in expected locations. "
        "Set RADIUS_DICTIONARY_PATH to override."
    )


if __name__ == '__main__':
    print("🚀 Starting MacRadiusServer...")
    dictionary_path = resolve_dictionary_path()
    srv = MacRadiusServer(dict=Dictionary(dictionary_path))
    srv.hosts["0.0.0.0"] = RemoteHost("0.0.0.0", os.getenv("RADIUS_SECRET", "testing123").encode(), "localhost")
    print("📡 Listening on 0.0.0.0 for incoming RADIUS requests...")
    srv.BindToAddress("0.0.0.0")
    srv.Run()

from pyrad.server import Server, RemoteHost
from pyrad.dictionary import Dictionary
from pyrad.packet import AccessAccept, AccessReject
from datetime import datetime, timezone
import mysql.connector
from mysql.connector import pooling
import os
import traceback

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
                'connect_timeout': 10,
                'charset': 'utf8mb4',
                'collation': 'utf8mb4_unicode_ci'
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
        """Get a connection from the pool with automatic reconnection"""
        try:
            conn = self.connection_pool.get_connection()
            conn.ping(reconnect=True)
            return conn
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            traceback.print_exc()
            raise

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

if __name__ == '__main__':
    print("🚀 Starting MacRadiusServer...")
    srv = MacRadiusServer(dict=Dictionary("dictionary"))
    srv.hosts["0.0.0.0"] = RemoteHost("0.0.0.0", os.getenv("RADIUS_SECRET", "testing123").encode(), "localhost")
    print("📡 Listening on 0.0.0.0 for incoming RADIUS requests...")
    srv.BindToAddress("0.0.0.0")
    srv.Run()

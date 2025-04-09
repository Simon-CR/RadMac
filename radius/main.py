from pyrad.server import Server, RemoteHost
from pyrad.dictionary import Dictionary
from pyrad.packet import AccessAccept, AccessReject
from datetime import datetime, timezone
import mysql.connector
import os
import traceback

DEFAULT_VLAN_ID = os.getenv("DEFAULT_VLAN", "505")
DENIED_VLAN = os.getenv("DENIED_VLAN", "999")

class MacRadiusServer(Server):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            self.db = mysql.connector.connect(
                host=os.getenv('DB_HOST'),
                port=int(os.getenv('DB_PORT', 3306)),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                database=os.getenv('DB_NAME'),
            )
            self.db.ping()
            print("✅ Successfully connected to the database.")
        except Exception as e:
            print("❌ Failed to connect to the database.")
            traceback.print_exc()
            raise

    def HandleAuthPacket(self, pkt):
        print(f"\n📡 Received RADIUS Auth Request")
        try:
            username = pkt['User-Name'][0].upper()
            print(f"→ Parsed MAC: {username}")
            print(f"→ Attributes: {[f'{k}={v}' for k, v in pkt.items()]}")

            cursor = self.db.cursor(dictionary=True)
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
                    self.db.commit()
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
                    self.db.commit()
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
                self.db.commit()

            self.SendReplyPacket(pkt.fd, reply)
            print(f"📤 Response sent: {'Access-Accept' if reply.code == AccessAccept else 'Access-Reject'}\n")

        except Exception as e:
            print("❌ Error processing request:")
            traceback.print_exc()

        finally:
            if 'cursor' in locals():
                cursor.close()

if __name__ == '__main__':
    print("🚀 Starting MacRadiusServer...")
    srv = MacRadiusServer(dict=Dictionary("dictionary"))
    srv.hosts["0.0.0.0"] = RemoteHost("0.0.0.0", os.getenv("RADIUS_SECRET", "testing123").encode(), "localhost")
    print("📡 Listening on 0.0.0.0 for incoming RADIUS requests...")
    srv.BindToAddress("0.0.0.0")
    srv.Run()

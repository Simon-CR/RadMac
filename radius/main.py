from pyrad.server import Server, RemoteHost
from pyrad.dictionary import Dictionary
from pyrad.packet import AccessAccept, AccessReject
from datetime import datetime, timezone
import mysql.connector
import os

DEFAULT_VLAN_ID = os.getenv("DEFAULT_VLAN", "505")
DENIED_VLAN = os.getenv("DENIED_VLAN", "999")

class MacRadiusServer(Server):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.db = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 3306)),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
        )

    def HandleAuthPacket(self, pkt):
        username = pkt['User-Name'][0].upper()
        cursor = self.db.cursor(dictionary=True)
        now_utc = datetime.now(timezone.utc)
        
        # Step 1: Check if the MAC exists in the users table
        cursor.execute("SELECT vlan_id FROM users WHERE mac_address = %s", (username,))
        result = cursor.fetchone()

        reply = self.CreateReplyPacket(pkt)

        # Step 2: Handle the Access-Accept or Access-Reject scenario
        if result:
            vlan_id = result['vlan_id']
            denied_vlan = os.getenv("DENIED_VLAN", "999")

            if vlan_id == denied_vlan:
                reply.code = AccessReject
                cursor.execute("""
                    INSERT INTO auth_logs (mac_address, reply, result, timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (username, "Access-Reject", f"Denied due to VLAN {denied_vlan}", now_utc))
                self.db.commit()
                print(f"[INFO] MAC {username} rejected due to VLAN {denied_vlan}")

            else:
                reply.code = AccessAccept
                reply.AddAttribute("Tunnel-Type", 13)
                reply.AddAttribute("Tunnel-Medium-Type", 6)
                reply.AddAttribute("Tunnel-Private-Group-Id", vlan_id)

                cursor.execute("""
                    INSERT INTO auth_logs (mac_address, reply, result, timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (username, "Access-Accept", f"Assigned to VLAN {vlan_id}", now_utc))
                self.db.commit()
                print(f"[INFO] MAC {username} accepted and assigned to VLAN {vlan_id}")

        else:
            reply.code = AccessAccept
            reply["Tunnel-Type"] = 13
            reply["Tunnel-Medium-Type"] = 6
            reply["Tunnel-Private-Group-Id"] = DEFAULT_VLAN_ID

            cursor.execute("""
                INSERT INTO auth_logs (mac_address, reply, result, timestamp)
                VALUES (%s, %s, %s, %s)
            """, (username, "Access-Accept", f"Assigned to fallback VLAN {DEFAULT_VLAN_ID}", now_utc))
            self.db.commit()
            print(f"[INFO] MAC {username} not found — assigned to fallback VLAN {DEFAULT_VLAN_ID}")

        self.SendReplyPacket(pkt.fd, reply)
        cursor.close()


if __name__ == '__main__':
    srv = MacRadiusServer(dict=Dictionary("dictionary"))
    srv.hosts["0.0.0.0"] = RemoteHost("0.0.0.0", os.getenv("RADIUS_SECRET", "testing123").encode(), "localhost")
    srv.BindToAddress("0.0.0.0")
    srv.Run()

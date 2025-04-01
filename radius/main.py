from pyrad.server import Server, RemoteHost
from pyrad.dictionary import Dictionary
from pyrad.packet import AccessAccept, AccessReject
import mysql.connector
import os
DEFAULT_VLAN_ID = os.getenv("DEFAULT_VLAN", "999")

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
        cursor.execute("SELECT vlan_id FROM users WHERE mac_address = %s", (username,))
        result = cursor.fetchone()
        cursor.close()

        if result:
            reply = self.CreateReplyPacket(pkt)
            reply.code = AccessAccept
            
            reply.AddAttribute("Tunnel-Type", 13)
            reply.AddAttribute("Tunnel-Medium-Type", 6)
            reply.AddAttribute("Tunnel-Private-Group-Id", result['vlan_id'])
        else:
            # Fallback to default VLAN
            reply = self.CreateReplyPacket(pkt)
            reply.code = AccessAccept
            reply["Tunnel-Type"] = 13  # VLAN
            reply["Tunnel-Medium-Type"] = 6  # IEEE-802
            reply["Tunnel-Private-Group-Id"] = DEFAULT_VLAN_ID
            self.SendReplyPacket(pkt.fd, reply)
            print(f"[INFO] MAC {mac} not found — assigned to fallback VLAN {DEFAULT_VLAN_ID}")

        self.SendReplyPacket(pkt.fd, reply)

if __name__ == '__main__':
    srv = MacRadiusServer(dict=Dictionary("dictionary"))
    srv.hosts["0.0.0.0"] = RemoteHost("0.0.0.0", os.getenv("RADIUS_SECRET", "testing123").encode(), "localhost")
    srv.BindToAddress("0.0.0.0")
    srv.Run()

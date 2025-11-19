from pyrad.server import Server, RemoteHost, ServerPacketError
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
import socket
import ipaddress
import subprocess

DEFAULT_VLAN_ID = os.getenv("DEFAULT_VLAN", "505")
DENIED_VLAN = os.getenv("DENIED_VLAN", "999")

class MacRadiusServer(Server):
    def __init__(self, *args, **kwargs):
        self.allowed_networks = []  # (ipaddress.IPv4Network/IPv6Network, secret_bytes)
        self.dynamic_hosts = {}  # hostname -> secret_bytes
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
    
    def _AddSecret(self, pkt):
        """Override pyrad behaviour to support CIDR-based client allow lists and lazy resolution."""
        source_ip = pkt.source[0]

        # 1. Check existing exact matches
        if source_ip in self.hosts:
            pkt.secret = self.hosts[source_ip].secret
            return

        # 2. Check CIDR networks
        try:
            ip_obj = ipaddress.ip_address(source_ip)
        except ValueError:
            ip_obj = None

        if ip_obj:
            for network, secret in self.allowed_networks:
                if ip_obj in network:
                    pkt.secret = secret
                    logging.debug(f"RADIUS source {source_ip} matched network {network}")
                    return

        # 3. Check dynamic hosts (lazy resolution)
        found_dynamic = False
        for hostname, secret in self.dynamic_hosts.items():
            # Try resolving the hostname itself, and also 'tasks.<hostname>' for Swarm
            candidates = [hostname]
            if not hostname.startswith("tasks."):
                 candidates.append(f"tasks.{hostname}")

            for cand in candidates:
                try:
                    infos = socket.getaddrinfo(cand, None)
                    for info in infos:
                        resolved_ip = info[4][0]
                        # Cache it
                        if resolved_ip not in self.hosts:
                            self.hosts[resolved_ip] = RemoteHost(resolved_ip, secret, hostname)
                            print(f"✅ Lazily resolved {cand} to {resolved_ip}")
                        
                        if resolved_ip == source_ip:
                            pkt.secret = secret
                            found_dynamic = True
                except socket.gaierror:
                    pass
        
        if found_dynamic:
            return

        # 4. Wildcard
        if '0.0.0.0' in self.hosts:
            pkt.secret = self.hosts['0.0.0.0'].secret
            return

        print(f"⚠️ DROPPING PACKET from unknown host: {source_ip}")
        raise ServerPacketError(f'Received packet from unknown host: {source_ip}')

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
        print(f"\n📡 Received RADIUS Auth Request from {pkt.source[0]}")
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


def detect_local_networks():
    """Detect all local networks attached to this container using ip route."""
    networks = set()
    try:
        # Use ip route to find all networks we are directly connected to
        # Output format example: "10.0.3.0/24 dev eth0 proto kernel scope link src 10.0.3.5"
        cmd = ["ip", "-o", "route", "show", "scope", "link"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if parts:
                    # The first part is usually the CIDR (e.g., 10.0.3.0/24)
                    cidr = parts[0]
                    try:
                        net = ipaddress.ip_network(cidr, strict=False)
                        if not net.is_loopback and not net.is_link_local:
                            networks.add(net)
                    except ValueError:
                        pass
    except Exception as e:
        print(f"⚠️ Failed to detect local networks via ip command: {e}")

    # Fallback to socket method if ip command failed or returned nothing
    if not networks:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip:
                parts = local_ip.split('.')
                # Assume /16 as a safe fallback for Docker
                networks.add(ipaddress.ip_network(f"{parts[0]}.{parts[1]}.0.0/16", strict=False))
        except Exception:
            pass

    return list(networks)

def register_allowed_clients(server: MacRadiusServer):
    """Allow RADIUS requests from explicitly configured client IPs/hosts.

    RADIUS_ALLOWED_CLIENTS can be a comma-separated list of entries in the form
    "host" or "host:secret". When a secret is omitted the default RADIUS_SECRET
    value is used. If the variable is not set we fall back to a safe set that
    includes localhost and the container's hostname so radtest and Swarm peers
    can reach the server without switching to host networking.
    """

    env_value = os.getenv("RADIUS_ALLOWED_CLIENTS", "").strip()
    default_secret = os.getenv("RADIUS_SECRET", "testing123").encode()

    if env_value:
        entries = [item.strip() for item in env_value.split(",") if item.strip()]
    else:
        entries = []

    # Always ensure internal Docker services and localhost are allowed
    # This ensures the Web UI, Watchdog, and Healthchecks always work
    internal_hosts = [
        "127.0.0.1",
        "localhost",
        os.getenv("APP_HOST", "app"),
        os.getenv("NGINX_HOST", "nginx"),
        os.getenv("WATCHDOG_HOST", "watchdog"),
        os.getenv("RADIUS_HOST", "radius"),
        os.getenv("HOSTNAME", "radius"),
    ]
    
    # Add internal hosts to entries if they aren't explicitly configured
    # We check if the host string appears at the start of any entry (to handle host:secret format)
    for host in internal_hosts:
        if host and not any(e.startswith(host) for e in entries):
            entries.append(host)

    configured_hosts = []
    configured_networks = []

    for entry in entries:
        host_token, _sep, secret_override = entry.partition(":")
        host_token = host_token.strip()
        if not host_token:
            continue

        secret_bytes = (secret_override.encode() if secret_override else default_secret)

        # Wildcard matching uses 0.0.0.0 sentinel supported by pyrad
        if host_token in {"*", "any", "0.0.0.0"}:
            server.hosts['0.0.0.0'] = RemoteHost('0.0.0.0', secret_bytes, 'wildcard')
            configured_hosts.append('0.0.0.0 (wildcard)')
            continue

        # CIDR notation handled via custom network list
        if "/" in host_token:
            try:
                network = ipaddress.ip_network(host_token, strict=False)
                server.allowed_networks.append((network, secret_bytes))
                configured_networks.append(str(network))
            except ValueError:
                print(f"⚠️ Invalid CIDR entry ignored: {host_token}")
            continue

        # Direct IP address or hostname resolution
        resolved_ips = set()
        try:
            ipaddress.ip_address(host_token)
            resolved_ips.add(host_token)
        except ValueError:
            # It's a hostname (or invalid)
            # Add to dynamic hosts for lazy resolution
            server.dynamic_hosts[host_token] = secret_bytes
            
            try:
                infos = socket.getaddrinfo(host_token, None)
                resolved_ips.update({info[4][0] for info in infos})
            except socket.gaierror:
                print(f"⚠️ Unable to resolve host '{host_token}' at startup - will retry lazily")
                continue

        for ip in resolved_ips:
            server.hosts[ip] = RemoteHost(ip, secret_bytes, host_token)
            configured_hosts.append(f"{host_token}->{ip}")

    if configured_hosts:
        print(f"✅ Allowed RADIUS client hosts: {', '.join(configured_hosts)}")
    
    # Auto-detect and allow local subnet if not explicitly disabled
    if os.getenv("RADIUS_ALLOW_LOCAL_SUBNET", "true").lower() == "true":
        local_nets = detect_local_networks()
        for net in local_nets:
            server.allowed_networks.append((net, default_secret))
            configured_networks.append(f"{net} (auto-detected)")
        
        # Allow all RFC1918 private networks to ensure connectivity across
        # Docker Swarm Ingress (usually 10.x), Bridge (usually 172.x), and Host LANs (192.168.x)
        # regardless of specific subnet configuration.
        private_nets = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
        for net_str in private_nets:
            net = ipaddress.ip_network(net_str)
            # Check if already added by auto-detection to avoid duplicates in log
            if not any(existing_net == net for existing_net, _ in server.allowed_networks):
                server.allowed_networks.append((net, default_secret))
                configured_networks.append(f"{net} (rfc1918)")

    if configured_networks:
        print(f"✅ Allowed RADIUS client networks: {', '.join(configured_networks)}")
    if not configured_hosts and not configured_networks:
        print("⚠️ No RADIUS clients configured; set RADIUS_ALLOWED_CLIENTS")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    print("🚀 Starting MacRadiusServer...")
    dictionary_path = resolve_dictionary_path()
    srv = MacRadiusServer(dict=Dictionary(dictionary_path))
    register_allowed_clients(srv)
    print("📡 Listening on 0.0.0.0 for incoming RADIUS requests...")
    srv.BindToAddress("0.0.0.0")
    srv.Run()

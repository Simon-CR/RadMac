#!/usr/bin/env python3
"""
Quick test to verify Docker socket restart functionality
Tests the same logic the watchdog uses for container restart
"""

import docker
import time
import sys

def test_docker_restart():
    print("🧪 Testing Docker Socket Restart Functionality")
    print("=" * 50)
    
    try:
        # Initialize Docker client
        client = docker.from_env()
        print("✅ Docker client initialized")
        
        # Create a simple test container
        print("📦 Creating test container...")
        container = client.containers.run(
            "python:3.9-slim",
            command="python -c 'import time; import http.server; import socketserver; handler = http.server.SimpleHTTPRequestHandler; httpd = socketserver.TCPServer((\"\", 8080), handler); print(\"Server running on port 8080\"); httpd.serve_forever()'",
            name="test-restart-container",
            ports={'8080/tcp': 8083},
            detach=True,
            remove=False
        )
        
        print(f"✅ Created container: {container.name} (ID: {container.short_id})")
        time.sleep(3)
        
        # Check container status
        container.reload()
        print(f"📊 Container status: {container.status}")
        
        # Test finding container by name (like watchdog does)
        print("\n🔍 Testing container lookup by name...")
        found_containers = client.containers.list(filters={"name": "test-restart-container"})
        if found_containers:
            print(f"✅ Found container by name: {found_containers[0].name}")
        else:
            print("❌ Could not find container by name")
            
        # Test restart functionality
        print("\n🔄 Testing container restart...")
        try:
            container.restart()
            print("✅ Container restart command successful")
            time.sleep(2)
            
            # Check status after restart
            container.reload()
            print(f"📊 Container status after restart: {container.status}")
            
        except Exception as e:
            print(f"❌ Container restart failed: {e}")
        
        # Test stopping and restarting (like when container is down)
        print("\n🛑 Testing stop and restart scenario...")
        try:
            container.stop()
            print("✅ Container stopped")
            time.sleep(1)
            
            container.reload()
            print(f"📊 Container status after stop: {container.status}")
            
            # Try to restart stopped container
            container.restart()
            print("✅ Container restarted from stopped state")
            time.sleep(2)
            
            container.reload()
            print(f"📊 Container status after restart from stopped: {container.status}")
            
        except Exception as e:
            print(f"❌ Stop/restart failed: {e}")
        
        # Test the "No containers found" scenario
        print("\n🗑️ Testing container removal scenario...")
        try:
            container.remove(force=True)
            print("✅ Container removed")
            
            # Try to find the removed container
            found_containers = client.containers.list(filters={"name": "test-restart-container"})
            if not found_containers:
                print("✅ Confirmed: No containers found matching name (expected)")
            else:
                print("❌ Unexpected: Container still found after removal")
                
        except Exception as e:
            print(f"❌ Container removal failed: {e}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    print("\n✅ Docker restart test completed!")
    return True

def test_swarm_vs_compose():
    """Test container name differences between Swarm and Compose"""
    print("\n🔍 Checking current Docker setup...")
    
    try:
        client = docker.from_env()
        
        # List all containers
        containers = client.containers.list(all=True)
        print(f"📊 Found {len(containers)} containers:")
        
        for container in containers[:10]:  # Show first 10
            print(f"  - Name: {container.name}")
            if container.labels:
                swarm_service = container.labels.get('com.docker.swarm.service.name')
                if swarm_service:
                    print(f"    Swarm Service: {swarm_service}")
                    
        # Check if we're in swarm mode
        try:
            swarm_info = client.swarm.attrs
            print("🐝 Docker Swarm mode detected")
            print(f"   Swarm ID: {swarm_info.get('ID', 'Unknown')[:12]}...")
        except:
            print("🐳 Standard Docker mode (no Swarm)")
            
    except Exception as e:
        print(f"❌ Setup check failed: {e}")

if __name__ == "__main__":
    test_swarm_vs_compose()
    test_docker_restart()

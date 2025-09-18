#!/bin/bash
# Database Connection Stress Test
# Simulates the NFS hiccup scenario by creating connection chaos

echo "🧪 Starting RadMac Database Connection Stress Test"
echo "This simulates NFS hiccups by creating connection issues..."

# Get database container name (try different naming patterns)
DB_CONTAINER=$(docker ps --format "table {{.Names}}" | grep -E "(database|db)" | head -n1)

if [ -z "$DB_CONTAINER" ]; then
    echo "❌ Could not find database container. Please ensure RadMac is running."
    exit 1
fi

echo "📍 Found database container: $DB_CONTAINER"

# Function to create connection chaos
create_connection_chaos() {
    echo "🔥 Creating connection chaos (simulating NFS hiccup)..."
    
    # Method 1: Create many rapid connections that will be aborted
    for i in {1..50}; do
        # Create connections that timeout/abort (simulates NFS issues)
        timeout 1 docker exec $DB_CONTAINER mariadb -h localhost -u root -p${MARIADB_ROOT_PASSWORD:-radmac} -e "SELECT SLEEP(10);" &
    done
    
    echo "⏱️  Waiting 5 seconds for connections to build up..."
    sleep 5
    
    # Kill the hanging connections (simulates network disconnect)
    echo "💥 Killing connections (simulating network disconnect)..."
    pkill -f "mariadb -h localhost"
    
    echo "📊 Current connection status:"
    docker exec $DB_CONTAINER mariadb -h localhost -u root -p${MARIADB_ROOT_PASSWORD:-radmac} -e "SHOW STATUS LIKE 'Aborted_connects'; SHOW STATUS LIKE 'Threads_connected';" 2>/dev/null || echo "Database may be stressed..."
}

# Function to check health endpoint
check_health() {
    echo "🔍 Checking database health endpoint..."
    
    # Try to get health status
    if command -v curl >/dev/null 2>&1; then
        HEALTH=$(curl -s http://localhost:8082/health 2>/dev/null || echo "Health check failed")
        echo "Health response: $HEALTH"
    else
        echo "Install curl to see health endpoint response"
    fi
}

# Function to monitor watchdog logs
monitor_watchdog() {
    echo "👀 Monitoring watchdog logs for recovery actions..."
    echo "   (Press Ctrl+C to stop monitoring)"
    
    # Find watchdog container
    WATCHDOG_CONTAINER=$(docker ps --format "table {{.Names}}" | grep -i watchdog | head -n1)
    
    if [ -n "$WATCHDOG_CONTAINER" ]; then
        echo "📍 Found watchdog container: $WATCHDOG_CONTAINER"
        echo "📝 Watchdog logs (last 10 lines + follow):"
        docker logs --tail 10 -f $WATCHDOG_CONTAINER
    else
        echo "❌ Watchdog container not found"
    fi
}

# Main test sequence
echo ""
echo "🎯 Test Plan:"
echo "1. Check initial health status"
echo "2. Create connection chaos (simulate NFS hiccup)"
echo "3. Monitor for degraded status and recovery"
echo ""

# Step 1: Initial health check
echo "=== Step 1: Initial Health Check ==="
check_health
echo ""

# Step 2: Create connection issues
echo "=== Step 2: Simulating NFS Hiccup ==="
create_connection_chaos
echo ""

# Step 3: Check health after chaos
echo "=== Step 3: Health Check After Chaos ==="
sleep 2
check_health
echo ""

# Step 4: Monitor recovery
echo "=== Step 4: Monitor Watchdog Recovery ==="
echo "The watchdog should detect 'degraded' status and trigger recovery..."
echo "Expected sequence:"
echo "  1. Health endpoint detects high aborted connections"
echo "  2. Returns 'degraded' status with warnings"
echo "  3. Watchdog triggers recovery action"
echo "  4. Database recovery script cleans up connections"
echo "  5. Status returns to 'healthy'"
echo ""

# Option to monitor logs
read -p "🔍 Monitor watchdog logs in real-time? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    monitor_watchdog
else
    echo "✅ Test complete! Check your watchdog logs manually for recovery actions."
    echo ""
    echo "🔍 To monitor manually:"
    echo "   docker logs -f \$(docker ps --format '{{.Names}}' | grep watchdog)"
    echo ""
    echo "🔍 To check database recovery:"
    echo "   curl http://localhost:8082/health"
fi
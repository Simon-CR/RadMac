#!/bin/bash

# Test Script for Watchdog Restart Functionality
# Tests restart behavior in local Docker Compose environment

echo "🧪 Testing Watchdog Restart Functionality"
echo "========================================"

# Change to test directory
cd "$(dirname "$0")"

echo "📋 Starting test environment..."
docker-compose -f docker-compose.test.yml up -d

echo "⏳ Waiting 30 seconds for services to initialize..."
sleep 30

echo "🔍 Checking initial service health..."
curl -s http://localhost:8081/health | jq . || echo "test-app not ready"
curl -s http://localhost:8082/health | jq . || echo "test-db not ready"

echo ""
echo "📊 Checking watchdog logs..."
docker logs test-watchdog --tail 10

echo ""
echo "🛑 Now stopping test-app container to trigger restart..."
docker stop test-app

echo "⏳ Waiting 45 seconds to observe restart behavior..."
sleep 45

echo ""
echo "📊 Watchdog logs after stopping test-app:"
docker logs test-watchdog --tail 20

echo ""
echo "🔍 Checking if test-app was restarted:"
docker ps --filter name=test-app

echo ""
echo "🔧 Testing app health after restart attempt:"
curl -s http://localhost:8081/health | jq . || echo "test-app still down"

echo ""
echo "🧹 Cleaning up test environment..."
docker-compose -f docker-compose.test.yml down -v

echo "✅ Test complete!"

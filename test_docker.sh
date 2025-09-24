#!/bin/bash

echo "🐳 Testing Docker Backend Environment"
echo "======================================="

# Build and start the Docker environment
echo "Building Docker image..."
docker-compose build

echo "Starting Docker containers..."
docker-compose up -d

# Wait for the containers to start
echo "Waiting for containers to start..."
sleep 5

# Test if the API is accessible
echo "Testing API endpoint..."
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8090/api/health)

if [ "$response" = "200" ]; then
    echo "✅ API is responding correctly"
else
    echo "❌ API is not responding (HTTP $response)"
    echo "Container logs:"
    docker-compose logs
    exit 1
fi

# Test file serving
echo "Testing static file serving..."
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8090/public/data/index.json)

if [ "$response" = "200" ]; then
    echo "✅ Static files are being served correctly"
else
    echo "❌ Static files are not accessible (HTTP $response)"
fi

echo ""
echo "🎉 Docker environment is ready!"
echo "📡 API URL: http://localhost:8090/api"
echo "📁 Static files: http://localhost:8090/public/data/"
echo ""
echo "To test the upload functionality:"
echo "cd /path/to/weird-bench && python run_benchmarks.py --upload-existing --api-url http://localhost:8090/api"
echo ""
echo "To stop the environment:"
echo "docker-compose down"
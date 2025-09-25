#!/bin/bash
set -e

echo "🚀 Deploying Weird Bench Site to Production"

# Stop any existing containers
echo "📦 Stopping existing containers..."
docker compose -f docker-compose.prod.yml down 2>/dev/null || true

# Pull nginx image explicitly to handle auth issues
echo "🐳 Pulling nginx image..."
docker pull registry.hub.docker.com/library/nginx:stable-alpine || \
docker pull nginx:stable-alpine || \
docker pull nginx:alpine

# Build the application
echo "🏗️  Building application..."
docker compose -f docker-compose.prod.yml build --no-cache

# Start the containers
echo "🚀 Starting containers..."
docker compose -f docker-compose.prod.yml up -d

# Wait for health check
echo "⏳ Waiting for health check..."
sleep 10

# Test the deployment
echo "🧪 Testing deployment..."
if curl -f -s http://localhost:8090/api/health > /dev/null; then
    echo "✅ Deployment successful!"
    echo "📊 API is running on http://localhost:8090/api"
    echo "🌐 Frontend is running on http://localhost:8090"
else
    echo "❌ Health check failed, checking logs..."
    docker compose -f docker-compose.prod.yml logs --tail=20
    exit 1
fi

echo "🎉 Production deployment complete!"
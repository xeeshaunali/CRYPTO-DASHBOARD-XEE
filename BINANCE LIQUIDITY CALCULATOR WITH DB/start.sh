#!/bin/bash

echo "=========================================="
echo "Binance Futures Trading Journal"
echo "Quick Start Script"
echo "=========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed!"
    echo "Please install Docker Compose first: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker and Docker Compose are installed"
echo ""

# Start the application
echo "🚀 Starting Binance Trading Journal..."
echo ""
docker-compose up -d

echo ""
echo "⏳ Waiting for services to start (30 seconds)..."
sleep 30

echo ""
echo "=========================================="
echo "✅ Application is ready!"
echo "=========================================="
echo ""
echo "📊 Trading Journal: http://localhost:5000"
echo "🗄️  phpMyAdmin:      http://localhost:8080"
echo "    - Username: root"
echo "    - Password: root"
echo ""
echo "=========================================="
echo ""
echo "Useful commands:"
echo "  - Stop:    docker-compose down"
echo "  - Restart: docker-compose restart"
echo "  - Logs:    docker-compose logs -f"
echo "=========================================="

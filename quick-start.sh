#!/bin/bash

# Quick Start Guide for House Price Predictor
# This script sets up and runs the entire application locally

set -e

echo "🏠 House Price Predictor - Quick Start"
echo "========================================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

echo "✅ Docker is installed"
echo ""

# Navigate to project directory
cd "$(dirname "$0")"

echo "📦 Building Docker images..."
echo "This may take a few minutes on first run..."
docker compose build

echo ""
echo "🚀 Starting services..."
docker compose up -d

echo ""
echo "⏳ Waiting for services to start..."
sleep 5

# Check if services are running
echo ""
echo "✅ Services are starting..."
echo ""
echo "📝 Application URLs:"
echo "   Frontend:  🎨 http://localhost:3000"
echo "   API Docs:  📚 http://localhost:8000/docs"
echo "   API:       ⚙️  http://localhost:8000"
echo ""

# Try to access the frontend
if curl -s http://localhost:3000 > /dev/null; then
    echo "✅ Frontend is running!"
else
    echo "⏳ Frontend is still starting, please wait a moment..."
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📖 Next steps:"
echo "1. Open http://localhost:3000 in your browser"
echo "2. Enter property details in the form"
echo "3. Click 'Predict Price' to get an estimate"
echo ""
echo "📊 View logs with:"
echo "   docker compose logs -f backend    # Backend logs"
echo "   docker compose logs -f frontend   # Frontend logs"
echo ""
echo "🛑 Stop services with:"
echo "   docker compose down"
echo ""
echo "📚 For more information, see:"
echo "   - README.md for overview"
echo "   - AWS_DEPLOYMENT_GUIDE.md for cloud deployment"
echo ""

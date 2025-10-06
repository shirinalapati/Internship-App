#!/bin/bash

echo "🚀 Setting up Redis for Internship Matcher..."
echo ""

# Check if Redis is installed
if command -v redis-cli &> /dev/null; then
    echo "✅ Redis CLI found"
    
    # Check if Redis is running
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis is already running"
    else
        echo "⚠️  Redis is installed but not running"
        echo "Starting Redis..."
        
        # Try to start Redis
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            brew services start redis
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            sudo systemctl start redis
        fi
        
        sleep 2
        
        if redis-cli ping &> /dev/null; then
            echo "✅ Redis started successfully"
        else
            echo "❌ Failed to start Redis"
            exit 1
        fi
    fi
else
    echo "❌ Redis not found. Installing..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install redis
            brew services start redis
        else
            echo "❌ Homebrew not found. Install from https://brew.sh"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        sudo apt-get update
        sudo apt-get install -y redis-server
        sudo systemctl start redis
    else
        echo "❌ Unsupported OS. Please install Redis manually"
        echo "Visit: https://redis.io/download"
        exit 1
    fi
fi

echo ""
echo "📦 Installing Python Redis package..."
pip install redis==5.0.1

echo ""
echo "✅ Setup complete!"
echo ""
echo "To verify Redis is working:"
echo "  redis-cli ping"
echo ""
echo "To check cache status:"
echo "  curl http://localhost:8000/api/cache-status"
echo ""
echo "To manually refresh cache:"
echo "  curl -X POST http://localhost:8000/api/refresh-cache"


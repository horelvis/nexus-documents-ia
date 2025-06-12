#!/bin/bash

# Setup verification script for Nexus Document Backend
# Checks all prerequisites before starting services

set -e

echo "🔍 Checking Nexus Document Backend setup..."
echo ""

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ] || [ ! -f "docker-compose.dev.yml" ]; then
    echo "❌ Error: Please run this script from the backend/docker directory"
    exit 1
fi

# Check .env file
echo "📄 Checking .env file..."
if [ -f "../.env" ]; then
    echo "✅ .env file found in backend root"
    
    # Check for required variables
    source ../.env 2>/dev/null || true
    
    if [ -z "$POSTGRES_USER" ]; then
        echo "⚠️  Warning: POSTGRES_USER not set in .env"
    else
        echo "✅ Database configuration found"
    fi
    
    if [ -z "$SECRET_KEY" ]; then
        echo "⚠️  Warning: SECRET_KEY not set in .env"
    else
        echo "✅ Security configuration found"
    fi
    
else
    echo "❌ .env file not found in backend root"
    echo "   Create it with: cp ../.env.example ../.env"
    echo "   Then edit the file with your settings"
    exit 1
fi

# Check credentials
echo ""
echo "🔑 Checking credentials..."
if [ -f "../credentials/nexus-document-ia-04252dae0146.json" ]; then
    echo "✅ GCS credentials found"
else
    echo "⚠️  Warning: GCS credentials not found"
    echo "   Place them at: ../credentials/nexus-document-ia-04252dae0146.json"
fi

# Check Docker
echo ""
echo "🐳 Checking Docker..."
if command -v docker >/dev/null 2>&1; then
    echo "✅ Docker installed"
    
    if docker info >/dev/null 2>&1; then
        echo "✅ Docker daemon running"
    else
        echo "❌ Docker daemon not running"
        echo "   Start Docker Desktop or run: sudo systemctl start docker"
        exit 1
    fi
else
    echo "❌ Docker not installed"
    echo "   Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check Docker Compose
if docker compose version >/dev/null 2>&1; then
    echo "✅ Docker Compose available"
else
    echo "❌ Docker Compose not available"
    echo "   Update Docker to get the latest compose plugin"
    exit 1
fi

# Check ports
echo ""
echo "🔌 Checking ports..."
PORTS=(8000 8001 8002 8003 8004 11434 5432 6379 6333)
USED_PORTS=()

for port in "${PORTS[@]}"; do
    if lsof -i :$port >/dev/null 2>&1; then
        USED_PORTS+=($port)
    fi
done

if [ ${#USED_PORTS[@]} -eq 0 ]; then
    echo "✅ All required ports are available"
else
    echo "⚠️  Warning: Some ports are in use: ${USED_PORTS[*]}"
    echo "   You may need to stop other services or change port mappings"
fi

# Check available disk space
echo ""
echo "💾 Checking disk space..."
AVAILABLE=$(df . | awk 'NR==2 {print $4}')
if [ $AVAILABLE -gt 5000000 ]; then  # 5GB in KB
    echo "✅ Sufficient disk space available"
else
    echo "⚠️  Warning: Low disk space. Docker images require ~5GB+"
fi

# Final summary
echo ""
echo "📋 Setup Summary:"
echo "   • .env file: $([ -f "../.env" ] && echo "✅ Found" || echo "❌ Missing")"
echo "   • GCS credentials: $([ -f "../credentials/nexus-document-ia-04252dae0146.json" ] && echo "✅ Found" || echo "⚠️  Missing")"
echo "   • Docker: $(command -v docker >/dev/null 2>&1 && echo "✅ Ready" || echo "❌ Missing")"
echo "   • Ports: $([ ${#USED_PORTS[@]} -eq 0 ] && echo "✅ Available" || echo "⚠️  Some in use")"
echo ""

if [ -f "../.env" ] && command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "🎉 Setup looks good! You can start the services with:"
    echo "   • Development: ./start-dev.sh"
    echo "   • Production:  ./start-prod.sh"
else
    echo "🔧 Please fix the issues above before starting services"
fi
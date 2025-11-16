#!/bin/bash

# Deployment Script for Internship Matcher
# This script automates the deployment process on EC2

set -e  # Exit on error

echo "🚀 Starting deployment of Internship Matcher..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# =====================================
# 1. Pre-deployment Checks
# =====================================
echo -e "${YELLOW}📋 Step 1: Running pre-deployment checks...${NC}"

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found!${NC}"
    echo "Please copy .env.production to .env and fill in your values:"
    echo "  cp .env.production .env"
    echo "  nano .env  # Edit with your actual values"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed!${NC}"
    echo "Run setup-ec2.sh first to install Docker"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Error: Docker Compose is not installed!${NC}"
    echo "Run setup-ec2.sh first to install Docker Compose"
    exit 1
fi

echo -e "${GREEN}✅ Pre-deployment checks passed${NC}"

# =====================================
# 2. Update CORS Settings
# =====================================
echo -e "${YELLOW}📋 Step 2: Checking CORS configuration...${NC}"

# Get EC2 public IP
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost")

echo "Public IP detected: $PUBLIC_IP"
echo -e "${YELLOW}⚠️  IMPORTANT: Update app.py CORS settings to include your domain${NC}"
echo "Current CORS origins should include: https://your-domain.com or http://$PUBLIC_IP"

read -p "Have you updated CORS settings in app.py? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Please update app.py CORS settings before deploying${NC}"
    echo "Add your domain to allow_origins list in app.py"
    exit 1
fi

# =====================================
# 3. Build Frontend
# =====================================
echo -e "${YELLOW}📋 Step 3: Building React frontend...${NC}"

cd frontend

# Check if frontend .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  Frontend .env not found, creating from template...${NC}"
    echo "REACT_APP_API_URL=https://your-domain.com" > .env
    echo "REACT_APP_STACK_AUTH_PROJECT_ID=your-project-id" >> .env
    echo "REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY=your-key" >> .env
    echo -e "${RED}Please edit frontend/.env with your actual values!${NC}"
    exit 1
fi

echo "Installing frontend dependencies..."
npm ci --silent

echo "Building frontend for production..."
npm run build

echo -e "${GREEN}✅ Frontend built successfully${NC}"

cd ..

# =====================================
# 4. Stop Existing Containers
# =====================================
echo -e "${YELLOW}📋 Step 4: Stopping existing containers...${NC}"

if docker-compose ps &> /dev/null; then
    docker-compose down
elif docker compose ps &> /dev/null; then
    docker compose down
fi

echo -e "${GREEN}✅ Existing containers stopped${NC}"

# =====================================
# 5. Build Docker Images
# =====================================
echo -e "${YELLOW}📋 Step 5: Building Docker images...${NC}"

if command -v docker-compose &> /dev/null; then
    docker-compose build --no-cache
else
    docker compose build --no-cache
fi

echo -e "${GREEN}✅ Docker images built${NC}"

# =====================================
# 6. Initialize Database
# =====================================
echo -e "${YELLOW}📋 Step 6: Checking database...${NC}"

if [ ! -f jobs.db ]; then
    echo "Creating new database..."
    touch jobs.db
    chmod 666 jobs.db
fi

echo -e "${GREEN}✅ Database ready${NC}"

# =====================================
# 7. Create SSL Directory
# =====================================
echo -e "${YELLOW}📋 Step 7: Preparing SSL directory...${NC}"

mkdir -p ssl
echo "SSL directory created (run setup-ssl.sh to obtain certificates)"

echo -e "${GREEN}✅ SSL directory ready${NC}"

# =====================================
# 8. Start Services
# =====================================
echo -e "${YELLOW}📋 Step 8: Starting services...${NC}"

if command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi

echo -e "${GREEN}✅ Services started${NC}"

# =====================================
# 9. Wait for Services to be Healthy
# =====================================
echo -e "${YELLOW}📋 Step 9: Waiting for services to be healthy...${NC}"

sleep 10

# Check Redis
echo "Checking Redis..."
if docker exec internship-redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis is healthy${NC}"
else
    echo -e "${RED}❌ Redis health check failed${NC}"
fi

# Check Backend
echo "Checking Backend..."
for i in {1..10}; do
    if curl -f http://localhost:8000/api/cache-status > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is healthy${NC}"
        break
    else
        echo "Waiting for backend... ($i/10)"
        sleep 5
    fi
done

# Check Nginx
echo "Checking Nginx..."
if curl -f http://localhost/health > /dev/null 2>&1 || curl -f http://localhost > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Nginx is healthy${NC}"
else
    echo -e "${YELLOW}⚠️  Nginx check failed (may need SSL setup)${NC}"
fi

# =====================================
# 10. Display Status
# =====================================
echo ""
echo "========================================"
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo "========================================"
echo ""

if command -v docker-compose &> /dev/null; then
    docker-compose ps
else
    docker compose ps
fi

echo ""
echo "📊 Service URLs:"
echo "  Frontend: http://$PUBLIC_IP"
echo "  Backend API: http://$PUBLIC_IP/api/cache-status"
echo ""
echo "📝 Next Steps:"
echo "  1. Set up SSL certificates:"
echo "     ./setup-ssl.sh your-domain.com"
echo ""
echo "  2. Point your domain DNS to this IP: $PUBLIC_IP"
echo ""
echo "  3. Update frontend/.env with your production domain"
echo ""
echo "  4. Trigger cache refresh:"
echo "     curl -X POST http://localhost:8000/api/refresh-cache"
echo ""
echo "📋 Useful Commands:"
echo "  View logs: docker-compose logs -f"
echo "  Restart: docker-compose restart"
echo "  Stop: docker-compose down"
echo "  Rebuild: ./deploy.sh"
echo ""
echo -e "${GREEN}✅ Deployment successful!${NC}"

#!/bin/bash

# EC2 Instance Setup Script for Internship Matcher
# Run this ONCE after launching a fresh EC2 instance

set -e  # Exit on error

echo "🚀 Setting up EC2 instance for Internship Matcher..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# =====================================
# 1. System Update
# =====================================
echo -e "${YELLOW}📋 Step 1: Updating system packages...${NC}"

sudo apt-get update
sudo apt-get upgrade -y

echo -e "${GREEN}✅ System updated${NC}"

# =====================================
# 2. Install Docker
# =====================================
echo -e "${YELLOW}📋 Step 2: Installing Docker...${NC}"

# Remove old versions
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Install prerequisites
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER

echo -e "${GREEN}✅ Docker installed${NC}"

# =====================================
# 3. Install Docker Compose (standalone)
# =====================================
echo -e "${YELLOW}📋 Step 3: Installing Docker Compose standalone...${NC}"

# Get latest version
DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)

# Download and install
sudo curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker-compose --version

echo -e "${GREEN}✅ Docker Compose installed${NC}"

# =====================================
# 4. Install Git
# =====================================
echo -e "${YELLOW}📋 Step 4: Installing Git...${NC}"

sudo apt-get install -y git

echo -e "${GREEN}✅ Git installed${NC}"

# =====================================
# 5. Install Node.js and npm
# =====================================
echo -e "${YELLOW}📋 Step 5: Installing Node.js and npm...${NC}"

# Install Node.js 18 LTS
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
node --version
npm --version

echo -e "${GREEN}✅ Node.js and npm installed${NC}"

# =====================================
# 6. Install Python 3.11
# =====================================
echo -e "${YELLOW}📋 Step 6: Checking Python installation...${NC}"

# Check if Python 3.11 is available
if ! command -v python3.11 &> /dev/null; then
    echo "Python 3.11 not found, installing..."
    sudo apt-get install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
fi

# Set python3.11 as default python3
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install pip
sudo apt-get install -y python3-pip

python3 --version
pip3 --version

echo -e "${GREEN}✅ Python 3.11 installed${NC}"

# =====================================
# 7. Install System Dependencies
# =====================================
echo -e "${YELLOW}📋 Step 7: Installing system dependencies...${NC}"

sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    build-essential \
    libssl-dev \
    libffi-dev \
    certbot \
    python3-certbot-nginx \
    htop \
    vim \
    nano \
    unzip

echo -e "${GREEN}✅ System dependencies installed${NC}"

# =====================================
# 8. Configure Firewall (UFW)
# =====================================
echo -e "${YELLOW}📋 Step 8: Configuring firewall...${NC}"

# Install UFW if not present
sudo apt-get install -y ufw

# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall (only if not already enabled)
echo "y" | sudo ufw enable || true

sudo ufw status

echo -e "${GREEN}✅ Firewall configured${NC}"

# =====================================
# 9. Create App Directory
# =====================================
echo -e "${YELLOW}📋 Step 9: Creating application directory...${NC}"

mkdir -p ~/internship-app
cd ~/internship-app

echo -e "${GREEN}✅ Application directory created${NC}"

# =====================================
# 10. Setup Swap (if needed for t2.micro)
# =====================================
echo -e "${YELLOW}📋 Step 10: Checking swap space...${NC}"

# Check if swap exists
if free | grep -q "Swap:.*0.*0.*0"; then
    echo "No swap found, creating 2GB swap..."

    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile

    # Make swap permanent
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

    echo -e "${GREEN}✅ Swap created (2GB)${NC}"
else
    echo -e "${GREEN}✅ Swap already configured${NC}"
fi

# =====================================
# 11. Configure Docker to Start on Boot
# =====================================
echo -e "${YELLOW}📋 Step 11: Configuring Docker to start on boot...${NC}"

sudo systemctl enable docker
sudo systemctl start docker

echo -e "${GREEN}✅ Docker configured to start on boot${NC}"

# =====================================
# 12. Create Useful Aliases
# =====================================
echo -e "${YELLOW}📋 Step 12: Creating useful aliases...${NC}"

cat >> ~/.bashrc << 'EOF'

# Internship App Aliases
alias app-logs='docker-compose logs -f'
alias app-restart='docker-compose restart'
alias app-stop='docker-compose down'
alias app-start='docker-compose up -d'
alias app-status='docker-compose ps'
alias app-deploy='cd ~/internship-app && ./deploy.sh'

EOF

echo -e "${GREEN}✅ Aliases added to ~/.bashrc${NC}"

# =====================================
# Summary
# =====================================
echo ""
echo "========================================"
echo -e "${GREEN}🎉 EC2 Setup Complete!${NC}"
echo "========================================"
echo ""
echo "📊 Installed Software:"
echo "  ✅ Docker $(docker --version | cut -d' ' -f3)"
echo "  ✅ Docker Compose $(docker-compose --version | cut -d' ' -f4)"
echo "  ✅ Git $(git --version | cut -d' ' -f3)"
echo "  ✅ Node.js $(node --version)"
echo "  ✅ Python $(python3 --version | cut -d' ' -f2)"
echo "  ✅ UFW Firewall (enabled)"
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. IMPORTANT: Log out and log back in for Docker group to take effect:"
echo "   ${YELLOW}exit${NC}"
echo "   Then SSH back into the instance"
echo ""
echo "2. Clone your repository:"
echo "   ${YELLOW}cd ~/internship-app${NC}"
echo "   ${YELLOW}git clone https://github.com/your-username/your-repo.git .${NC}"
echo ""
echo "3. Configure environment variables:"
echo "   ${YELLOW}cp .env.production .env${NC}"
echo "   ${YELLOW}nano .env${NC}  # Fill in your API keys and secrets"
echo ""
echo "4. Update frontend environment:"
echo "   ${YELLOW}cd frontend${NC}"
echo "   ${YELLOW}cp .env.example .env${NC}"
echo "   ${YELLOW}nano .env${NC}  # Update with your domain"
echo "   ${YELLOW}cd ..${NC}"
echo ""
echo "5. Deploy the application:"
echo "   ${YELLOW}./deploy.sh${NC}"
echo ""
echo "6. Set up SSL (after DNS is configured):"
echo "   ${YELLOW}./setup-ssl.sh your-domain.com${NC}"
echo ""
echo "🔧 Useful Commands:"
echo "  app-logs      - View application logs"
echo "  app-restart   - Restart services"
echo "  app-stop      - Stop all services"
echo "  app-start     - Start all services"
echo "  app-status    - Check service status"
echo "  app-deploy    - Redeploy application"
echo ""
echo -e "${GREEN}✅ Setup complete! Remember to log out and log back in.${NC}"

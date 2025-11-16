# AWS EC2 Deployment Guide - Internship Matcher

Complete step-by-step guide to deploy the Internship Matcher application on AWS EC2 Free Tier.

## 📋 Table of Contents
1. [Prerequisites](#prerequisites)
2. [AWS Setup](#aws-setup)
3. [EC2 Instance Setup](#ec2-instance-setup)
4. [Application Deployment](#application-deployment)
5. [Domain & SSL Setup](#domain--ssl-setup)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance](#maintenance)

---

## Prerequisites

### Required
- AWS Account (Free Tier eligible)
- GitHub account (for code repository)
- Domain name (optional, for HTTPS)
- API Keys:
  - OpenAI API key
  - AWS S3 credentials
  - Stack Auth credentials

### Estimated Costs
- **Months 1-12**: FREE (AWS Free Tier)
- **After 12 months**: ~$11.50/month
  - EC2 t2.micro: $8.50/month
  - EBS storage: $2/month
  - Data transfer: ~$1/month

---

## AWS Setup

### Step 1: Launch EC2 Instance

1. **Log into AWS Console**
   - Go to https://console.aws.amazon.com
   - Navigate to EC2 Dashboard

2. **Launch Instance**
   - Click "Launch Instance"
   - **Name**: `internship-matcher-prod`
   - **AMI**: Ubuntu Server 22.04 LTS (Free Tier eligible)
   - **Instance Type**: t2.micro (Free Tier eligible)
   - **Key Pair**: Create new key pair
     - Name: `internship-matcher-key`
     - Type: RSA
     - Format: .pem
     - Download and save securely!

3. **Network Settings**
   - Create security group: `internship-matcher-sg`
   - Configure rules:
     - **SSH**: Port 22, Source: My IP (your IP)
     - **HTTP**: Port 80, Source: Anywhere (0.0.0.0/0)
     - **HTTPS**: Port 443, Source: Anywhere (0.0.0.0/0)

4. **Storage**
   - Root volume: 20 GB gp3 (Free Tier: up to 30 GB)

5. **Launch Instance**
   - Review and launch
   - Note down the Public IPv4 address

### Step 2: Connect to EC2 Instance

```bash
# Make key file secure
chmod 400 internship-matcher-key.pem

# Connect to instance
ssh -i internship-matcher-key.pem ubuntu@<YOUR-EC2-PUBLIC-IP>
```

---

## EC2 Instance Setup

### Step 1: Run Setup Script

```bash
# Download setup script
curl -O https://raw.githubusercontent.com/YOUR-USERNAME/YOUR-REPO/main/setup-ec2.sh

# Make executable
chmod +x setup-ec2.sh

# Run setup (installs Docker, Node.js, Python, etc.)
./setup-ec2.sh
```

This script will install:
- Docker & Docker Compose
- Node.js 18 LTS
- Python 3.11
- Git
- System dependencies (Tesseract, etc.)
- Firewall configuration

**IMPORTANT**: After script completes, log out and log back in:
```bash
exit
ssh -i internship-matcher-key.pem ubuntu@<YOUR-EC2-PUBLIC-IP>
```

### Step 2: Clone Your Repository

```bash
cd ~/internship-app
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git .
```

---

## Application Deployment

### Step 1: Configure Environment Variables

#### Backend Environment (.env)

```bash
# Copy template
cp .env.production .env

# Edit with your values
nano .env
```

**Required variables:**
```env
# OpenAI (REQUIRED)
OPENAI_API_KEY=sk-proj-your-actual-key-here

# AWS S3 (REQUIRED)
AWS_ACCESS_KEY_ID=your-actual-access-key
AWS_SECRET_ACCESS_KEY=your-actual-secret-key
AWS_BUCKET_NAME=internship-matcher-developer
AWS_REGION=us-east-2

# Stack Auth (REQUIRED)
STACK_AUTH_PROJECT_ID=your-actual-project-id
STACK_AUTH_PUBLISHABLE_CLIENT_KEY=your-actual-key
STACK_AUTH_SECRET_KEY=your-actual-secret

# Session Secret
SECRET_KEY=generate-with-openssl-rand-hex-32

# Redis & Database (auto-configured)
REDIS_URL=redis://redis:6379
DATABASE_URL=sqlite:///./jobs.db
```

**Generate SECRET_KEY:**
```bash
openssl rand -hex 32
```

#### Frontend Environment

```bash
cd frontend

# Create .env file
nano .env
```

```env
REACT_APP_STACK_AUTH_PROJECT_ID=your-stack-auth-project-id
REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY=your-key
REACT_APP_API_URL=https://your-domain.com
# OR for testing with IP:
# REACT_APP_API_URL=http://your-ec2-ip
```

```bash
cd ..
```

### Step 2: Update CORS Settings

Edit `app.py` to include your production domain:

```bash
nano app.py
```

Find this section and update:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "https://your-domain.com",  # ADD THIS
        "http://your-ec2-ip"        # ADD THIS (for testing)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Step 3: Deploy Application

```bash
./deploy.sh
```

This script will:
1. Check prerequisites
2. Build React frontend
3. Build Docker containers
4. Start all services (backend, redis, nginx)
5. Run health checks

**Expected output:**
```
🎉 Deployment Complete!

Service URLs:
  Frontend: http://YOUR-IP
  Backend API: http://YOUR-IP/api/cache-status

Next Steps:
  1. Set up SSL certificates
  2. Point domain DNS to IP
```

### Step 4: Verify Deployment

```bash
# Check all services are running
docker-compose ps

# Should show 3 services: backend, redis, nginx

# Check logs
docker-compose logs -f
```

**Test endpoints:**
```bash
# Backend health check
curl http://localhost:8000/api/cache-status

# Frontend
curl http://localhost/health

# Trigger cache refresh
curl -X POST http://localhost:8000/api/refresh-cache
```

---

## Domain & SSL Setup

### Step 1: Configure Domain DNS

1. Go to your domain registrar (Namecheap, GoDaddy, etc.)
2. Add DNS A record:
   - **Type**: A
   - **Host**: @ (or your subdomain)
   - **Value**: Your EC2 Public IPv4 address
   - **TTL**: 300

3. Wait for DNS propagation (5-30 minutes)
   ```bash
   # Check DNS
   nslookup your-domain.com
   ```

### Step 2: Obtain SSL Certificate (Let's Encrypt)

Create SSL setup script:

```bash
nano setup-ssl.sh
```

```bash
#!/bin/bash

DOMAIN=$1

if [ -z "$DOMAIN" ]; then
    echo "Usage: ./setup-ssl.sh your-domain.com"
    exit 1
fi

# Stop nginx to free port 80
docker-compose stop nginx

# Get certificate
sudo certbot certonly --standalone -d $DOMAIN --email your-email@example.com --agree-tos --non-interactive

# Copy certificates
sudo mkdir -p ./ssl
sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem ./ssl/
sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem ./ssl/
sudo chown -R $USER:$USER ./ssl

# Restart nginx
docker-compose up -d nginx

echo "✅ SSL certificates obtained for $DOMAIN"
echo "🔒 HTTPS is now enabled!"
```

```bash
chmod +x setup-ssl.sh
./setup-ssl.sh your-domain.com
```

### Step 3: Auto-Renew SSL Certificates

```bash
# Create renewal script
sudo nano /etc/cron.d/certbot-renew
```

Add:
```
0 0 1 * * root certbot renew --quiet --post-hook "cd /home/ubuntu/internship-app && ./setup-ssl.sh your-domain.com"
```

---

## Troubleshooting

### Service Not Starting

```bash
# Check logs
docker-compose logs backend
docker-compose logs redis
docker-compose logs nginx

# Restart specific service
docker-compose restart backend

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

### Database Issues

```bash
# Check database file
ls -lah jobs.db

# Reset database (WARNING: deletes all data)
docker-compose down
rm jobs.db
touch jobs.db
chmod 666 jobs.db
docker-compose up -d
```

### Redis Connection Issues

```bash
# Check Redis
docker exec internship-redis redis-cli ping
# Should return: PONG

# Restart Redis
docker-compose restart redis
```

### Frontend Not Loading

```bash
# Check nginx logs
docker-compose logs nginx

# Rebuild frontend
cd frontend
npm run build
cd ..
docker-compose up -d --build nginx
```

### Port Already in Use

```bash
# Check what's using port 80
sudo lsof -i :80

# Stop conflicting service
sudo systemctl stop apache2  # or nginx
```

### Out of Memory (t2.micro)

```bash
# Check memory
free -h

# Restart services to free memory
docker-compose restart

# If persistent, consider upgrading to t3.small
```

---

## Maintenance

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f redis
docker-compose logs -f nginx

# Last 100 lines
docker-compose logs --tail=100
```

### Update Application

```bash
# Pull latest code
git pull origin main

# Redeploy
./deploy.sh
```

### Backup Database

```bash
# Create backup directory
mkdir -p backups

# Backup database
cp jobs.db backups/jobs-$(date +%Y%m%d-%H%M%S).db

# Automated daily backup (cron)
echo "0 2 * * * cd /home/ubuntu/internship-app && cp jobs.db backups/jobs-\$(date +\%Y\%m\%d).db" | crontab -
```

### Monitor Resources

```bash
# System resources
htop

# Disk usage
df -h

# Docker stats
docker stats
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart backend

# Full restart
docker-compose down && docker-compose up -d
```

### Clean Up Docker

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Complete cleanup (careful!)
docker system prune -a --volumes
```

---

## Security Best Practices

1. **Keep SSH Key Secure**
   - Never commit to Git
   - Store in secure location
   - Use passphrase protection

2. **Restrict SSH Access**
   ```bash
   # Only allow your IP
   sudo ufw allow from YOUR_IP to any port 22
   ```

3. **Regular Updates**
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   ```

4. **Monitor Logs**
   ```bash
   # Check for suspicious activity
   sudo tail -f /var/log/auth.log
   ```

5. **Environment Variables**
   - Never commit .env file
   - Rotate API keys regularly
   - Use strong SECRET_KEY

---

## Cost Optimization

### Free Tier Limits (12 months)
- 750 hours/month t2.micro
- 30 GB EBS storage
- 1 GB data transfer out

### After Free Tier
- **Stay on t2.micro**: ~$8.50/month
- **Upgrade to t3.small**: ~$15/month (better performance)
- **Reserved Instance**: Save 30-60% with 1-year commitment

### Monitor Usage
```bash
# AWS Cost Explorer in AWS Console
# Set billing alerts at $10, $20
```

---

## Performance Optimization

### 1. Enable Redis Persistence
Already configured in docker-compose.yml with `appendonly yes`

### 2. Database Maintenance
```bash
# Vacuum SQLite database monthly
docker exec -it internship-backend python3 -c "
from job_database import get_db
db = get_db()
db.execute('VACUUM')
db.close()
"
```

### 3. Monitor Application
```bash
# Install monitoring (optional)
docker run -d -p 9090:9090 prom/prometheus
```

---

## Quick Reference

### Common Commands

```bash
# Start all services
app-start   # or: docker-compose up -d

# Stop all services
app-stop    # or: docker-compose down

# Restart services
app-restart # or: docker-compose restart

# View logs
app-logs    # or: docker-compose logs -f

# Check status
app-status  # or: docker-compose ps

# Deploy/update
app-deploy  # or: ./deploy.sh
```

### Important Files

- **Configuration**: `.env`, `frontend/.env`
- **Logs**: `docker-compose logs`
- **Database**: `jobs.db`
- **SSL Certs**: `./ssl/`
- **Nginx Config**: `nginx.conf`

### Service URLs

- **Frontend**: `http://your-domain.com` or `http://your-ec2-ip`
- **Backend API**: `http://your-domain.com/api`
- **Health Check**: `http://your-domain.com/health`
- **Cache Status**: `http://your-domain.com/api/cache-status`

---

## Support

### Getting Help

1. Check logs: `docker-compose logs -f`
2. Check service status: `docker-compose ps`
3. Review this guide
4. Check AWS EC2 console for instance issues

### Common Issues

- **503 Bad Gateway**: Backend not running (check logs)
- **CORS Error**: Update app.py with your domain
- **SSL Error**: Run `setup-ssl.sh` again
- **Out of Memory**: Restart services or upgrade instance

---

## Next Steps After Deployment

1. ✅ Test the application thoroughly
2. ✅ Configure monitoring/alerting
3. ✅ Set up automated backups
4. ✅ Configure domain email
5. ✅ Add analytics (Google Analytics, etc.)
6. ✅ Set up error tracking (Sentry)
7. ✅ Create user documentation

**Your application is now live! 🎉**

Access it at: `https://your-domain.com`

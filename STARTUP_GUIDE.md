# Internship Matcher - Startup Guide

Complete guide for starting and managing the Internship Matcher application with proper cache management.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Daily Startup Checklist](#daily-startup-checklist)
3. [Cache Management](#cache-management)
4. [API Endpoints Reference](#api-endpoints-reference)
5. [Environment Setup](#environment-setup)
6. [Troubleshooting](#troubleshooting)
7. [Advanced Usage](#advanced-usage)

---

## Quick Start

### Using the Automated Script (Recommended)

```bash
# Start everything with cache refresh
./start.sh --all --refresh

# Start just the backend
./start.sh --backend

# Start with full cache refresh
./start.sh --all --refresh-full

# Check cache status
./start.sh --status
```

### Manual Startup

```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start Backend
source venv/bin/activate
python app.py

# Terminal 3: Start Frontend
cd frontend
npm start
```

---

## Daily Startup Checklist

Follow these steps every time you start working on the project:

### ✅ Step 1: Verify Redis is Running

```bash
# Check Redis status
redis-cli ping
# Should return: PONG

# If not running, start it:
brew services start redis  # macOS
# OR
sudo systemctl start redis  # Linux
```

### ✅ Step 2: Start Backend Server

```bash
cd /path/to/Internship-App
source venv/bin/activate
python app.py
```

**What happens on startup:**
- ✓ Initializes hybrid cache system (Redis + SQLite)
- ✓ Checks if cache has existing jobs
- ✓ If empty: Automatically scrapes latest jobs from GitHub
- ✓ If populated: Uses existing cache (4-hour TTL)
- ✓ Displays cache statistics

**Expected output:**
```
🚀 Starting up Internship Matcher with Hybrid Cache System...
✅ Redis connected successfully
✅ Database initialized successfully
📦 Using existing cache: 1234 jobs available
📊 Database: 1234 active jobs
⚡ Redis: 1234 jobs cached
✅ Startup complete!
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### ✅ Step 3: Start Frontend Server

```bash
cd frontend
npm start
```

Frontend will open automatically at `http://localhost:3000`

### ✅ Step 4: Verify Cache Status (Optional but Recommended)

```bash
curl http://localhost:8000/api/cache-status | python3 -m json.tool
```

**Example response:**
```json
{
  "hybrid_cache": {
    "redis": {
      "status": "active",
      "job_count": 1234,
      "hours_remaining": 3.5
    },
    "database": {
      "active_jobs": 1234,
      "total_jobs": 1500,
      "new_jobs_24h": 50
    },
    "hybrid": {
      "status": "optimal",
      "message": "Both Redis and Database available"
    }
  },
  "redis_available": true,
  "database_available": true
}
```

### ✅ Step 5: Refresh Cache (Only When Needed)

**When to refresh:**
- Starting a new work session (want latest jobs)
- Cache is older than 4 hours (Redis expired)
- Suspect stale data
- After changes to scraping logic

**Commands:**

```bash
# Smart refresh (auto-detects incremental vs full)
curl -X POST http://localhost:8000/api/refresh-cache

# Force full refresh (scrape everything)
curl -X POST "http://localhost:8000/api/refresh-cache?force_full=true"

# Incremental refresh (only new jobs from last 7 days)
curl -X POST "http://localhost:8000/api/refresh-cache-incremental?max_days_old=7"
```

---

## Cache Management

### Understanding the Hybrid Cache System

The application uses a **two-tier caching strategy**:

#### Tier 1: Redis (Speed Layer)
- **Purpose:** Fast in-memory cache for active sessions
- **TTL:** 4 hours (auto-expires)
- **Location:** `redis://localhost:6379`
- **Advantage:** Sub-millisecond response times

#### Tier 2: SQLite Database (Persistence Layer)
- **Purpose:** Long-term storage with deduplication
- **File:** `./jobs.db`
- **Features:**
  - Job deduplication via SHA-256 hashing
  - Historical tracking (`first_seen`, `last_seen`)
  - Auto-marks jobs inactive after 3 days
  - Never expires (permanent storage)

#### How They Work Together:

```
User Request → Check Redis → Hit? Return data
                            ↓
                           Miss? → Query Database → Return data
                                                   ↓
                                        Warm Redis cache for next request
```

**On Cache Refresh:**
1. Scrape jobs from GitHub repository
2. Hash each job (company|title|location|domain)
3. Check database for existing hash
4. If new: Insert with `first_seen` timestamp
5. If exists: Update `last_seen` timestamp
6. Store in Redis with 4-hour TTL
7. Mark old jobs (>3 days) as inactive

### Cache Refresh Strategies

#### 1. Smart Refresh (Recommended)

```bash
curl -X POST http://localhost:8000/api/refresh-cache
```

**Behavior:**
- Checks last scrape time
- If < 24 hours: Incremental scrape (new jobs only)
- If > 24 hours: Full scrape (all jobs)
- Database deduplication prevents duplicates

**Use when:**
- Daily startup routine
- Want fresh data without overthinking

#### 2. Full Refresh

```bash
curl -X POST "http://localhost:8000/api/refresh-cache?force_full=true"
```

**Behavior:**
- Clears Redis cache
- Scrapes all jobs from source
- Updates database with new `last_seen` timestamps
- Marks unseen jobs as inactive

**Use when:**
- Major changes to job repository
- Suspect data inconsistencies
- First-time setup

#### 3. Incremental Refresh

```bash
curl -X POST "http://localhost:8000/api/refresh-cache-incremental?max_days_old=7"
```

**Behavior:**
- Only scrapes and returns new jobs
- Filters by `max_days_old` parameter
- Faster, network-friendly
- Database prevents duplicates

**Use when:**
- Just want to check for new jobs
- Want to minimize scraping load
- Testing new scraping features

### Using the Python CLI Script

Alternative to curl commands:

```bash
# Check status only
python refresh_cache.py --status-only

# Smart refresh
python refresh_cache.py

# Full refresh
python refresh_cache.py --full

# Incremental refresh
python refresh_cache.py --incremental

# Full refresh with 30-day filter
python refresh_cache.py --full --days 30
```

**Advantages:**
- Pretty-printed output
- Progress indicators
- Before/after statistics
- Error handling with detailed messages

---

## API Endpoints Reference

### Cache Management Endpoints

#### GET `/api/cache-status`
**Purpose:** Get comprehensive cache and system status

**Response:**
```json
{
  "hybrid_cache": {
    "redis": {
      "status": "active|expired|unavailable",
      "job_count": 1234,
      "hours_remaining": 3.5
    },
    "database": {
      "active_jobs": 1234,
      "total_jobs": 1500,
      "new_jobs_24h": 50
    },
    "hybrid": {
      "status": "optimal|degraded|database_only",
      "message": "Status description"
    }
  },
  "redis_available": true,
  "database_available": true,
  "cache_system": "hybrid_redis_database",
  "redis_ttl_hours": 4
}
```

#### POST `/api/refresh-cache`
**Purpose:** Refresh cache with smart detection or force full refresh

**Parameters:**
- `force_full` (bool): Force full scrape (default: false)
- `max_days_old` (int): Filter jobs by days old (optional)

**Examples:**
```bash
# Smart refresh
curl -X POST http://localhost:8000/api/refresh-cache

# Force full
curl -X POST "http://localhost:8000/api/refresh-cache?force_full=true"

# 30-day filter
curl -X POST "http://localhost:8000/api/refresh-cache?max_days_old=30"

# Full with filter
curl -X POST "http://localhost:8000/api/refresh-cache?force_full=true&max_days_old=30"
```

**Response:**
```json
{
  "success": true,
  "message": "Cache refreshed successfully",
  "new_jobs": 50,
  "total_jobs": 1234,
  "database_success": true,
  "redis_success": true,
  "scrape_type": "smart|full|incremental",
  "max_days_old": null,
  "redis_ttl_hours": 4
}
```

#### POST `/api/refresh-cache-incremental`
**Purpose:** Force incremental refresh (new jobs only)

**Parameters:**
- `max_days_old` (int): Filter jobs by days old (optional)

**Example:**
```bash
curl -X POST "http://localhost:8000/api/refresh-cache-incremental?max_days_old=7"
```

#### GET `/api/database-stats`
**Purpose:** Get detailed database statistics

**Response:**
```json
{
  "success": true,
  "database_stats": {
    "total_jobs": 1500,
    "active_jobs": 1234,
    "inactive_jobs": 266,
    "sources": {
      "github_internships": 1234
    },
    "new_jobs_24h": 50,
    "latest_cache_operation": {
      "operation_type": "startup|manual_refresh|incremental",
      "timestamp": "2025-11-07T10:30:00",
      "jobs_affected": 1234
    }
  }
}
```

### Application Endpoints

#### POST `/api/upload`
Upload resume for job matching

#### POST `/api/match`
Match resume against cached jobs

#### GET `/api/health`
Health check endpoint

---

## Environment Setup

### Required Environment Variables

Create a `.env` file in the project root with these variables:

```bash
# REQUIRED - OpenAI API for resume parsing and skill extraction
OPENAI_API_KEY=sk-...

# OPTIONAL - Redis connection (defaults to localhost:6379)
REDIS_URL=redis://localhost:6379

# OPTIONAL - Database (defaults to SQLite local file)
DATABASE_URL=sqlite:///./jobs.db

# OPTIONAL - Stack Auth (for user authentication)
STACK_AUTH_PROJECT_ID=your-project-id
STACK_AUTH_PUBLISHABLE_CLIENT_KEY=pck_...
STACK_AUTH_SECRET_KEY=ssk_...

# OPTIONAL - AWS S3 (for resume storage)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket

# OPTIONAL - Google OAuth (if using)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/callback
```

### Frontend Environment Variables

Create `frontend/.env`:

```bash
# Stack Auth credentials (must match backend project)
REACT_APP_STACK_AUTH_PROJECT_ID=your-project-id
REACT_APP_STACK_AUTH_PUBLISHABLE_CLIENT_KEY=pck_...

# Backend API URL (for production deployments)
REACT_APP_API_URL=http://localhost:8000
```

### First-Time Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd Internship-App

# 2. Setup Python environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Setup Redis
bash ./setup_redis.sh

# 5. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 6. Setup frontend
cd frontend
npm install
cd ..

# 7. First run
./start.sh --all --refresh-full
```

### Verify Installation

```bash
# Check Redis
redis-cli ping  # Should return: PONG

# Check Python packages
pip list | grep -E "fastapi|uvicorn|redis|openai"

# Check Node modules
ls frontend/node_modules | grep react

# Check environment variables
source venv/bin/activate
python -c "import os; print('OpenAI Key:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')"
```

---

## Troubleshooting

### Redis Issues

**Problem:** `redis-cli: command not found`

**Solution:**
```bash
# Install Redis
./setup_redis.sh
# OR manually:
brew install redis  # macOS
sudo apt-get install redis-server  # Linux
```

**Problem:** `Could not connect to Redis at 127.0.0.1:6379`

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# Start Redis
brew services start redis  # macOS
sudo systemctl start redis  # Linux

# Or run in foreground
redis-server
```

**Problem:** Redis connects but cache not working

**Solution:**
```bash
# Check Redis keys
redis-cli
> KEYS *
> GET job_listings_cache

# Clear Redis if needed
> FLUSHALL

# Refresh cache
curl -X POST http://localhost:8000/api/refresh-cache
```

### Backend Issues

**Problem:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:**
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Problem:** `Port 8000 already in use`

**Solution:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill $(lsof -t -i:8000)

# Or use a different port
uvicorn app:app --port 8001
```

**Problem:** `OPENAI_API_KEY not set`

**Solution:**
```bash
# Add to .env file
echo "OPENAI_API_KEY=sk-your-key-here" >> .env

# Or export temporarily
export OPENAI_API_KEY=sk-your-key-here
```

### Frontend Issues

**Problem:** `npm: command not found`

**Solution:**
```bash
# Install Node.js
brew install node  # macOS
# OR download from nodejs.org
```

**Problem:** `Port 3000 already in use`

**Solution:**
```bash
# Kill process on port 3000
kill $(lsof -t -i:3000)

# Or use different port
PORT=3001 npm start
```

**Problem:** Stack Auth OAuth errors

**Solution:**
```bash
# Check environment variables are loaded
cd frontend
cat .env

# Verify variables in browser console
# Should see project ID and publishable key logged

# Check Stack Auth dashboard
# - OAuth providers configured
# - Callback URLs include http://localhost:3000/handler/*

# Rebuild if .env changed
npm run build
```

### Cache/Database Issues

**Problem:** Jobs not updating after scrape

**Solution:**
```bash
# Check cache status
curl http://localhost:8000/api/cache-status

# Force full refresh
curl -X POST "http://localhost:8000/api/refresh-cache?force_full=true"

# Check database directly
sqlite3 jobs.db "SELECT COUNT(*) FROM jobs WHERE is_active=1;"
```

**Problem:** Database locked errors

**Solution:**
```bash
# Close all connections to database
pkill -f "python app.py"

# Remove lock file if exists
rm jobs.db-journal

# Restart backend
python app.py
```

**Problem:** Job scraping fails

**Solution:**
```bash
# Check internet connection
curl https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md

# Check OpenAI API key
python -c "import os; import openai; openai.api_key = os.getenv('OPENAI_API_KEY'); print('Key valid')"

# Try manual refresh with verbose output
python refresh_cache.py --full
```

---

## Advanced Usage

### Running in Production

```bash
# Use production environment variables
export REDIS_URL=redis://production-redis:6379
export DATABASE_URL=postgresql://user:pass@host/db

# Run with multiple workers
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4

# Build frontend for production
cd frontend
npm run build
# Serve with nginx or similar
```

### Custom Cache TTL

Edit `job_cache.py`:
```python
REDIS_TTL = 4 * 60 * 60  # 4 hours (change as needed)
```

### Monitoring Cache Performance

```bash
# Watch cache status in real-time
watch -n 5 'curl -s http://localhost:8000/api/cache-status | python3 -m json.tool'

# Monitor Redis memory
redis-cli INFO memory

# Check database size
du -h jobs.db
```

### Backup and Restore

```bash
# Backup database
cp jobs.db jobs.db.backup.$(date +%Y%m%d)

# Restore database
cp jobs.db.backup.20251107 jobs.db

# Export jobs to JSON
sqlite3 jobs.db "SELECT * FROM jobs" | python3 -m json.tool > jobs_export.json
```

### Debugging

```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
python app.py

# Run backend with auto-reload
uvicorn app:app --reload

# Check all environment variables
env | grep -E "OPENAI|REDIS|STACK|AWS"
```

---

## Quick Reference

### Daily Commands Cheatsheet

```bash
# Start everything
./start.sh --all

# Start with cache refresh
./start.sh --all --refresh

# Check cache status
./start.sh --status

# Manual cache refresh
curl -X POST http://localhost:8000/api/refresh-cache

# Check Redis
redis-cli ping

# View backend logs (if using start.sh)
tail -f backend.log

# View frontend logs (if using start.sh)
tail -f frontend.log

# Stop all services
kill $(lsof -t -i:8000,3000)
```

### Service URLs

- **Backend API:** http://localhost:8000
- **Frontend App:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs
- **Redis:** redis://localhost:6379

### Important Files

- **Backend:** `app.py`
- **Cache Logic:** `job_cache.py`
- **Job Scraper:** `job_scraper.py`
- **Database:** `jobs.db`
- **Frontend Config:** `frontend/src/stack/client.ts`
- **Environment:** `.env`, `frontend/.env`

---

## Support

For issues or questions:
1. Check this guide's troubleshooting section
2. Review backend/frontend logs
3. Check `jobs.db` and Redis for data consistency
4. Verify all environment variables are set correctly

**Happy coding!** 🚀

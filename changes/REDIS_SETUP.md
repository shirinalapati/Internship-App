# Redis Caching Setup

This application uses Redis to cache job data, dramatically improving performance and reducing redundant scraping.

## 🚀 Benefits

- **1000x faster** - Jobs load from cache in microseconds instead of 30+ seconds of scraping
- **Scalable** - Handles 1000+ concurrent users efficiently
- **Smart caching** - Auto-expires after 24 hours, scrapes on startup if needed
- **Fallback support** - Works without Redis (slower, but functional)

## 📋 Local Development Setup

### Option 1: Using Docker (Recommended)

```bash
# Run Redis in a Docker container
docker run -d -p 6379:6379 --name redis-internship redis:7-alpine

# Stop Redis
docker stop redis-internship

# Start Redis again
docker start redis-internship
```

### Option 2: Install Redis Locally

**macOS:**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis
```

**Windows:**
- Download from https://redis.io/download or use WSL

### Verify Redis is Running

```bash
redis-cli ping
# Should return: PONG
```

## 🔧 Configuration

Add to your `.env` file:

```bash
# Redis Configuration (optional - defaults to localhost)
REDIS_URL=redis://localhost:6379

# For cloud Redis (Render, Railway, Upstash, etc.)
# REDIS_URL=redis://username:password@hostname:port
```

## ☁️ Production Deployment

### Render (Recommended)

1. In your Render dashboard, create a **Redis** service
2. Copy the **Internal Redis URL** 
3. Add it as an environment variable:
   ```
   REDIS_URL=redis://red-xxxxx:6379
   ```

### Railway

1. Add Redis to your project
2. Copy the **Redis URL** from the variables tab
3. Set as environment variable

### Upstash (Serverless Redis)

1. Create a database at https://upstash.com
2. Copy the Redis URL
3. Set as environment variable

## 📊 Monitoring Cache

### Check Cache Status

```bash
curl http://localhost:8000/api/cache-status
```

Response:
```json
{
  "redis_connected": true,
  "cache_info": {
    "status": "active",
    "job_count": 145,
    "ttl_seconds": 82800,
    "hours_remaining": 23.0,
    "message": "145 jobs cached, expires in 23.0h"
  },
  "cache_key": "internship_jobs_cache",
  "ttl_hours": 24.0
}
```

### Manually Refresh Cache

```bash
curl -X POST http://localhost:8000/api/refresh-cache
```

This forces a fresh scrape and updates the cache immediately.

## 🔍 How It Works

### On Server Startup:
1. ✅ Connect to Redis
2. 📦 Check if cache exists and is fresh (<24h old)
3. 🌐 If cache is empty/stale, scrape jobs and populate cache
4. ⚡ All users get instant results from cache

### On User Request:
1. ⚡ Try to get jobs from Redis cache (microseconds)
2. 🌐 If cache miss, scrape and cache (30 seconds)
3. 📤 Return jobs to user

### Cache Expiration:
- Automatically expires after **24 hours**
- Next request triggers fresh scrape
- All subsequent users get the fresh cache

## 🛠️ Troubleshooting

### Redis Connection Failed
```
⚠️ Redis connection failed: Error 111 connecting to localhost:6379
```
**Solution:** Make sure Redis is running (`redis-cli ping`)

### No Cache Without Redis
```
⚠️ Running without Redis - jobs will be scraped per request
```
**Impact:** App still works, but slower. Each user triggers a scrape.

### Cache Corrupted
If you see JSON decode errors, clear the cache:
```bash
redis-cli DEL internship_jobs_cache
```

## 📈 Performance Comparison

| Scenario | Without Redis | With Redis |
|----------|--------------|------------|
| First user | 30 seconds | 30 seconds* |
| User 2-1000 | 30 seconds each | <0.01 seconds |
| Total for 1000 users | ~8 hours | ~30 seconds |

*Scraped once on startup or first request

## 🔐 Security Notes

- Use secure Redis URLs in production (TLS/SSL)
- Don't expose Redis port publicly
- Use authentication for cloud Redis
- Keep REDIS_URL in environment variables, never in code


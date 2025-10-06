"""
Job Cache Module - Redis-based caching for scraped jobs
Caches job data for 24 hours to avoid redundant scraping
"""
import os
import json
import redis
from typing import List, Dict, Optional
from datetime import datetime

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_KEY = "internship_jobs_cache"
CACHE_TTL = 24 * 60 * 60  # 24 hours in seconds

# Initialize Redis client
redis_client = None

def init_redis():
    """Initialize Redis connection"""
    global redis_client
    try:
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        # Test connection
        redis_client.ping()
        print("✅ Redis connected successfully")
        return True
    except redis.ConnectionError as e:
        print(f"⚠️ Redis connection failed: {e}")
        print("📝 Continuing without cache - will scrape jobs on each request")
        redis_client = None
        return False
    except Exception as e:
        print(f"❌ Redis initialization error: {e}")
        redis_client = None
        return False

def get_cached_jobs() -> Optional[List[Dict]]:
    """
    Get cached jobs from Redis
    Returns None if cache miss or Redis unavailable
    """
    if not redis_client:
        return None
    
    try:
        cached_data = redis_client.get(CACHE_KEY)
        if cached_data:
            jobs = json.loads(cached_data)
            print(f"✅ Retrieved {len(jobs)} jobs from cache")
            return jobs
        else:
            print("📝 Cache miss - no jobs in cache")
            return None
    except redis.RedisError as e:
        print(f"⚠️ Redis error while getting cache: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in cache: {e}")
        # Clear corrupted cache
        try:
            redis_client.delete(CACHE_KEY)
        except:
            pass
        return None

def set_cached_jobs(jobs: List[Dict]) -> bool:
    """
    Cache jobs in Redis with 24-hour TTL
    Returns True if successful, False otherwise
    """
    if not redis_client:
        print("⚠️ Redis not available - skipping cache")
        return False
    
    try:
        jobs_json = json.dumps(jobs)
        redis_client.setex(CACHE_KEY, CACHE_TTL, jobs_json)
        print(f"✅ Cached {len(jobs)} jobs with 24h TTL")
        return True
    except redis.RedisError as e:
        print(f"⚠️ Redis error while setting cache: {e}")
        return False
    except Exception as e:
        print(f"❌ Error caching jobs: {e}")
        return False

def get_cache_info() -> Dict:
    """Get cache metadata (TTL, size, etc.)"""
    if not redis_client:
        return {
            "status": "unavailable",
            "message": "Redis not connected"
        }
    
    try:
        exists = redis_client.exists(CACHE_KEY)
        if not exists:
            return {
                "status": "empty",
                "message": "No cached jobs"
            }
        
        ttl = redis_client.ttl(CACHE_KEY)
        cached_data = redis_client.get(CACHE_KEY)
        job_count = len(json.loads(cached_data)) if cached_data else 0
        
        hours_remaining = ttl / 3600 if ttl > 0 else 0
        
        return {
            "status": "active",
            "job_count": job_count,
            "ttl_seconds": ttl,
            "hours_remaining": round(hours_remaining, 1),
            "message": f"{job_count} jobs cached, expires in {round(hours_remaining, 1)}h"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def clear_cache() -> bool:
    """Clear the job cache (useful for manual refresh)"""
    if not redis_client:
        return False
    
    try:
        redis_client.delete(CACHE_KEY)
        print("✅ Cache cleared successfully")
        return True
    except redis.RedisError as e:
        print(f"⚠️ Error clearing cache: {e}")
        return False

def is_redis_available() -> bool:
    """Check if Redis is connected and available"""
    if not redis_client:
        return False
    
    try:
        redis_client.ping()
        return True
    except:
        return False


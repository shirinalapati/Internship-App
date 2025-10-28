"""
Job Cache Module - Hybrid Redis + Database caching for scraped jobs
- Redis: Fast access to active job listings (4-hour TTL)
- Database: Persistent storage with deduplication and historical tracking
"""
import os
import json
import redis
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from job_database import (
    init_database, bulk_insert_jobs, get_active_jobs, 
    get_new_jobs_since, get_database_stats, record_cache_operation,
    cleanup_old_metadata
)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_KEY = "internship_jobs_cache"
CACHE_TTL = 4 * 60 * 60  # 4 hours in seconds (reduced from 24h)
LAST_SCRAPE_KEY = "last_scrape_time"

# Initialize Redis client
redis_client = None
database_initialized = False

def init_redis():
    """Initialize Redis connection and database"""
    global redis_client, database_initialized
    
    # Initialize database first
    if not database_initialized:
        database_initialized = init_database()
        if database_initialized:
            print("✅ Database initialized successfully")
        else:
            print("⚠️ Database initialization failed")
    
    # Initialize Redis
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
        print("📝 Continuing with database only - Redis cache disabled")
        redis_client = None
        return database_initialized
    except Exception as e:
        print(f"❌ Redis initialization error: {e}")
        redis_client = None
        return database_initialized

def get_cached_jobs() -> Optional[List[Dict]]:
    """
    Get cached jobs using hybrid approach:
    1. Try Redis first (fast access)
    2. Fall back to database if Redis unavailable
    3. Warm Redis cache from database if needed
    """
    # Try Redis first
    if redis_client:
        try:
            cached_data = redis_client.get(CACHE_KEY)
            if cached_data:
                jobs = json.loads(cached_data)
                print(f"⚡ Retrieved {len(jobs)} jobs from Redis cache")
                return jobs
        except redis.RedisError as e:
            print(f"⚠️ Redis error while getting cache: {e}")
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in Redis cache: {e}")
            # Clear corrupted cache
            try:
                redis_client.delete(CACHE_KEY)
            except:
                pass
    
    # Redis miss or unavailable - try database
    if database_initialized:
        try:
            jobs = get_active_jobs(limit=10000)  # Get all active jobs
            if jobs:
                print(f"📦 Retrieved {len(jobs)} jobs from database")
                
                # Warm Redis cache if available
                if redis_client and jobs:
                    try:
                        jobs_json = json.dumps(jobs, default=str)
                        redis_client.setex(CACHE_KEY, CACHE_TTL, jobs_json)
                        print(f"🔄 Warmed Redis cache with {len(jobs)} jobs")
                    except Exception as e:
                        print(f"⚠️ Failed to warm Redis cache: {e}")
                
                return jobs
            else:
                print("📝 No active jobs in database")
                return None
        except Exception as e:
            print(f"❌ Database error while getting jobs: {e}")
            return None
    
    print("📝 No cache available - Redis and database both unavailable")
    return None

def set_cached_jobs(jobs: List[Dict], cache_type: str = 'daily') -> Dict:
    """
    Store jobs using hybrid approach:
    1. Store in database with deduplication
    2. Update Redis cache for fast access
    3. Record cache operation metadata
    Returns summary of operations
    """
    summary = {
        'database_success': False,
        'redis_success': False,
        'new_jobs': 0,
        'total_jobs': len(jobs)
    }
    
    # Store in database first (with deduplication)
    if database_initialized:
        try:
            db_result = bulk_insert_jobs(jobs)
            if 'error' not in db_result:
                summary['database_success'] = True
                summary['new_jobs'] = db_result.get('new_jobs', 0)
                summary['updated_jobs'] = db_result.get('updated_jobs', 0)
                
                # Record cache operation
                record_cache_operation(
                    cache_type=cache_type,
                    job_count=len(jobs),
                    new_jobs=summary['new_jobs'],
                    status='success',
                    metadata=db_result
                )
                
                print(f"✅ Database: {summary['new_jobs']} new jobs, {summary['updated_jobs']} updated")
            else:
                print(f"❌ Database error: {db_result['error']}")
        except Exception as e:
            print(f"❌ Database error while storing jobs: {e}")
    
    # Update Redis cache
    if redis_client:
        try:
            # Get fresh active jobs from database for Redis
            if database_initialized:
                active_jobs = get_active_jobs(limit=10000)
                if active_jobs:
                    jobs_json = json.dumps(active_jobs, default=str)
                    redis_client.setex(CACHE_KEY, CACHE_TTL, jobs_json)
                    summary['redis_success'] = True
                    print(f"✅ Redis cache updated with {len(active_jobs)} active jobs")
            else:
                # Fallback to original Redis-only approach
                jobs_json = json.dumps(jobs, default=str)
                redis_client.setex(CACHE_KEY, CACHE_TTL, jobs_json)
                summary['redis_success'] = True
                print(f"✅ Redis cache updated with {len(jobs)} jobs")
        except redis.RedisError as e:
            print(f"⚠️ Redis error while setting cache: {e}")
        except Exception as e:
            print(f"❌ Error updating Redis cache: {e}")
    
    # Update last scrape time
    if redis_client:
        try:
            redis_client.set(LAST_SCRAPE_KEY, datetime.utcnow().isoformat())
        except:
            pass
    
    return summary

def get_cache_info() -> Dict:
    """Get comprehensive cache metadata from both Redis and Database"""
    info = {
        "redis": {"status": "unavailable"},
        "database": {"status": "unavailable"},
        "hybrid": {"status": "partial"}
    }
    
    # Redis info
    if redis_client:
        try:
            exists = redis_client.exists(CACHE_KEY)
            if exists:
                ttl = redis_client.ttl(CACHE_KEY)
                cached_data = redis_client.get(CACHE_KEY)
                job_count = len(json.loads(cached_data)) if cached_data else 0
                hours_remaining = ttl / 3600 if ttl > 0 else 0
                
                info["redis"] = {
                    "status": "active",
                    "job_count": job_count,
                    "ttl_seconds": ttl,
                    "hours_remaining": round(hours_remaining, 1),
                    "message": f"{job_count} jobs cached, expires in {round(hours_remaining, 1)}h"
                }
            else:
                info["redis"] = {
                    "status": "empty",
                    "message": "No jobs in Redis cache"
                }
        except Exception as e:
            info["redis"] = {
                "status": "error",
                "message": str(e)
            }
    
    # Database info
    if database_initialized:
        try:
            db_stats = get_database_stats()
            info["database"] = {
                "status": "active",
                "total_jobs": db_stats.get('total_jobs', 0),
                "active_jobs": db_stats.get('active_jobs', 0),
                "inactive_jobs": db_stats.get('inactive_jobs', 0),
                "new_jobs_24h": db_stats.get('new_jobs_24h', 0),
                "sources": db_stats.get('sources', {}),
                "latest_cache": db_stats.get('latest_cache', {}),
                "message": f"{db_stats.get('active_jobs', 0)} active jobs in database"
            }
        except Exception as e:
            info["database"] = {
                "status": "error",
                "message": str(e)
            }
    
    # Hybrid status
    redis_ok = info["redis"]["status"] in ["active", "empty"]
    db_ok = info["database"]["status"] == "active"
    
    if redis_ok and db_ok:
        info["hybrid"]["status"] = "optimal"
        info["hybrid"]["message"] = "Both Redis and Database available"
    elif db_ok:
        info["hybrid"]["status"] = "database_only"
        info["hybrid"]["message"] = "Database available, Redis unavailable"
    elif redis_ok:
        info["hybrid"]["status"] = "redis_only"
        info["hybrid"]["message"] = "Redis available, Database unavailable"
    else:
        info["hybrid"]["status"] = "unavailable"
        info["hybrid"]["message"] = "Both Redis and Database unavailable"
    
    return info

def clear_cache() -> Dict:
    """Clear both Redis and optionally database cache"""
    result = {"redis": False, "database": False}
    
    # Clear Redis cache
    if redis_client:
        try:
            redis_client.delete(CACHE_KEY)
            redis_client.delete(LAST_SCRAPE_KEY)
            result["redis"] = True
            print("✅ Redis cache cleared successfully")
        except redis.RedisError as e:
            print(f"⚠️ Error clearing Redis cache: {e}")
    
    return result

def should_do_incremental_scrape() -> bool:
    """
    Determine if we should do incremental scraping vs full scrape
    Based on last scrape time and cache status
    """
    if not redis_client:
        return True  # Always incremental if no Redis
    
    try:
        last_scrape = redis_client.get(LAST_SCRAPE_KEY)
        if not last_scrape:
            print("📝 No last scrape time - doing full scrape")
            return False  # Full scrape if never scraped
        
        last_scrape_time = datetime.fromisoformat(last_scrape)
        time_since_scrape = datetime.utcnow() - last_scrape_time
        
        # Do full scrape if more than 24 hours since last scrape
        if time_since_scrape > timedelta(hours=24):
            print(f"📝 Last scrape was {time_since_scrape} ago - doing full scrape")
            return False
        
        # Do incremental scrape if less than 24 hours
        print(f"📝 Last scrape was {time_since_scrape} ago - doing incremental scrape")
        return True
        
    except Exception as e:
        print(f"⚠️ Error checking last scrape time: {e}")
        return True  # Default to incremental

def get_new_jobs_only(scraped_jobs: List[Dict]) -> List[Dict]:
    """
    Filter scraped jobs to only return truly new ones
    Uses database to check for existing jobs
    """
    if not database_initialized:
        print("⚠️ Database not available - returning all jobs")
        return scraped_jobs
    
    try:
        from job_database import generate_job_hash, get_db, Job
        
        # Generate hashes for all scraped jobs
        scraped_hashes = {}
        for job in scraped_jobs:
            job_hash = generate_job_hash(
                job.get('company', ''),
                job.get('title', ''),
                job.get('location', ''),
                job.get('apply_link', '')
            )
            scraped_hashes[job_hash] = job
        
        # Check which hashes exist in database
        db = get_db()
        try:
            existing_hashes = set()
            if scraped_hashes:
                existing_jobs = db.query(Job.job_hash).filter(
                    Job.job_hash.in_(list(scraped_hashes.keys()))
                ).all()
                existing_hashes = {job.job_hash for job in existing_jobs}
        finally:
            db.close()
        
        # Return only jobs with new hashes
        new_jobs = [
            job for job_hash, job in scraped_hashes.items() 
            if job_hash not in existing_hashes
        ]
        
        print(f"🔍 Filtered {len(scraped_jobs)} scraped jobs → {len(new_jobs)} new jobs")
        return new_jobs
        
    except Exception as e:
        print(f"❌ Error filtering new jobs: {e}")
        return scraped_jobs  # Return all jobs on error

def get_jobs_for_matching(limit: Optional[int] = None) -> List[Dict]:
    """
    Get jobs optimized for matching algorithm
    Tries Redis first, falls back to database
    """
    jobs = get_cached_jobs()
    
    if jobs and limit:
        return jobs[:limit]
    elif jobs:
        return jobs
    else:
        # No cached jobs - try database directly
        if database_initialized:
            return get_active_jobs(limit=limit)
        else:
            return []

def is_hybrid_cache_available() -> bool:
    """Check if either Redis or Database is available"""
    redis_ok = False
    db_ok = database_initialized
    
    if redis_client:
        try:
            redis_client.ping()
            redis_ok = True
        except:
            pass
    
    return redis_ok or db_ok

def is_redis_available() -> bool:
    """Check if Redis is connected and available"""
    if not redis_client:
        return False
    
    try:
        redis_client.ping()
        return True
    except:
        return False

def is_database_available() -> bool:
    """Check if database is available"""
    return database_initialized

# Weekly cleanup function
def perform_weekly_cleanup():
    """Perform weekly maintenance tasks"""
    if database_initialized:
        try:
            cleanup_old_metadata(days=30)
            print("✅ Weekly cleanup completed")
        except Exception as e:
            print(f"❌ Weekly cleanup failed: {e}")

# Initialize on import
init_redis()


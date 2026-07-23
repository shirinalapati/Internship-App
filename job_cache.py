"""
Job Cache Module - Hybrid Redis + Database caching for scraped jobs
- Redis: Fast access to active job listings (4-hour TTL)
- Database: Persistent storage with deduplication and historical tracking
"""
import logging
import os
import json
import redis
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
from job_database import (
    init_database, bulk_insert_jobs, get_active_jobs,
    get_active_jobs_paginated, get_job_count,
    get_new_jobs_since, get_database_stats, record_cache_operation,
    cleanup_old_metadata, get_distinct_active_companies
)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_KEY = "internship_jobs_cache"
CACHE_TTL = 2 * 60 * 60  # 2 hours in seconds (reduced from 4h to limit Redis memory footprint)
LAST_SCRAPE_KEY = "last_scrape_time"

# Distinct-company list backing the avoid/target-company filter autocomplete.
# Small payload (low hundreds of names) so it's cached as a single JSON blob —
# no need for the chunked list-streaming used for the full jobs cache.
COMPANIES_CACHE_KEY = "internship_companies_cache"
COMPANIES_CACHE_TTL = CACHE_TTL  # same freshness window as the jobs cache

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
            logger.info("Database initialized successfully")
        else:
            logger.warning("Database initialization failed")

    # Initialize Redis
    try:
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=15,
            socket_timeout=30,
            retry_on_timeout=True
        )
        # Test connection
        redis_client.ping()
        logger.info("Redis connected successfully")
        return True
    except redis.ConnectionError as e:
        logger.warning(f"Redis connection failed: {e} — continuing with database only")
        redis_client = None
        return database_initialized
    except Exception as e:
        logger.error(f"Redis initialization error: {e}")
        redis_client = None
        return database_initialized

def refresh_redis_from_database(page_size: int = 500) -> int:
    """
    Stream all active jobs from the database into Redis in fixed-size chunks.

    Instead of loading 10 000+ rows into a single Python list, this function
    fetches ``page_size`` rows at a time, serialises each page to JSON, and
    appends it to a Redis list key.  Peak memory per cycle is proportional to
    one page rather than the entire dataset.

    The Redis key is rebuilt atomically: a temporary key is populated first,
    then renamed over the live key so readers never see a partial dataset.

    Args:
        page_size: Number of jobs to fetch per database round-trip (default 500).

    Returns:
        Total number of jobs written to Redis, or 0 on failure.
    """
    if not redis_client:
        logger.warning("refresh_redis_from_database: Redis unavailable — skipping")
        return 0

    if not database_initialized:
        logger.warning("refresh_redis_from_database: database unavailable — skipping")
        return 0

    tmp_key = f"{CACHE_KEY}:tmp"
    total = 0
    offset = 0

    try:
        # Remove any leftover temp key from a previous failed run
        redis_client.delete(tmp_key)

        while True:
            page = get_active_jobs_paginated(offset=offset, limit=page_size)
            if not page:
                break  # No more rows

            # Serialise this page and push each job as a separate list element
            # so we never hold the full dataset in memory at once.
            pipe = redis_client.pipeline(transaction=False)
            for job in page:
                pipe.rpush(tmp_key, json.dumps(job, default=str))
            pipe.execute()

            page_len = len(page)
            total += page_len
            offset += page_size

            if total % 2000 == 0 or page_len < page_size:
                logger.info(f"[Cache refresh] Streamed {total} jobs to Redis...")

            # Free the page immediately so GC can reclaim it
            del page

            # If this page was smaller than a full page, we've reached the end
            if page_len < page_size:
                break

        if total == 0:
            logger.info("refresh_redis_from_database: no active jobs found")
            redis_client.delete(tmp_key)
            return 0

        # Atomically replace the live key and set TTL
        pipe = redis_client.pipeline()
        pipe.rename(tmp_key, CACHE_KEY)
        pipe.expire(CACHE_KEY, CACHE_TTL)
        pipe.execute()

        logger.info(f"[Cache refresh] Complete — {total} jobs in Redis (TTL {CACHE_TTL // 3600}h)")
        return total

    except Exception as e:
        logger.error(f"refresh_redis_from_database failed: {e}")
        try:
            redis_client.delete(tmp_key)
        except Exception:
            pass
        return 0


def get_cached_jobs() -> Optional[List[Dict]]:
    """
    Get cached jobs using hybrid approach:
    1. Try Redis first (fast access)
    2. Fall back to database if Redis unavailable, fetching in pages to
       avoid loading the entire dataset into memory at once
    3. Warm Redis cache from database if needed (via paginated streaming)
    """
    # Try Redis first
    if redis_client:
        try:
            key_type = redis_client.type(CACHE_KEY)
            if key_type == "list":
                # New list-based storage: each element is a JSON-encoded job dict
                raw_items = redis_client.lrange(CACHE_KEY, 0, -1)
                if raw_items:
                    jobs = [json.loads(item) for item in raw_items]
                    del raw_items
                    return jobs
            elif key_type == "string":
                # Legacy string key (single JSON blob) — read and migrate
                cached_data = redis_client.get(CACHE_KEY)
                if cached_data:
                    jobs = json.loads(cached_data)
                    return jobs
            # key_type == "none" means key doesn't exist — fall through to DB
        except redis.RedisError as e:
            logger.warning(f"Redis error while getting cache: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Redis cache: {e}")
            # Clear corrupted cache
            try:
                redis_client.delete(CACHE_KEY)
            except Exception:
                pass
    
    # Redis miss or unavailable — try database using paginated fetches
    if database_initialized:
        try:
            # Warm Redis via streaming if possible (avoids one giant list)
            if redis_client:
                total = refresh_redis_from_database()
                if total:
                    logger.info(f"Warmed Redis cache with {total} jobs (paginated)")
                    # Now read back from Redis so callers get a consistent list
                    try:
                        raw_items = redis_client.lrange(CACHE_KEY, 0, -1)
                        jobs = [json.loads(item) for item in raw_items]
                        del raw_items
                        return jobs if jobs else None
                    except Exception as e:
                        logger.warning(f"Could not read back from Redis after warm: {e}")

            # Redis unavailable — assemble list page by page from the database
            jobs: List[Dict] = []
            offset = 0
            page_size = 500
            while True:
                page = get_active_jobs_paginated(offset=offset, limit=page_size)
                if not page:
                    break
                page_len = len(page)
                jobs.extend(page)
                offset += page_size
                del page
                if len(jobs) % 2000 == 0:
                    logger.info(f"Loaded {len(jobs)} jobs from database...")
                if page_len < page_size:
                    break  # Last page reached

            if jobs:
                logger.info(f"Retrieved {len(jobs)} jobs from database (paginated)")
                return jobs
            else:
                logger.info("No active jobs in database")
                return None
        except Exception as e:
            logger.error(f"Database error while getting jobs: {e}")
            return None

    logger.warning("No cache available — Redis and database both unavailable")
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
                
                logger.info(f"Database: {summary['new_jobs']} new jobs, {summary['updated_jobs']} updated")
            else:
                logger.error(f"Database error: {db_result['error']}")
        except Exception as e:
            logger.error(f"Database error while storing jobs: {e}")

    # Update Redis cache — stream from database in chunks to avoid a large
    # in-memory list.  Explicit del of the incoming jobs list helps GC.
    del jobs  # caller's list no longer needed; database is the source of truth
    if redis_client:
        try:
            if database_initialized:
                cached_count = refresh_redis_from_database()
                if cached_count:
                    summary['redis_success'] = True
                    logger.info(f"Redis cache updated with {cached_count} jobs (paginated)")
            else:
                logger.warning("set_cached_jobs: database unavailable, Redis not updated")
        except redis.RedisError as e:
            logger.warning(f"Redis error while setting cache: {e}")
        except Exception as e:
            logger.error(f"Error updating Redis cache: {e}")
    
    # Update last scrape time
    if redis_client:
        try:
            redis_client.set(LAST_SCRAPE_KEY, datetime.utcnow().isoformat())
        except:
            pass

    # Recompute the distinct-companies cache now, at write time, rather than
    # leaving it to whichever request happens to miss the cache next. Keeps
    # the avoid/target-company autocomplete in sync with every scrape without
    # a separate cron.
    if summary['database_success']:
        refresh_companies_cache()

    return summary

def refresh_companies_cache() -> int:
    """Recompute the distinct-active-companies list from the database and
    push it into Redis. Called after every successful scrape write; also
    safe to call directly (e.g. from a lazy cache-miss fallback)."""
    if not database_initialized:
        return 0
    try:
        companies = get_distinct_active_companies()
        if redis_client and companies:
            redis_client.setex(COMPANIES_CACHE_KEY, COMPANIES_CACHE_TTL, json.dumps(companies))
        return len(companies)
    except Exception as e:
        logger.error(f"refresh_companies_cache failed: {e}")
        return 0

def get_cached_companies() -> List[str]:
    """
    Distinct active-job company names, hybrid Redis + DB (same tiering as
    get_cached_jobs): Redis first, DB fallback with a lazy cache warm.
    """
    if redis_client:
        try:
            cached = redis_client.get(COMPANIES_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except redis.RedisError as e:
            logger.warning(f"Redis error while getting companies cache: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in companies cache: {e}")
            try:
                redis_client.delete(COMPANIES_CACHE_KEY)
            except Exception:
                pass

    # Redis miss/unavailable — read straight from the database and, if
    # possible, warm Redis so the next request doesn't repeat the query.
    if database_initialized:
        companies = get_distinct_active_companies()
        if redis_client and companies:
            try:
                redis_client.setex(COMPANIES_CACHE_KEY, COMPANIES_CACHE_TTL, json.dumps(companies))
            except redis.RedisError:
                pass
        return companies

    return []

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
                # Cache key is now a Redis list — use llen() for O(1) count
                key_type = redis_client.type(CACHE_KEY)
                if key_type == "list":
                    job_count = redis_client.llen(CACHE_KEY)
                else:
                    # Legacy string key — fall back to JSON parse for count
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
            redis_client.delete(COMPANIES_CACHE_KEY)
            result["redis"] = True
            logger.info("Redis cache cleared successfully")
        except redis.RedisError as e:
            logger.warning(f"Error clearing Redis cache: {e}")
    
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
            logger.info("No last scrape time — doing full scrape")
            return False  # Full scrape if never scraped

        last_scrape_time = datetime.fromisoformat(last_scrape)
        time_since_scrape = datetime.utcnow() - last_scrape_time

        if time_since_scrape > timedelta(hours=24):
            logger.info(f"Last scrape was {time_since_scrape} ago — doing full scrape")
            return False

        logger.info(f"Last scrape was {time_since_scrape} ago — doing incremental scrape")
        return True

    except Exception as e:
        logger.warning(f"Error checking last scrape time: {e}")
        return True  # Default to incremental

def get_new_jobs_only(scraped_jobs: List[Dict]) -> List[Dict]:
    """
    Filter scraped jobs to only return truly new ones
    Uses database to check for existing jobs
    """
    if not database_initialized:
        logger.warning("Database not available — returning all jobs")
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
        
        logger.info(f"Filtered {len(scraped_jobs)} scraped jobs → {len(new_jobs)} new jobs")
        return new_jobs

    except Exception as e:
        logger.error(f"Error filtering new jobs: {e}")
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
            logger.info("Weekly cleanup completed")
        except Exception as e:
            logger.error(f"Weekly cleanup failed: {e}")

# Initialize on import
init_redis()


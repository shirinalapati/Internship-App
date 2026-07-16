import logging
import os
import re
import secrets
import subprocess
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, File, UploadFile, HTTPException, Form, Query, Depends, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
from dotenv import load_dotenv
import io
import json
import asyncio
from datetime import datetime

# Import our modules
from resume_parser import parse_resume, is_valid_resume
from resume_parser.parse_resume import extract_text_only
from job_scrapers.dispatcher import scrape_jobs
from matching.matcher import match_resume_to_jobs, analyze_and_match_single_call
from matching.metadata_matcher import extract_resume_metadata
from job_categories import CATEGORY_IDS


def _parse_categories(raw: str):
    """Parse a comma-separated `categories` form value into a validated id list.

    Unknown ids are dropped; empty result => no department filtering.
    """
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip() in CATEGORY_IDS]
import job_cache
from s3_service import upload_resume_to_s3, download_resume_from_s3, delete_resume_from_s3
from resume_tailor.tailor_resume import tailor_resume as _tailor_resume
from job_database import (
    get_resume_cache,
    set_resume_cache,
    get_user_resume_history,
    get_db,
    close_db,
    save_user_attribution,
    list_saved_jobs,
    get_saved_job_hashes,
    upsert_saved_job,
    update_saved_job,
    delete_saved_job,
)
from auth import require_user

# Base directory of this file (used for templates/static/uploads paths)
BASE_DIR = Path(__file__).resolve().parent

# Bump whenever a scoring/prompt change makes cached results stale.
# Old entries become misses automatically — no manual purge needed.
PROMPT_VERSION = "v2"


def _resume_cache_key(resume_hash, use_llm, categories):
    """Cache key for a resume's match results.

    Includes the selected department categories so changing the department
    filter is a DIFFERENT key -> cache miss -> a fresh search (instead of
    serving the previous selection's cached results). Sorted so selection order
    doesn't matter; 'all' when no filter is applied.
    """
    mode = 'deep' if use_llm else 'quick'
    catsig = 'all' if not categories else 'cat-' + '-'.join(sorted(categories))
    return f"{resume_hash}_{mode}_{catsig}_{PROMPT_VERSION}"

# Load environment variables
load_dotenv()

# Usage tracking master switch.
# When TRACK_USAGE is "true" (the default), weekly per-user quotas, slowapi
# rate limiting, and the per-upload cooldown are all enforced. Set it to
# "false" in development to disable every limit for unrestricted testing.
TRACK_USAGE = os.getenv("TRACK_USAGE", "true").strip().lower() == "true"
logger.info(f"Usage tracking (quotas + rate limits): {'ENABLED' if TRACK_USAGE else 'DISABLED'}")

# Hosted MCP endpoint (zero-install tier, /mcp). The mcp SDK needs Python
# >= 3.10; the dev venv is 3.9, so the import is guarded — the app boots
# without it and simply doesn't mount /mcp. Production (3.11) serves it.
try:
    import mcp_remote as _mcp_remote
    logger.info("Hosted MCP endpoint available — will mount at /mcp")
except ImportError as _mcp_err:
    _mcp_remote = None
    logger.warning(f"Hosted MCP endpoint disabled (mcp SDK unavailable): {_mcp_err}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown with a proper lifespan context."""
    # ---- startup ----
    environment = os.getenv("ENVIRONMENT", "development").lower()
    logger.info(f"Starting up Internship Matcher [{environment.upper()}] with Hybrid Cache System...")

    loop = asyncio.get_event_loop()
    cache_available = await loop.run_in_executor(None, job_cache.init_redis)

    if cache_available:
        # Check cache status without loading all jobs into memory
        cache_info = await loop.run_in_executor(None, job_cache.get_cache_info)
        should_refresh = False

        redis_info = cache_info.get('redis', {})
        db_info = cache_info.get('database', {})
        redis_job_count = redis_info.get('job_count', 0)
        db_active_jobs = db_info.get('active_jobs', 0)
        cache_has_jobs = redis_job_count > 0 or db_active_jobs > 0

        if environment == "development":
            if cache_has_jobs:
                last_update = db_info.get('last_update')
                if last_update:
                    from datetime import datetime, timedelta
                    try:
                        last_update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                        time_since_update = datetime.now(last_update_time.tzinfo) - last_update_time
                        if time_since_update > timedelta(hours=6):
                            logger.info(f"Cache is {time_since_update.total_seconds() / 3600:.1f} hours old — refreshing...")
                            should_refresh = True
                        else:
                            logger.info(f"Cache system ready: {db_active_jobs} jobs in DB, {redis_job_count} in Redis")
                    except Exception as e:
                        logger.warning(f"Error parsing cache timestamp: {e}")
                else:
                    logger.info(f"Cache system ready: {db_active_jobs} jobs in DB, {redis_job_count} in Redis")
            else:
                should_refresh = True
                logger.info("No cached jobs found — initializing cache...")
        else:
            # production AND staging: always scrape on startup so every deploy gets
            # fresh data. The scrape runs in the background — server available immediately.
            should_refresh = True
            if cache_has_jobs:
                logger.info(f"{environment.capitalize()} startup: {db_active_jobs} jobs in DB, scraping for fresh data...")
            else:
                logger.info(f"{environment.capitalize()} startup: no cached jobs — initializing cache...")

        if should_refresh and os.getenv("SKIP_STARTUP_SCRAPE", "").lower() in ("1", "true", "yes"):
            logger.info("SKIP_STARTUP_SCRAPE is set — skipping startup scrape")
            should_refresh = False

        if should_refresh:
            async def _background_scrape():
                try:
                    jobs = await scrape_jobs(max_days_old=30)
                    if jobs:
                        cache_result = job_cache.set_cached_jobs(jobs, cache_type='startup')
                        if cache_result.get('database_success') or cache_result.get('redis_success'):
                            logger.info(f"Startup cache initialized: {cache_result.get('new_jobs', 0)} new jobs, {len(jobs)} total")
                        else:
                            logger.warning("Cache initialization failed")
                    else:
                        logger.warning("No jobs scraped on startup")
                except Exception as e:
                    logger.error(f"Error during startup scraping: {e}")
            asyncio.create_task(_background_scrape())
            logger.info("Job scrape started in background — server starting immediately")
    else:
        logger.warning("Hybrid cache system unavailable — jobs will be scraped per request")

    try:
        final_info = await loop.run_in_executor(None, job_cache.get_cache_info)
        if final_info.get('database', {}).get('status') == 'active':
            db_info = final_info['database']
            logger.info(f"Database: {db_info.get('active_jobs', 0)} active jobs")
        if final_info.get('redis', {}).get('status') == 'active':
            redis_info = final_info['redis']
            logger.info(f"Redis: {redis_info.get('job_count', 0)} jobs cached")
    except Exception as e:
        logger.warning(f"Error getting final cache status: {e}")

    logger.info("Startup complete!")

    # Start background refresh task and track it for clean cancellation
    refresh_task = asyncio.create_task(daily_cache_refresh_task())
    logger.info("Daily cache refresh scheduler started")

    if _mcp_remote is not None:
        # FastAPI does not run a mounted sub-app's lifespan — the MCP
        # session manager must be started from the parent lifespan.
        # StreamableHTTPSessionManager has a one-shot _ran guard that raises
        # if .run() is called twice on the same instance. Test fixtures cycle
        # the lifespan multiple times per process, so reset _ran before each
        # run. In production the lifespan only runs once — harmless there.
        sm = _mcp_remote.remote_mcp.session_manager
        sm._has_started = False  # allow re-run when lifespan cycles in tests
        async with sm.run():
            yield  # server is running
    else:
        yield  # server is running

    # ---- shutdown ----
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Rate limiting setup
# ---------------------------------------------------------------------------

def _get_rate_limit_key(request: Request) -> str:
    """
    Rate-limit by Clerk user_id when the request carries a valid Bearer token,
    falling back to client IP. This prevents shared IPs (campus / office NAT)
    from exhausting each other's quotas.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            import jwt as _jwt
            payload = _jwt.decode(
                auth[7:], options={"verify_signature": False}
            )
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    return f"ip:{request.client.host if request.client else 'unknown'}"


_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
# enabled=TRACK_USAGE — when usage tracking is off, every @limiter.limit(...)
# decorator becomes a no-op, removing all rate limiting / waiting times.
limiter = Limiter(key_func=_get_rate_limit_key, storage_uri=_REDIS_URL, enabled=TRACK_USAGE)

# Global concurrency gate — prevents OOM from simultaneous LLM calls.
# Railway hobby tier has ~512 MB RAM; each analysis can use 100–200 MB.
# Two concurrent analyses is the safe maximum.
LLM_SEMAPHORE = asyncio.Semaphore(2)

# Create FastAPI app
app = FastAPI(title="Internship Matcher", version="1.0.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter

def _log_rate_limit_exceeded(request: Request, exc: RateLimitExceeded):
    logger.warning(
        "Rate limit exceeded — limit=%s endpoint=%s key=%s",
        exc.limit.limit,
        request.url.path,
        _get_rate_limit_key(request),
    )
    return _rate_limit_exceeded_handler(request, exc)

app.add_exception_handler(RateLimitExceeded, _log_rate_limit_exceeded)

# Add CORS middleware for React frontend
_CORS_ORIGINS = [
    "https://internship-app-production.up.railway.app",
    "https://internshipmatcher.com",
    "https://www.internshipmatcher.com",
    "http://internshipmatcher.com",
    "http://www.internshipmatcher.com",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]
if _ENVIRONMENT == "staging":
    _CORS_ORIGINS.append("https://internship-app-staging.up.railway.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # Important for SSE streaming
)

# Add session middleware for basic session support
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-secret-key-here"))

_INTERNSHIP_MATCHER_API_KEY = os.getenv("INTERNSHIP_MATCHER_API_KEY")

async def require_api_key(x_api_key: str = Header(None)):
    if not _INTERNSHIP_MATCHER_API_KEY or x_api_key != _INTERNSHIP_MATCHER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# Setup templates and static files using absolute paths
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Serve React frontend build (if it exists)
FRONTEND_BUILD = BASE_DIR / "frontend" / "build"
if FRONTEND_BUILD.exists():
    # Mount React's built static assets at /static so index.html asset paths resolve correctly
    app.mount("/static", StaticFiles(directory=str(FRONTEND_BUILD / "static")), name="static")
else:
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Create upload folder if it doesn't exist (absolute path)
UPLOAD_FOLDER = BASE_DIR / "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------------------------
# MCP /api/v1 surface (per-user API keys) + /developer key CRUD (Clerk auth).
# v1_app is a sub-app so its OpenAPI contract is published at
# /api/v1/openapi.json even though the main app's docs are disabled.
# NO Claude calls live behind these routes — see mcp_api.py.
# ---------------------------------------------------------------------------
from mcp_api import v1_app as _mcp_v1_app, developer_router as _developer_router
app.mount("/api/v1", _mcp_v1_app)
app.include_router(_developer_router)

# Hosted MCP (zero-install tier): /mcp — guarded above for Python < 3.10
if _mcp_remote is not None:
    app.mount("/mcp", _mcp_remote.streamable_app())

    class _McpSlashRewrite:
        """Map /mcp -> /mcp/ at the ASGI layer. Starlette's Mount answers the
        bare path with a 307, but MCP clients POST and won't follow it —
        users paste '/mcp' without a trailing slash."""
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope.get("type") == "http" and scope.get("path") == "/mcp":
                scope = dict(scope)
                scope["path"] = "/mcp/"
                scope["raw_path"] = b"/mcp/"
            await self.app(scope, receive, send)

    app.add_middleware(_McpSlashRewrite)



async def daily_cache_refresh_task():
    """
    Background task that automatically refreshes the cache every 24 hours.
    This ensures jobs stay fresh without manual intervention.

    IMPROVED: Better error handling, logging, and recovery
    """
    refresh_count = 0

    while True:
        try:
            # Wait 24 hours before first refresh (cache was just initialized on startup)
            logger.info("[Scheduled] Next cache refresh in 24 hours...")
            await asyncio.sleep(24 * 60 * 60)  # 24 hours in seconds

            refresh_count += 1
            logger.info(f"[Scheduled #{refresh_count}] Starting daily cache refresh")

            # Step 1: Scrape fresh jobs and persist to database
            try:
                jobs = await scrape_jobs(max_days_old=30)
            except Exception as scrape_error:
                logger.error(f"[Scheduled] Scraping failed: {scrape_error}")
                import traceback
                traceback.print_exc()
                continue  # Don't stop the task, try again in 24h

            if jobs:
                # Persist scraped jobs to the database (deduplication happens here)
                try:
                    cache_result = job_cache.set_cached_jobs(jobs, cache_type='daily_scheduled')
                    new_jobs = cache_result.get('new_jobs', 0)

                    if cache_result.get('database_success'):
                        logger.info(f"[Scheduled #{refresh_count}] Database updated: {new_jobs} new jobs")
                    else:
                        logger.warning(f"[Scheduled #{refresh_count}] Database update failed")
                except Exception as cache_error:
                    logger.error(f"[Scheduled #{refresh_count}] Cache storage failed: {cache_error}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.info(f"[Scheduled #{refresh_count}] No new jobs scraped")

            # Step 2: Refresh Redis from database in chunks (memory-efficient)
            try:
                loop = asyncio.get_event_loop()
                total_cached = await loop.run_in_executor(
                    None, job_cache.refresh_redis_from_database
                )
                logger.info(
                    f"[Scheduled #{refresh_count}] Daily refresh complete: "
                    f"{total_cached} jobs now in Redis"
                )
            except Exception as redis_error:
                logger.error(f"[Scheduled #{refresh_count}] Redis refresh failed: {redis_error}")

        except asyncio.CancelledError:
            logger.info(f"[Scheduled] Daily cache refresh task cancelled after {refresh_count} refreshes")
            break
        except Exception as e:
            logger.error(f"[Scheduled #{refresh_count}] Unexpected error in daily cache refresh: {e}")
            import traceback
            traceback.print_exc()
            continue


async def get_jobs_with_cache():
    """
    Get jobs using hybrid cache system (Redis + Database).
    This function is used by all endpoints to get job data efficiently.

    On a Redis hit the list is read back from the list key.
    On a cache miss, jobs are fetched from the database in 500-job pages
    rather than loading the entire dataset at once, keeping peak memory low.
    """
    # Try to get from hybrid cache system (Redis list or DB paginated)
    cached_jobs = job_cache.get_cached_jobs()

    if cached_jobs:
        logger.info(f"Using {len(cached_jobs)} jobs from hybrid cache")
        return cached_jobs

    # Cache miss — scrape fresh jobs, persist, then stream to Redis in chunks
    logger.info("Cache miss — scraping fresh jobs...")
    try:
        jobs = await scrape_jobs(max_days_old=30)

        if jobs:
            cache_result = job_cache.set_cached_jobs(jobs, cache_type='on_demand')
            new_jobs = cache_result.get('new_jobs', 0)

            if cache_result.get('database_success') or cache_result.get('redis_success'):
                logger.info(f"Scraped and cached: {new_jobs} new jobs")
            else:
                logger.warning("Scraping successful but caching failed")

            # get_cached_jobs() will read from Redis list or DB pages
            return job_cache.get_cached_jobs() or jobs
        else:
            logger.warning("No jobs scraped")
            return []

    except Exception as e:
        logger.error(f"Error during smart scraping: {e}")
        try:
            from job_cache import get_jobs_for_matching
            fallback_jobs = get_jobs_for_matching()
            if fallback_jobs:
                logger.info(f"Using {len(fallback_jobs)} fallback jobs from database")
                return fallback_jobs
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")

        return []


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def index():
    """Serve React frontend"""
    index_file = FRONTEND_BUILD / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard - main page for resume upload"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "results": None,
        "error": None
    })


@app.post("/match", response_class=HTMLResponse)
async def match_resume(request: Request, resume: UploadFile = File(...)):
    """Match resume to internship opportunities"""
    try:
        # Validate file
        if not resume:
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": "No file was uploaded. Please select a resume file."
            })

        # Check file extension
        file_extension = resume.filename.split('.')[-1].lower() if resume.filename else ''
        allowed_extensions = ['pdf', 'png', 'jpg', 'jpeg']
        
        if file_extension not in allowed_extensions:
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Invalid file type '{file_extension}'. Please upload a PDF, PNG, JPG, or JPEG file."
            })

        # Read file content
        try:
            file_content = await resume.read()
            if not file_content:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "The uploaded file appears to be empty. Please upload a valid resume file."
                })
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error reading the uploaded file: {str(e)}"
            })

        logger.info(f"Upload: {resume.filename} ({len(file_content)} bytes, {resume.content_type})")

        # Parse resume using LLM (returns skills, text, and metadata)
        try:
            resume_skills, resume_text, resume_metadata = parse_resume(file_content, resume.filename)
            if not resume_skills:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "No skills were detected in your resume. Please make sure your resume includes technical skills, programming languages, or relevant experience."
                })
        except Exception as e:
            logger.error(f"Error parsing resume: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error parsing your resume: {str(e)}"
            })

        logger.info(f"Resume: {len(resume_skills)} skills, {resume_metadata.get('experience_level', 'unknown')} level")

        # Validate resume content
        if resume_text and not is_valid_resume(resume_text):
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": "The uploaded file does not appear to be a valid resume. Please upload a document that contains relevant professional information."
            })

        # Get jobs from cache or scrape
        try:
            jobs = await get_jobs_with_cache()
            if not jobs:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "Unable to fetch internship opportunities at this time. Please try again later."
                })
        except Exception as e:
            logger.error(f"Error fetching jobs: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error fetching internship opportunities: {str(e)}"
            })

        # Match resume to jobs
        try:
            matched_jobs = match_resume_to_jobs(resume_skills, jobs, resume_text)
            if not matched_jobs:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "No matching internship opportunities were found for your skills. Consider updating your resume with more relevant technical skills."
                })
            logger.info(f"Matched {len(matched_jobs)} jobs")
        except Exception as e:
            logger.error(f"Error matching jobs: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error matching your resume to jobs: {str(e)}"
            })

        # Return results
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "results": matched_jobs,
            "user": None
        })

    except Exception as e:
        logger.error(f"Unexpected error in match_resume: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "results": None,
            "error": f"An unexpected error occurred: {str(e)}. Please try again or contact support if the problem persists."
        })


@app.post("/api/match")
@limiter.limit("3/10minutes")
async def api_match_resume(request: Request, resume: UploadFile = File(...), think_deeper: str = Form("true"), categories: str = Form(default="")):
    """API endpoint for React frontend - returns JSON instead of HTML"""
    selected_categories = _parse_categories(categories)
    try:
        # Validate file
        if not resume:
            raise HTTPException(status_code=400, detail="No file was uploaded. Please select a resume file.")

        # Check file extension
        file_extension = resume.filename.split('.')[-1].lower() if resume.filename else ''
        allowed_extensions = ['pdf', 'png', 'jpg', 'jpeg']
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type '{file_extension}'. Please upload a PDF, PNG, JPG, or JPEG file."
            )

        # Read file content
        try:
            file_content = await resume.read()
            if not file_content:
                raise HTTPException(status_code=400, detail="The uploaded file appears to be empty. Please upload a valid resume file.")
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            raise HTTPException(status_code=400, detail=f"Error reading the uploaded file: {str(e)}")

        logger.info(f"Upload: {resume.filename} ({len(file_content)} bytes, {resume.content_type})")

        # Upload file to S3
        s3_key = None
        try:
            s3_key = upload_resume_to_s3(file_content, resume.filename)
            logger.info(f"S3: uploaded {resume.filename} as {s3_key}")
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to upload resume: {str(e)}")

        # Download file from S3 for processing
        try:
            downloaded_content, original_filename = download_resume_from_s3(s3_key)
        except Exception as e:
            logger.error(f"S3 download failed: {e}")
            if s3_key:
                delete_resume_from_s3(s3_key)
            raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")

        # Parse resume using selected method (returns skills, text, and metadata)
        _req_user_id = None
        try:
            use_llm = think_deeper.lower() == "true"

            # Think Deeper requires authentication — propagate 401 for unauthenticated callers
            if use_llm:
                _req_user_id = await require_user(request)
                if TRACK_USAGE:
                    from quota import get_think_deeper_quota_status, WEEKLY_THINK_DEEPER_LIMIT
                    _qdb = get_db()
                    try:
                        _qstatus = get_think_deeper_quota_status(_qdb, _req_user_id)
                        if _qstatus["remaining"] <= 0:
                            raise HTTPException(
                                status_code=429,
                                detail={
                                    "error": "weekly_quota_exceeded",
                                    "message": f"You've used all {WEEKLY_THINK_DEEPER_LIMIT} Think Deeper analyses this week.",
                                    "limit": _qstatus["limit"],
                                    "used": _qstatus["used"],
                                    "remaining": 0,
                                    "reset_at": _qstatus["reset_at"].isoformat() if _qstatus["reset_at"] else None,
                                },
                            )
                    finally:
                        close_db(_qdb)

            resume_skills, resume_text, resume_metadata = parse_resume(downloaded_content, original_filename, use_llm)
            if not resume_skills:
                raise HTTPException(
                    status_code=400,
                    detail="No skills were detected in your resume. Please make sure your resume includes technical skills, programming languages, or relevant experience."
                )
        except Exception as e:
            logger.error(f"Error parsing resume: {e}")
            raise HTTPException(status_code=400, detail=f"Error parsing your resume: {str(e)}")

        logger.info(f"Resume: {len(resume_skills)} skills, {resume_metadata.get('experience_level', 'unknown')} level")

        # Validate resume content
        if resume_text and not is_valid_resume(resume_text):
            raise HTTPException(
                status_code=400,
                detail="The uploaded file does not appear to be a valid resume. Please upload a document that contains relevant professional information."
            )

        # Get jobs from cache or scrape
        try:
            jobs = await get_jobs_with_cache()
            if not jobs:
                raise HTTPException(
                    status_code=500,
                    detail="Unable to fetch internship opportunities at this time. Please try again later."
                )
        except Exception as e:
            logger.error(f"Error fetching jobs: {e}")
            raise HTTPException(status_code=500, detail=f"Error fetching internship opportunities: {str(e)}")

        # Match resume to jobs with intelligent prefiltering
        try:
            matched_jobs = match_resume_to_jobs(resume_skills, jobs, resume_text, use_llm=use_llm, categories=selected_categories)
            logger.info(f"Matched {len(matched_jobs)} jobs from {len(jobs)} total")

            # Filter jobs with score > 0 for the final response
            jobs_with_matches = [job for job in matched_jobs if job.get('match_score', 0) > 0]

            if not jobs_with_matches:
                logger.warning(f"No jobs with score > 0 out of {len(matched_jobs)} matched")
                
                return JSONResponse(content={
                    "success": True,
                    "message": "No matching internship opportunities were found for your skills. Consider updating your resume with more relevant technical skills.",
                    "jobs": matched_jobs[:5],  # Return jobs with scores for debugging
                    "skills_found": resume_skills,
                    "debug_info": {
                        "total_jobs_scraped": len(jobs),
                        "jobs_processed": len(matched_jobs),

                        "skills_extracted": len(resume_skills),
                        "all_job_scores": [{"company": job.get('company'), "title": job.get('title'), "score": job.get('match_score', 0)} for job in matched_jobs[:5]]
                    }
                })
            
            # Use jobs with matches for the success response
            matched_jobs = jobs_with_matches

            # Record Think Deeper usage after a successful deep match
            if TRACK_USAGE and use_llm and _req_user_id:
                try:
                    from quota import record_think_deeper_request
                    _rdb = get_db()
                    try:
                        record_think_deeper_request(_rdb, _req_user_id)
                        _rdb.commit()
                    except Exception as _re:
                        logger.warning(f"Failed to record think_deeper quota for user={_req_user_id}: {_re}")
                        _rdb.rollback()
                    finally:
                        close_db(_rdb)
                except Exception as _re:
                    logger.warning(f"Think Deeper quota recording import error: {_re}")

        except Exception as e:
            logger.error(f"Error matching jobs: {e}")
            raise HTTPException(status_code=500, detail=f"Error matching your resume to jobs: {str(e)}")

        # Clean up S3 file after processing
        if s3_key:
            try:
                delete_resume_from_s3(s3_key)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up S3 file {s3_key}: {cleanup_error}")

        # Return JSON response for React frontend
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(matched_jobs)} matching opportunities!",
            "jobs": matched_jobs,
            "skills_found": resume_skills
        })

    except HTTPException:
        if 's3_key' in locals() and s3_key:
            try:
                delete_resume_from_s3(s3_key)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up S3 file {s3_key}: {cleanup_error}")
        raise
    except Exception as e:
        if 's3_key' in locals() and s3_key:
            try:
                delete_resume_from_s3(s3_key)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up S3 file {s3_key}: {cleanup_error}")

        logger.error(f"Unexpected error in api_match_resume: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}. Please try again or contact support if the problem persists."
        )


@app.get("/api/resume-cache/{resume_hash}")
@limiter.limit("20/minute")
async def check_resume_cache(request: Request, resume_hash: str, user_id: str = Depends(require_user), think_deeper: str = Query("true"), categories: str = Query("")):
    use_llm = think_deeper.lower() == "true"
    cache_key = _resume_cache_key(resume_hash, use_llm, _parse_categories(categories))
    cached = get_resume_cache(user_id, cache_key)
    if cached:
        return JSONResponse({"hit": True, "results": cached["results"], "skills": cached["skills"]})
    return JSONResponse({"hit": False})


@app.get("/api/user-history")
@limiter.limit("20/minute")
async def get_user_history(request: Request, user_id: str = Depends(require_user)):
    entries = get_user_resume_history(user_id)
    return JSONResponse(entries)


@app.get("/api/saved-jobs")
@limiter.limit("60/minute")
async def api_list_saved_jobs(request: Request, hashes_only: bool = Query(False), user_id: str = Depends(require_user)):
    if hashes_only:
        return JSONResponse({"job_hashes": get_saved_job_hashes(user_id)})
    return JSONResponse(list_saved_jobs(user_id))


@app.post("/api/saved-jobs")
@limiter.limit("60/minute")
async def api_save_job(request: Request, user_id: str = Depends(require_user)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    job_hash = (body.get("job_hash") or "").strip()
    if not job_hash:
        raise HTTPException(status_code=400, detail="job_hash is required")
    try:
        saved = upsert_saved_job(
            user_id=user_id,
            job_hash=job_hash,
            status=body.get("status") or "saved",
            notes=body.get("notes") or "",
            deadline=body.get("deadline") or None,
            job_snapshot=body.get("job_snapshot") or body.get("job") or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(saved, status_code=201)


@app.patch("/api/saved-jobs/{job_hash}")
@limiter.limit("60/minute")
async def api_update_saved_job(job_hash: str, request: Request, user_id: str = Depends(require_user)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        saved = update_saved_job(
            user_id=user_id,
            job_hash=job_hash,
            status=body.get("status"),
            notes=body.get("notes"),
            deadline=body.get("deadline"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not saved:
        raise HTTPException(status_code=404, detail="Saved job not found")
    return JSONResponse(saved)


@app.delete("/api/saved-jobs/{job_hash}")
@limiter.limit("60/minute")
async def api_delete_saved_job(job_hash: str, request: Request, user_id: str = Depends(require_user)):
    deleted = delete_saved_job(user_id, job_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved job not found")
    return JSONResponse({"ok": True})


@app.post("/api/track-attribution")
async def track_attribution(request: Request, user_id: str = Depends(require_user)):
    """Record first-touch UTM attribution for a signed-in user. Idempotent."""
    try:
        body = await request.json()
    except Exception as e:
        logger.warning(f"Attribution: could not parse request body for user={user_id} — {e}")
        body = {}
    saved = save_user_attribution(user_id, body)
    logger.info(f"Attribution: track-attribution user={user_id} saved={saved}")
    return JSONResponse({"ok": True})


@app.post("/api/match-stream")
@limiter.limit("3/10minutes")
async def stream_match_resume(
    request: Request,
    resume: UploadFile = File(...),
    think_deeper: str = Form("true"),
    resume_hash: str = Form(default=""),
    categories: str = Form(default=""),
    user_id: str = Depends(require_user),
):
    """Streaming endpoint that provides real-time progress updates"""
    # Department/category filter selected on the upload page (empty => all jobs).
    selected_categories = _parse_categories(categories)
    
    # IMPORTANT: Read all file data BEFORE the generator function
    # to avoid "i/o operation on closed file" errors
    try:
        # Validate file
        if not resume:
            async def error_response():
                yield {"data": json.dumps({'error': 'No file was uploaded'})}
            return EventSourceResponse(error_response())

        file_extension = resume.filename.split('.')[-1].lower() if resume.filename else ''
        allowed_extensions = ['pdf', 'png', 'jpg', 'jpeg']
        
        if file_extension not in allowed_extensions:
            async def error_response():
                yield {"data": json.dumps({'error': f'Invalid file type: {file_extension}'})}
            return EventSourceResponse(error_response())

        # Read file content ONCE, before the generator
        file_content = await resume.read()
        filename = resume.filename
        content_type = resume.content_type

        if not file_content:
            async def error_response():
                yield {"data": json.dumps({'error': 'Empty file uploaded'})}
            return EventSourceResponse(error_response())

        # Check resume cache before doing S3 upload or any LLM work
        if user_id and resume_hash:
            try:
                use_llm_early = think_deeper.lower() == "true"
                cache_key_early = _resume_cache_key(resume_hash, use_llm_early, selected_categories)
                cached_early = get_resume_cache(user_id, cache_key_early)
                if cached_early:
                    logger.info(f"Cache hit before S3 upload for user {user_id}, returning early")
                    cached_results = cached_early['results']
                    cached_skills = cached_early['skills']
                    async def cached_response():
                        yield f"data: {json.dumps({'step': 0, 'message': 'Connection established, starting analysis...', 'progress': 5})}\n\n"
                        await asyncio.sleep(0.01)
                        yield f"data: {json.dumps({'step': 1, 'message': 'Found cached results!', 'final_results': cached_results, 'matches_found': len([j for j in cached_results if j.get('match_score', 0) > 0]), 'total_results': len(cached_results), 'progress': 100, 'complete': True, 'from_cache': True})}\n\n"
                    return EventSourceResponse(cached_response())
            except Exception as cache_err:
                logger.warning(f"Pre-S3 cache check failed, proceeding normally: {cache_err}")

        # Enforce Think Deeper weekly quota (only when no cache hit + user authenticated)
        if TRACK_USAGE and user_id and think_deeper.lower() == "true":
            from quota import get_think_deeper_quota_status, WEEKLY_THINK_DEEPER_LIMIT
            _qdb = get_db()
            try:
                _qstatus = get_think_deeper_quota_status(_qdb, user_id)
                if _qstatus["remaining"] <= 0:
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "weekly_quota_exceeded",
                            "message": f"You've used all {WEEKLY_THINK_DEEPER_LIMIT} Think Deeper analyses this week.",
                            "limit": _qstatus["limit"],
                            "used": _qstatus["used"],
                            "remaining": 0,
                            "reset_at": _qstatus["reset_at"].isoformat() if _qstatus["reset_at"] else None,
                        },
                    )
            finally:
                close_db(_qdb)

        # Upload file to S3 ONCE, before the generator
        try:
            s3_key = upload_resume_to_s3(file_content, filename)
            logger.info(f"Stream: uploaded {filename} to S3 as {s3_key}")
        except Exception as e:
            logger.error(f"Stream: S3 upload failed: {e}")
            error_msg = str(e)
            async def error_response():
                yield {"data": json.dumps({'error': f'S3 upload failed: {error_msg}'})}
            return EventSourceResponse(error_response())
    except Exception as e:
        error_msg = str(e)
        async def error_response():
            yield {"data": json.dumps({'error': f'File upload error: {error_msg}'})}
        return EventSourceResponse(error_response())
    
    async def generate_progress():
        # Acquire the global LLM semaphore — this is the key protection against OOM
        # on Railway's 512 MB hobby container. If 2 analyses are already running,
        # new requests wait at most 5 seconds then yield a "server busy" event.
        try:
            acquired = await asyncio.wait_for(LLM_SEMAPHORE.acquire(), timeout=5.0)
        except asyncio.TimeoutError:
            yield {"data": json.dumps({
                "error": "Server is busy processing other requests. Please try again in 30 seconds."
            })}
            return

        try:
            import time as _time
            _request_start = _time.monotonic()
            logger.info("SSE generator started (semaphore acquired)")

            # Send immediate "connected" event to establish the stream
            yield f"data: {json.dumps({'step': 0, 'message': 'Connection established, starting analysis...', 'progress': 5})}\n\n"
            await asyncio.sleep(0.01)  # Tiny delay to flush
            
            # Convert think_deeper parameter to boolean
            use_llm = think_deeper.lower() == "true"

            # Track current step and progress for dynamic updates
            current_step = [0]  # Use list to allow modification in nested function
            progress_queue = asyncio.Queue()  # Async queue for real-time progress messages
            loop = asyncio.get_running_loop()  # Get RUNNING event loop for thread-safe operations (critical for async generators)

            def progress_callback(message):
                """Thread-safe callback function to queue progress messages"""
                current_step[0] += 1
                # Calculate progress percentage based on step and mode
                if use_llm:
                    # Deep Thinking Mode: More granular steps (up to 10+ steps)
                    progress_map = {
                        "Extracting text from resume...": 20,
                        "Analyzing resume with AI...": 30,
                        "Pre-filtering top candidates for you...": 60,
                        "Running AI career analysis": 70,  # Batch messages start here
                        "Enhancing results with career insights...": 90,
                    }
                else:
                    # Quick Mode: Fewer steps (7 total)
                    progress_map = {
                        "Extracting text from resume...": 20,
                        "Analyzing resume with AI...": 30,
                        "Matching jobs with keyword analysis...": 70,
                    }

                # Find matching progress or default
                progress = 50  # Default
                for key, value in progress_map.items():
                    if key in message:
                        progress = value
                        # For batch messages, calculate incremental progress
                        if "batch" in message and "of" in message:
                            try:
                                # Extract "batch X of Y" and calculate progress
                                parts = message.split("batch")[-1].strip()
                                batch_info = parts.split("of")
                                current_batch = int(batch_info[0].strip().split()[0])
                                total_batches = int(batch_info[1].strip().split()[0])
                                # Progress from 70% to 85% across batches
                                batch_progress = 70 + int((current_batch / total_batches) * 15)
                                progress = batch_progress
                            except:
                                pass
                        break

                # Thread-safe queue put (works from worker threads)
                asyncio.run_coroutine_threadsafe(
                    progress_queue.put({'step': current_step[0], 'message': message, 'progress': progress}),
                    loop
                )

            yield f"data: {json.dumps({'step': 1, 'message': 'Uploading resume to secure storage...', 'progress': 10})}\n\n"
            await asyncio.sleep(0.05)  # Small delay to ensure SSE flushes to client

            # Download file from S3 for processing
            try:
                downloaded_content, original_filename = download_resume_from_s3(s3_key)
            except Exception as e:
                yield f"data: {json.dumps({'error': f'S3 download failed: {str(e)}'})}\n\n"
                return

            # Step 2: Extract text (no LLM) + load jobs concurrently
            current_step[0] = 1

            # Kick off job loading immediately while we extract text
            jobs_task = asyncio.create_task(get_jobs_with_cache())

            try:
                text_task = asyncio.create_task(
                    asyncio.to_thread(
                        extract_text_only,
                        downloaded_content,
                        original_filename,
                        progress_callback
                    )
                )

                while not text_task.done():
                    try:
                        progress_msg = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                        yield f"data: {json.dumps(progress_msg)}\n\n"
                        await asyncio.sleep(0.02)
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0)
                        continue

                resume_text = await text_task

                if not resume_text.strip():
                    jobs_task.cancel()
                    yield f"data: {json.dumps({'error': 'No text could be extracted from the resume'})}\n\n"
                    try:
                        delete_resume_from_s3(s3_key)
                    except:
                        pass
                    return

            except Exception as e:
                jobs_task.cancel()
                yield f"data: {json.dumps({'error': f'Resume text extraction failed: {str(e)}'})}\n\n"
                try:
                    delete_resume_from_s3(s3_key)
                except:
                    pass
                return

            # Step 3: Await job loading (likely already done since it ran in parallel)
            current_step[0] += 1
            yield f"data: {json.dumps({'step': current_step[0], 'message': 'Loading internship opportunities...', 'progress': 30})}\n\n"
            await asyncio.sleep(0.05)

            try:
                jobs = await jobs_task
                if not jobs:
                    yield f"data: {json.dumps({'error': 'No jobs found'})}\n\n"
                    try:
                        delete_resume_from_s3(s3_key)
                    except:
                        pass
                    return
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Job loading failed: {str(e)}'})}\n\n"
                try:
                    delete_resume_from_s3(s3_key)
                except:
                    pass
                return

            # Step 4: Single combined LLM call — skills extraction + job matching
            current_step[0] += 1
            yield f"data: {json.dumps({'step': current_step[0], 'message': 'Analyzing resume and matching jobs...', 'progress': 40})}\n\n"
            await asyncio.sleep(0.05)

            try:
                if use_llm:
                    analysis_task = asyncio.create_task(
                        asyncio.to_thread(
                            analyze_and_match_single_call,
                            resume_text,
                            jobs,
                            progress_callback,
                            categories=selected_categories,
                        )
                    )

                    while not analysis_task.done():
                        try:
                            progress_msg = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                            yield f"data: {json.dumps(progress_msg)}\n\n"
                            await asyncio.sleep(0.02)
                        except asyncio.TimeoutError:
                            await asyncio.sleep(0)
                            continue

                    resume_skills, resume_metadata, matched_jobs = await analysis_task

                    # Drain remaining progress messages
                    while not progress_queue.empty():
                        try:
                            progress_msg = progress_queue.get_nowait()
                            yield f"data: {json.dumps(progress_msg)}\n\n"
                            await asyncio.sleep(0.02)
                        except asyncio.QueueEmpty:
                            break
                else:
                    # Quick mode: fast keyword matching with Haiku skills, no heavy Sonnet LLM
                    from matching.matcher import simple_keyword_match, _extract_resume_profile_haiku
                    
                    if progress_callback:
                        progress_callback("Extracting profile with AI...")
                        
                    profile = await asyncio.to_thread(_extract_resume_profile_haiku, resume_text)
                    resume_skills = profile.get("skills", [])
                    resume_metadata = {
                        "experience_level": profile.get("experience_level", "student"),
                        "years_of_experience": profile.get("years_of_experience", 0),
                        "is_student": profile.get("experience_level", "student") == "student",
                    }
                    
                    matched_jobs = await asyncio.to_thread(
                        simple_keyword_match, resume_skills, jobs, resume_text, progress_callback,
                        categories=selected_categories,
                    )

                if resume_skills:
                    current_step[0] += 1
                    yield f"data: {json.dumps({'step': current_step[0], 'message': f'Found {len(resume_skills)} skills in your resume', 'skills': resume_skills, 'progress': 80})}\n\n"
                    await asyncio.sleep(0.05)

                # Convert to format expected by frontend
                formatted_jobs = []
                for job in matched_jobs:
                    first_seen = job.get('first_seen')
                    last_seen = job.get('last_seen')

                    def _to_utc_iso(ts):
                        if not ts:
                            return None
                        if hasattr(ts, 'isoformat'):
                            # Naive datetime from DB — mark as UTC so JS parses correctly
                            return ts.isoformat() + 'Z'
                        if isinstance(ts, str):
                            # String from Redis/cache — normalize to proper UTC ISO
                            if not ts.endswith('Z') and '+' not in ts:
                                ts = ts.replace(' ', 'T') + 'Z'
                            return ts
                        return str(ts)

                    first_seen = _to_utc_iso(first_seen)
                    last_seen = _to_utc_iso(last_seen)

                    formatted_jobs.append({
                        'job_hash': job.get('job_hash'),
                        'company': job.get('company', 'Unknown'),
                        'title': job.get('title', 'Unknown'),
                        'location': job.get('location', 'Unknown'),
                        'apply_link': job.get('apply_link', '#'),
                        'match_score': job.get('match_score', 0),
                        'match_description': job.get('match_description', ''),
                        'ai_reasoning': job.get('ai_reasoning'),
                        'required_skills': job.get('required_skills', []),
                        'first_seen': first_seen,
                        'last_seen': last_seen
                    })

                jobs_with_matches = [job for job in formatted_jobs if job['match_score'] > 0]
                final_results = formatted_jobs if use_llm else formatted_jobs[:50]

                completion_message = (
                    f'Analysis complete! Found {len(jobs_with_matches)} matches out of {len(final_results)} jobs analyzed.'
                    if use_llm else
                    f'Quick matching complete! Found {len(jobs_with_matches)} matching jobs.'
                )

                # Clean up S3 file after successful processing
                try:
                    delete_resume_from_s3(s3_key)
                except Exception as cleanup_error:
                    logger.warning(f"Stream: Failed to clean up S3 file {s3_key}: {cleanup_error}")

                # Save to resume cache if user is authenticated
                if user_id and resume_hash:
                    try:
                        save_cache_key = _resume_cache_key(resume_hash, use_llm, selected_categories)
                        set_resume_cache(user_id, save_cache_key, final_results, resume_skills)
                        logger.info(f"Saved results to resume cache for user {user_id}")
                    except Exception as cache_err:
                        logger.warning(f"Failed to save resume cache: {cache_err}")

                # Record Think Deeper usage after a successful deep match (never on cache hits)
                if TRACK_USAGE and user_id and use_llm:
                    try:
                        from quota import record_think_deeper_request
                        _rdb = get_db()
                        try:
                            record_think_deeper_request(_rdb, user_id, resume_hash or None)
                            _rdb.commit()
                        except Exception as _re:
                            logger.warning(f"Failed to record think_deeper quota for user={user_id}: {_re}")
                            _rdb.rollback()
                        finally:
                            close_db(_rdb)
                    except Exception as _re:
                        logger.warning(f"Think Deeper quota recording import error: {_re}")

                current_step[0] += 1
                _elapsed = _time.monotonic() - _request_start
                logger.info(f"Request completed in {_elapsed:.2f}s — {len(jobs_with_matches)} matches")
                yield f"data: {json.dumps({'step': current_step[0], 'message': completion_message, 'final_results': final_results, 'matches_found': len(jobs_with_matches), 'total_results': len(final_results), 'progress': 100, 'complete': True})}\n\n"
                await asyncio.sleep(0.05)

            except Exception as e:
                _elapsed = _time.monotonic() - _request_start
                logger.error(f"Error in job matching after {_elapsed:.2f}s: {e}")
                try:
                    delete_resume_from_s3(s3_key)
                except:
                    pass
                yield f"data: {json.dumps({'error': f'Job matching failed: {str(e)}'})}\n\n"

        except Exception as e:
            _elapsed = _time.monotonic() - _request_start
            logger.error(f"Unexpected error after {_elapsed:.2f}s: {e}")
            try:
                delete_resume_from_s3(s3_key)
            except Exception as cleanup_error:
                logger.warning(f"Stream: Failed to clean up S3 file {s3_key}: {cleanup_error}")
            
            yield f"data: {json.dumps({'error': f'Unexpected error: {str(e)}'})}\n\n"
        finally:
            LLM_SEMAPHORE.release()
            logger.info("SSE generator finished (semaphore released)")

    async def sse_generator():
        """Wrapper generator that converts string yields to proper SSE format for EventSourceResponse"""
        async for event in generate_progress():
            # EventSourceResponse expects dicts with 'data' key, not raw strings
            # Extract the JSON from "data: {...}\n\n" format
            if event.startswith("data: "):
                json_str = event[6:].strip()  # Remove "data: " prefix and trailing newlines
                if json_str:
                    yield {"data": json_str}
    
    return EventSourceResponse(
        sse_generator(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Pragma": "no-cache",
            "Expires": "0",
        },
        ping=5,  # Send ping every 5 seconds to keep connection alive
    )


@app.get("/api/cache-status")
@limiter.limit("10/minute")
async def cache_status(request: Request, _: None = Depends(require_api_key)):
    """Get comprehensive hybrid cache status and information"""
    cache_info = job_cache.get_cache_info()
    
    return JSONResponse({
        "hybrid_cache": cache_info,
        "redis_available": job_cache.is_redis_available(),
        "database_available": job_cache.is_database_available(),
        "cache_system": "hybrid_redis_database",
        "redis_ttl_hours": job_cache.CACHE_TTL / 3600,
        "features": {
            "incremental_scraping": True,
            "job_deduplication": True,
            "persistent_storage": True,
            "automatic_cleanup": True
        }
    })


@app.get("/api/test-matching")
async def test_matching():
    """Debug endpoint to test matching system with sample data"""
    try:
        # Sample test data
        resume_skills = ["Python", "JavaScript", "React"]
        resume_text = "Computer Science student with web development experience"
        
        sample_jobs = [
            {
                "title": "Software Engineer Intern",
                "company": "TestCorp",
                "description": "Python and JavaScript development",
                "location": "San Francisco, CA",
                "apply_link": "https://example.com/apply",
                "required_skills": []
            }
        ]
        
        # Test matching
        matched_jobs = match_resume_to_jobs(resume_skills, sample_jobs, resume_text)
        
        # Format for frontend
        formatted_jobs = []
        for job in matched_jobs:
            job_result = {
                'company': job.get('company', 'Unknown'),
                'title': job.get('title', 'Unknown'),
                'location': job.get('location', 'Unknown'),
                'apply_link': job.get('apply_link', '#'),
                'match_score': job.get('match_score', 0),
                'match_description': job.get('match_description', ''),
                'required_skills': job.get('required_skills', [])
            }
            formatted_jobs.append(job_result)
        
        return JSONResponse({
            "success": True,
            "message": f"Test completed - found {len(formatted_jobs)} matches",
            "jobs": formatted_jobs,
            "skills_found": resume_skills,
            "system_info": {
                "using_two_stage_matching": True,
                "llm_enabled": bool(os.getenv("OPENAI_API_KEY")),
                "job_count": len(formatted_jobs)
            }
        })
        
    except Exception as e:
        logger.error(f"Test matching error: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "system_info": {
                "llm_enabled": bool(os.getenv("OPENAI_API_KEY"))
            }
        })


@app.post("/api/refresh-cache")
@limiter.limit("1/5minutes")
async def refresh_cache(request: Request, force_full: bool = False, max_days_old: int = 30,
                        _: None = Depends(require_api_key)):
    """
    Manually refresh the hybrid cache system (admin endpoint)

    Args:
        force_full: If True, performs full scrape. If False, uses smart detection
        max_days_old: Filter to only get jobs posted within N days (default: 30 days for last month)
    """
    try:
        scrape_type = "full" if force_full else "smart"
        date_filter_msg = f" (last {max_days_old} days)" if max_days_old else ""
        logger.info(f"Manual cache refresh requested ({scrape_type} scrape{date_filter_msg})")
        
        # Clear Redis cache (keep database for deduplication)
        clear_result = job_cache.clear_cache()
        
        # Perform scraping based on force_full parameter
        if force_full:
            from job_scrapers.dispatcher import scrape_jobs_full
            jobs = await scrape_jobs_full(max_days_old=max_days_old)
        else:
            # Smart scraping (auto-detects incremental vs full)
            jobs = await scrape_jobs(max_days_old=max_days_old)
        
        if not jobs:
            # If no new jobs in incremental mode, that's okay
            if not force_full:
                cache_info = job_cache.get_cache_info()
                db_jobs = cache_info.get('database', {}).get('active_jobs', 0)
                return JSONResponse({
                    "success": True,
                    "message": f"No new jobs found{date_filter_msg}. {db_jobs} jobs already in database",
                    "new_jobs": 0,
                    "total_jobs": db_jobs,
                    "scrape_type": scrape_type,
                    "max_days_old": max_days_old
                })
            else:
                raise HTTPException(status_code=500, detail=f"No jobs scraped in full refresh{date_filter_msg}")
        
        # Store in hybrid cache system
        cache_result = job_cache.set_cached_jobs(jobs, cache_type='manual_refresh')
        
        return JSONResponse({
            "success": True,
            "message": f"Cache refreshed successfully{date_filter_msg}",
            "new_jobs": cache_result.get('new_jobs', 0),
            "total_jobs": cache_result.get('total_jobs', len(jobs)),
            "database_success": cache_result.get('database_success', False),
            "redis_success": cache_result.get('redis_success', False),
            "scrape_type": scrape_type,
            "max_days_old": max_days_old,
            "redis_ttl_hours": job_cache.CACHE_TTL / 3600
        })
    except Exception as e:
        logger.error(f"Error refreshing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Cache refresh failed: {str(e)}")


@app.post("/api/refresh-cache-incremental")
@limiter.limit("2/5minutes")
async def refresh_cache_incremental(request: Request, max_days_old: int = 30,
                                    _: None = Depends(require_api_key)):
    """
    Force incremental cache refresh (only new jobs)

    Args:
        max_days_old: Filter to only get jobs posted within N days (default: 30 days for last month)
    """
    try:
        date_filter_msg = f" (last {max_days_old} days)" if max_days_old else ""
        logger.info(f"Incremental cache refresh requested{date_filter_msg}")
        
        from job_scrapers.dispatcher import scrape_jobs_incremental
        jobs = await scrape_jobs_incremental(max_days_old=max_days_old)
        
        cache_result = job_cache.set_cached_jobs(jobs, cache_type='incremental_manual')
        
        return JSONResponse({
            "success": True,
            "message": f"Incremental refresh completed{date_filter_msg}",
            "new_jobs": cache_result.get('new_jobs', 0),
            "total_processed": len(jobs),
            "database_success": cache_result.get('database_success', False),
            "redis_success": cache_result.get('redis_success', False),
            "max_days_old": max_days_old
        })
    except Exception as e:
        logger.error(f"Error in incremental refresh: {e}")
        raise HTTPException(status_code=500, detail=f"Incremental refresh failed: {str(e)}")


@app.get("/api/categories")
@limiter.limit("30/minute")
async def list_categories(request: Request):
    """Canonical department categories + live active-job counts for each.

    Powers the upload-page department filter (labels + counts). Public, cheap —
    reuses the cached job list. Counts use metadata['category'] (stamped at insert
    time; not-yet-backfilled rows fall into 'other')."""
    from job_categories import CATEGORIES
    from collections import Counter
    try:
        jobs = await get_jobs_with_cache() or []
    except Exception:
        jobs = []
    counts = Counter((j.get('metadata') or {}).get('category') or 'other' for j in jobs)
    return JSONResponse({
        "categories": [
            {"id": cid, "label": label, "count": counts.get(cid, 0)}
            for cid, label in CATEGORIES
        ],
        "total": len(jobs),
    })


@app.get("/api/database-stats")
@limiter.limit("10/minute")
async def database_stats(request: Request):
    """Get database statistics — public endpoint used by the landing page job counter."""
    try:
        from job_database import get_database_stats
        stats = get_database_stats()

        return JSONResponse(
            {
                "success": True,
                "database_stats": stats,
                "available": job_cache.is_database_available(),
            },
            headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(e)}")


@app.get("/api/refresh-health")
@limiter.limit("10/minute")
async def refresh_health(request: Request):
    """Check the health of the cache refresh system"""
    try:
        from job_database import get_db, CacheMetadata, Job
        from datetime import datetime, timedelta
        import json

        db = get_db()
        try:
            # Get most recent cache operation
            latest_op = db.query(CacheMetadata).order_by(CacheMetadata.last_updated.desc()).first()

            # Get stats
            active_count = db.query(Job).filter(Job.is_active == True).count()
            now = datetime.utcnow()

            health_status = {
                "status": "healthy",
                "warnings": [],
                "info": {}
            }

            if latest_op:
                time_since_update = now - latest_op.last_updated
                hours_since = time_since_update.total_seconds() / 3600

                health_status["info"]["last_refresh"] = {
                    "time": latest_op.last_updated.isoformat(),
                    "hours_ago": round(hours_since, 1),
                    "type": latest_op.cache_type,
                    "status": latest_op.status,
                    "new_jobs": latest_op.new_jobs_added,
                    "total_jobs": latest_op.job_count
                }

                # Check if refresh is overdue (>26 hours = daily refresh likely failed)
                if hours_since > 26:
                    health_status["status"] = "unhealthy"
                    health_status["warnings"].append(f"No refresh in {round(hours_since, 1)}h - daily refresh may not be running")
                elif hours_since > 24:
                    health_status["status"] = "warning"
                    health_status["warnings"].append(f"Refresh slightly overdue ({round(hours_since, 1)}h)")
            else:
                health_status["status"] = "unknown"
                health_status["warnings"].append("No cache operations recorded in database")

            # Check active job count
            health_status["info"]["active_jobs"] = active_count

            if active_count == 0:
                health_status["status"] = "critical"
                health_status["warnings"].append("No active jobs in database")
            elif active_count < 50:
                if health_status["status"] == "healthy":
                    health_status["status"] = "warning"
                health_status["warnings"].append(f"Low active job count: {active_count}")

            # Check job age distribution
            active_jobs = db.query(Job).filter(Job.is_active == True).all()

            if active_jobs:
                old_jobs = 0
                recent_jobs = 0

                for job in active_jobs:
                    try:
                        metadata = json.loads(job.job_metadata) if job.job_metadata else {}
                        days_since = metadata.get('days_since_posted')

                        if days_since is not None:
                            if days_since > 21:  # More than 3 weeks
                                old_jobs += 1
                            elif days_since <= 7:  # Last week
                                recent_jobs += 1
                    except:
                        pass

                health_status["info"]["job_age_distribution"] = {
                    "recent_jobs_0_7d": recent_jobs,
                    "old_jobs_21plus_d": old_jobs,
                    "recent_percentage": round(recent_jobs / len(active_jobs) * 100, 1) if active_jobs else 0
                }

                if recent_jobs < len(active_jobs) * 0.15:  # Less than 15% recent
                    if health_status["status"] == "healthy":
                        health_status["status"] = "warning"
                    health_status["warnings"].append("Less than 15% of jobs are from last 7 days - may need refresh")

            return JSONResponse({
                "success": True,
                "health": health_status,
                "recommendation": (
                    "Run manual refresh with: curl -X POST /api/refresh-cache?max_days_old=30"
                    if health_status["status"] in ["unhealthy", "warning"]
                    else "System is healthy"
                )
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error checking refresh health: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "health": {
                "status": "error",
                "warnings": [f"Health check failed: {str(e)}"]
            }
        }, status_code=500)



def _sanitize_filename(value: str) -> str:
    """Replace non-alphanumeric characters with underscores for safe filenames."""
    return re.sub(r"[^\w\-]", "_", value)


@app.post("/api/tailor-resume")
@limiter.limit("2/minute")
async def tailor_resume_endpoint(
    request: Request,
    resume: UploadFile = File(...),
    job_title: str = Form(...),
    company: str = Form(...),
    job_description: str = Form(default=""),
    job_hash: str = Form(default=""),
    template_id: str = Form(default="classic"),
    user_id: str = Depends(require_user),
):
    from quota import get_tailor_quota_status, record_tailor_request, WEEKLY_TAILOR_LIMIT
    from job_database import get_job_by_hash
    from resume_tailor.tailor_resume import TEMPLATE_REGISTRY

    if template_id not in TEMPLATE_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown template_id: {template_id}")

    # Check Postgres-backed weekly quota before doing any work
    if TRACK_USAGE:
        db = get_db()
        try:
            status = get_tailor_quota_status(db, user_id)
            if status["remaining"] <= 0:
                reset_at = status["reset_at"]
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "weekly_quota_exceeded",
                        "message": f"You've used all {WEEKLY_TAILOR_LIMIT} tailored resumes this week.",
                        "limit": status["limit"],
                        "used": status["used"],
                        "remaining": 0,
                        "reset_at": reset_at.isoformat() if reset_at else None,
                    },
                )
        finally:
            close_db(db)

    # Resolve the job description: prefer the FULL description looked up by job_hash
    # from the DB, falling back to the posted form field (covers stale caches that
    # predate job_hash, and direct API callers that don't send one).
    resolved_jd = job_description
    jd_source = "form"
    if job_hash:
        looked_up = get_job_by_hash(job_hash)
        if looked_up and looked_up.get("description"):
            resolved_jd = looked_up["description"]
            jd_source = "job_hash"

    logger.info(
        f"Tailor request: user={user_id} job='{job_title}' at '{company}' "
        f"file={resume.filename} jd_source={jd_source} jd_len={len(resolved_jd or '')}"
    )

    if not resume.filename or not resume.filename.lower().endswith(".pdf"):
        logger.error(f"Tailor error (user={user_id}): unsupported format — {resume.filename}")
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported")

    file_content = await resume.read()
    if not file_content:
        logger.error(f"Tailor error (user={user_id}): empty file")
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    import time
    start_time = time.time()

    try:
        pdf_bytes = _tailor_resume(file_content, job_title, company, resolved_jd, template_id=template_id)
    except ValueError as e:
        logger.error(f"Tailor error (user={user_id}): {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        logger.error(f"Tailor error (user={user_id}): pdflatex not found")
        raise HTTPException(status_code=500, detail="LaTeX compiler unavailable — pdflatex not found")
    except subprocess.TimeoutExpired:
        logger.error(f"Tailor error (user={user_id}): pdflatex timed out")
        raise HTTPException(status_code=500, detail="LaTeX compilation timed out")
    except RuntimeError as e:
        logger.error(f"Tailor error (user={user_id}): runtime error — {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Tailor error (user={user_id}): unexpected — {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Resume tailoring failed: {e}")

    execution_time = round(time.time() - start_time, 2)
    safe_company = _sanitize_filename(company)
    safe_title = _sanitize_filename(job_title)
    filename = f"resume_tailored_{safe_company}_{safe_title}.pdf"

    # Record usage AFTER successful generation — failed attempts don't count against quota
    if TRACK_USAGE:
        db = get_db()
        try:
            record_tailor_request(db, user_id, job_title, company)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to record tailor quota entry for user={user_id}: {e}")
            db.rollback()
        finally:
            close_db(db)

    logger.info(f"Tailor complete: user={user_id} time={execution_time}s size={len(pdf_bytes)} bytes")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/critique-resume")
@limiter.limit("5/minute")
async def critique_resume_endpoint(
    request: Request,
    resume: UploadFile = File(...),
    target_category: str = Form(default=""),
    user_id: str = Depends(require_user),
):
    """Returns structured JSON (resume + sparse per-bullet critiques), not a PDF —
    the frontend renders it as an annotated resume page. Cache hits are free and
    never touch the weekly quota; only a real (non-cached) Sonnet call does."""
    import hashlib

    from job_categories import CATEGORY_IDS
    from job_database import get_critique_cache, set_critique_cache
    from quota import get_critique_quota_status, record_critique_request, WEEKLY_CRITIQUE_LIMIT
    from resume_critique.critique_resume import critique_resume_to_json
    from resume_tailor.tailor_resume import extract_text_from_pdf

    if not resume.filename or not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported")

    file_content = await resume.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    resume_hash = hashlib.sha256(file_content).hexdigest()
    category = target_category if target_category in CATEGORY_IDS else ""

    cached = get_critique_cache(user_id, resume_hash, category or "auto")
    if cached:
        logger.info(f"Critique cache hit: user={user_id} hash={resume_hash[:12]}")
        return JSONResponse({**cached, "cached": True})

    # Quota is checked AFTER the cache lookup — a cache hit above already
    # returned, so only real Sonnet calls reach this check.
    if TRACK_USAGE:
        db = get_db()
        try:
            status = get_critique_quota_status(db, user_id)
            if status["remaining"] <= 0:
                reset_at = status["reset_at"]
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "weekly_quota_exceeded",
                        "message": f"You've used all {WEEKLY_CRITIQUE_LIMIT} critiques this week.",
                        "limit": status["limit"],
                        "used": status["used"],
                        "remaining": 0,
                        "reset_at": reset_at.isoformat() if reset_at else None,
                    },
                )
        finally:
            close_db(db)

    try:
        resume_text = extract_text_from_pdf(file_content)
        result = critique_resume_to_json(resume_text, target_category=category or None)
    except RuntimeError as e:
        logger.error(f"Critique error (user={user_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Critique error (user={user_id}): unexpected — {e}")
        raise HTTPException(status_code=500, detail=f"Resume critique failed: {e}")

    set_critique_cache(user_id, resume_hash, category or "auto", result)

    if TRACK_USAGE:
        db = get_db()
        try:
            record_critique_request(db, user_id)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to record critique quota entry for user={user_id}: {e}")
            db.rollback()
        finally:
            close_db(db)

    return JSONResponse({**result, "cached": False})


@app.post("/api/dev/critique-resume-text")
@limiter.limit("5/minute")
async def critique_resume_text_dev_endpoint(request: Request, user_id: str = Depends(require_user)):
    """DEV-ONLY: same as /api/critique-resume but takes pasted resume text instead of a PDF
    upload. Exists purely so the Critique flow can be exercised by browser automation / manual
    testing when a working file input isn't available — mirrors production's parse-then-critique
    call, just skipping the PDF-extraction step. 404s outside development/staging."""
    if _ENVIRONMENT == "production":
        raise HTTPException(status_code=404, detail="Not found")

    from job_categories import CATEGORY_IDS
    from resume_critique.critique_resume import critique_resume_to_json

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    resume_text = (body.get("resume_text") or "").strip()
    if not resume_text:
        raise HTTPException(status_code=400, detail="resume_text is required")
    target_category = body.get("target_category") or ""
    category = target_category if target_category in CATEGORY_IDS else None

    try:
        result = critique_resume_to_json(resume_text, target_category=category)
    except RuntimeError as e:
        logger.error(f"Dev critique-by-text error (user={user_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Dev critique-by-text error (user={user_id}): unexpected — {e}")
        raise HTTPException(status_code=500, detail=f"Resume critique failed: {e}")

    return JSONResponse({**result, "cached": False})


@app.post("/api/critique-resume/rewrite")
@limiter.limit("2/minute")
async def critique_rewrite_endpoint(request: Request, user_id: str = Depends(require_user)):
    """Rewrites ONLY the critiqued bullets (everything else stays byte-identical) and compiles
    a fresh PDF. JSON in/out — the client already has structured_resume + critiques from the
    /api/critique-resume call, so no file re-upload is needed. Consumes the TAILOR quota (same
    ledger as /api/tailor-resume), not the critique quota — this is a resume-generation action,
    same reasoning as why remote-compile has its own separate ledger from tailor."""
    import base64

    from quota import get_tailor_quota_status, record_tailor_request, WEEKLY_TAILOR_LIMIT
    from resume_critique.critique_resume import apply_critique_rewrite, to_compile_schema
    from resume_tailor.tailor_resume import compile_resume_json_to_pdf

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    structured_resume = body.get("structured_resume")
    extra_context = body.get("extra_context", "")
    # Green bullets are "do more of this" exemplars, not rewrite targets — only red/yellow
    # actually get sent to the model, so rewritten_bullet_ids below is never a false label.
    critiques = [c for c in (body.get("critiques") or []) if c.get("severity") in ("red", "yellow")]

    if not isinstance(structured_resume, dict):
        raise HTTPException(status_code=400, detail="structured_resume is required")
    if not critiques:
        raise HTTPException(status_code=400, detail="No red/yellow critiques to rewrite")

    if TRACK_USAGE:
        db = get_db()
        try:
            status = get_tailor_quota_status(db, user_id)
            if status["remaining"] <= 0:
                reset_at = status["reset_at"]
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "weekly_quota_exceeded",
                        "message": f"You've used all {WEEKLY_TAILOR_LIMIT} tailored resumes this week.",
                        "limit": status["limit"],
                        "used": status["used"],
                        "remaining": 0,
                        "reset_at": reset_at.isoformat() if reset_at else None,
                    },
                )
        finally:
            close_db(db)

    try:
        rewritten = apply_critique_rewrite(structured_resume, critiques, extra_context)
        pdf_bytes, _diagnostics = compile_resume_json_to_pdf(to_compile_schema(rewritten))
    except RuntimeError as e:
        logger.error(f"Critique rewrite error (user={user_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="LaTeX compiler unavailable — pdflatex not found")
    except Exception as e:
        logger.error(f"Critique rewrite error (user={user_id}): unexpected — {e}")
        raise HTTPException(status_code=500, detail=f"Resume rewrite failed: {e}")

    if TRACK_USAGE:
        db = get_db()
        try:
            record_tailor_request(db, user_id, "Critique-based rewrite", "Critique")
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to record tailor quota entry for user={user_id}: {e}")
            db.rollback()
        finally:
            close_db(db)

    return JSONResponse({
        "structured_resume": rewritten,
        "pdf_base64": base64.b64encode(pdf_bytes).decode(),
        "rewritten_bullet_ids": [c["bullet_id"] for c in critiques if c.get("bullet_id")],
    })


@app.get("/api/usage")
@limiter.limit("20/minute")
async def get_usage(request: Request, user_id: str = Depends(require_user)):
    from quota import (
        get_critique_quota_status,
        get_remote_compile_quota_status,
        get_tailor_quota_status,
        get_think_deeper_quota_status,
    )
    db = get_db()
    try:
        tailor = get_tailor_quota_status(db, user_id)
        deep = get_think_deeper_quota_status(db, user_id)
        remote_compile = get_remote_compile_quota_status(db, user_id)
        critique = get_critique_quota_status(db, user_id)
    finally:
        db.close()

    def _shape(q):
        return {
            "limit": q["limit"],
            "used": q["used"],
            "remaining": q["remaining"],
            "reset_at": q["reset_at"].isoformat() if q["reset_at"] else None,
            "window_days": 7,
        }

    return JSONResponse({
        "tailor_resume": _shape(tailor),
        "think_deeper": _shape(deep),
        "critique": _shape(critique),
        # Consumed by API-key remote compiles (MCP /api/v1), NOT by the in-app
        # tailor feature — the frontend surfaces that distinction.
        "remote_compile": _shape(remote_compile),
    })


# ---------------------------------------------------------------------------
# Universal ATS Crawler endpoints  (admin-gated via require_api_key)
#
# NOTE: registered BEFORE the React catch-all (moved to the very end of this
# file). Starlette matches routes in registration order, so the GET
# /api/crawl/status route must precede the GET /{full_path} catch-all or it is
# shadowed and returns index.html instead of the status payload.
# ---------------------------------------------------------------------------

# Crawls run FIRE-AND-FORGET, not inline. Railway's
# edge proxy aborts any HTTP request at ~300s, but a full crawl / discover (which
# probes ~15k boards) routinely runs longer. Awaiting inline returned a 502 to the
# client at 5 min even though the work succeeded server-side, and made the GitHub
# Actions step (curl --fail-with-body --retry) go red and retry. So each endpoint
# schedules the crawl on the event loop and returns 202 immediately; progress is
# polled via GET /api/crawl/status.
_CRAWL_RUNNING: dict = {}          # crawl_type -> bool (a run is in flight)
_CRAWL_LAST: dict = {}             # crawl_type -> summary of the last finished run
_CRAWL_TASKS: set = set()          # strong refs so tasks aren't GC'd mid-flight


async def _run_crawl_task(crawl_type, coro, cache_key=None):
    """Await a crawl coroutine in the background, record the outcome, clear the flag."""
    started = datetime.utcnow()
    try:
        result = await coro
        if cache_key:
            from job_database import record_cache_operation
            record_cache_operation(cache_key, result.get("jobs_found", 0), result.get("new_jobs", 0))
        _CRAWL_LAST[crawl_type] = {
            "ok": True,
            "started_at": started.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            **result,
        }
        logger.info("[crawl:%s] complete: %s", crawl_type, result)
    except Exception as exc:  # a background crash must never vanish silently
        _CRAWL_LAST[crawl_type] = {
            "ok": False,
            "started_at": started.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(exc),
        }
        logger.exception("[crawl:%s] failed", crawl_type)
    finally:
        _CRAWL_RUNNING[crawl_type] = False


def _start_crawl(crawl_type, coro, cache_key=None) -> bool:
    """
    Atomically claim the crawl slot and schedule the background task. Returns
    False (and closes the un-awaited coroutine) if a crawl of this type is
    already running. The flag is set BEFORE scheduling, with no await in between,
    so the claim is atomic on the single event loop.
    """
    if _CRAWL_RUNNING.get(crawl_type):
        coro.close()  # avoid 'coroutine was never awaited' warning
        return False
    _CRAWL_RUNNING[crawl_type] = True
    task = asyncio.create_task(_run_crawl_task(crawl_type, coro, cache_key))
    _CRAWL_TASKS.add(task)
    task.add_done_callback(_CRAWL_TASKS.discard)
    return True


@app.post("/api/crawl/incremental")
async def crawl_incremental(
    request: Request,
    _: None = Depends(require_api_key),
):
    """
    Trigger an incremental ATS crawl (jobs updated in last N hours).
    Designed to run every 15 minutes via GitHub Actions.

    Body (JSON, optional):
      max_age_hours: int = 1
      ats_types: list[str] = []  # empty = all
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    max_age_hours = int(body.get("max_age_hours", 1))
    ats_types = body.get("ats_types") or []

    from crawlers.orchestrator import CrawlOrchestrator
    coro = CrawlOrchestrator().run_incremental(max_age_hours=max_age_hours, ats_types=ats_types)
    if not _start_crawl("incremental", coro, "ats_incremental"):
        return JSONResponse({"success": True, "status": "already_running", "crawl_type": "incremental"})
    return JSONResponse(
        {"success": True, "status": "started", "crawl_type": "incremental"},
        status_code=202,
    )


@app.post("/api/crawl/full")
async def crawl_full(
    request: Request,
    _: None = Depends(require_api_key),
):
    """
    Trigger a full ATS crawl (all companies, no time filter).
    Designed to run nightly via GitHub Actions.

    Body (JSON, optional):
      ats_types: list[str] = []  # empty = all
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    ats_types = body.get("ats_types") or []

    from crawlers.orchestrator import CrawlOrchestrator
    coro = CrawlOrchestrator().run_full(ats_types=ats_types)
    if not _start_crawl("full", coro, "ats_full"):
        return JSONResponse({"success": True, "status": "already_running", "crawl_type": "full"})
    return JSONResponse(
        {"success": True, "status": "started", "crawl_type": "full"},
        status_code=202,
    )


@app.post("/api/crawl/discover-companies")
async def crawl_discover_companies(
    request: Request,
    _: None = Depends(require_api_key),
):
    """
    Probe community datasets (Greenhouse tokens, Lever slugs, Ashby sitemap)
    and upsert newly discovered companies into the company_registry.
    Designed to run weekly via GitHub Actions.

    By default (incremental) it skips slugs already registered as ACTIVE companies,
    so it spends compute discovering net-new / not-yet-registered boards instead of
    re-probing the thousands already known. Pass {"rescan_all": true} to force a
    full re-probe of every slug in the datasets (occasional registry rebuild).

    Body (JSON, optional):
      rescan_all: bool = false
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    rescan_all = bool(body.get("rescan_all", False))

    from crawlers.bootstrap import run_bootstrap
    from crawlers.company_registry import CompanyRegistryStore
    coro = run_bootstrap(registry=CompanyRegistryStore(), incremental=not rescan_all)
    # discover seeds the company_registry, not the jobs cache -> no cache_key
    if not _start_crawl("discover", coro):
        return JSONResponse({"success": True, "status": "already_running", "crawl_type": "discover"})
    return JSONResponse(
        {"success": True, "status": "started", "crawl_type": "discover"},
        status_code=202,
    )


@app.get("/api/crawl/status")
async def crawl_status(request: Request):
    """
    Return crawl health: last incremental/full timestamps, company counts by
    ATS type, and jobs added in last 24h / 7d.

    Public endpoint (no auth) — matches the pattern of /api/database-stats.
    """
    from job_database import get_db, close_db, Job, CacheMetadata
    from crawlers.company_registry import CompanyRegistryStore
    from datetime import timedelta

    from sqlalchemy import text as sa_text

    db = get_db()
    try:
        now = datetime.utcnow()
        jobs_24h = db.query(Job).filter(
            Job.first_seen >= now - timedelta(hours=24)
        ).count()
        jobs_7d = db.query(Job).filter(
            Job.first_seen >= now - timedelta(days=7)
        ).count()

        last_incremental = db.query(CacheMetadata).filter(
            CacheMetadata.cache_type == "ats_incremental"
        ).order_by(CacheMetadata.last_updated.desc()).first()
        last_full = db.query(CacheMetadata).filter(
            CacheMetadata.cache_type == "ats_full"
        ).order_by(CacheMetadata.last_updated.desc()).first()

        # Egress health: verify get_due_for_crawl() is fetching ≤200 rows/call.
        # rows_per_call should drop from ~10,159 → ≤200 after the limit fix.
        egress_check = None
        try:
            row = db.execute(sa_text("""
                SELECT calls,
                       rows,
                       CASE WHEN calls > 0 THEN rows / calls ELSE 0 END AS rows_per_call
                FROM   pg_stat_statements
                WHERE  query LIKE '%company_registry%crawl_priority%'
                ORDER  BY calls DESC
                LIMIT  1
            """)).fetchone()
            if row:
                egress_check = {
                    "calls": row[0],
                    "total_rows": row[1],
                    "rows_per_call": row[2],
                    "status": "ok" if row[2] <= 200 else "high",
                }
        except Exception:
            pass  # pg_stat_statements may not be available in all environments
    finally:
        close_db(db)

    registry_stats = CompanyRegistryStore().get_stats()

    return JSONResponse({
        "success": True,
        "last_incremental": last_incremental.last_updated.isoformat() if last_incremental else None,
        "last_full": last_full.last_updated.isoformat() if last_full else None,
        "total_companies": registry_stats.get("total_active", 0),
        "companies_by_ats": registry_stats.get("by_ats", {}),
        "jobs_added_24h": jobs_24h,
        "jobs_added_7d": jobs_7d,
        # Live state of the fire-and-forget background crawls (see _start_crawl):
        # `running` shows what's in flight right now; `last_run` carries the
        # summary/error of each type's most recent completed run this process.
        "running": {k: bool(v) for k, v in _CRAWL_RUNNING.items()},
        "last_run": _CRAWL_LAST,
        "egress_health": egress_check,
    })


# Catch-all: serve React app for any non-API route. MUST stay the last route
# registered — Starlette matches in registration order, so any route added below
# this one is shadowed (it previously swallowed GET /api/crawl/status).
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_react(full_path: str):
    index = FRONTEND_BUILD / "index.html"
    if FRONTEND_BUILD.exists() and index.exists():
        return FileResponse(str(index))
    return JSONResponse({"error": "Frontend not built"}, status_code=404)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=[
            ".",
            "resume_parser",
            "resume_tailor",
            "matching",
            "job_scrapers",
            "email_sender",
        ],
        reload_excludes=["frontend", "venv", ".git", "__pycache__"],
    )

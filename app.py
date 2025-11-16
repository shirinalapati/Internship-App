import os
import secrets
from fastapi import FastAPI, Request, File, UploadFile, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from dotenv import load_dotenv
import io
import json
import asyncio
from datetime import datetime

# Import our modules
from resume_parser import parse_resume, is_valid_resume
from job_scrapers.dispatcher import scrape_jobs
from matching.matcher import match_resume_to_jobs
from matching.metadata_matcher import extract_resume_metadata
import job_cache
from s3_service import upload_resume_to_s3, download_resume_from_s3, delete_resume_from_s3

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(title="Internship Matcher", version="1.0.0")

# Add CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add session middleware for basic session support
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-secret-key-here"))

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create upload folder if it doesn't exist
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Startup event to initialize hybrid cache system
@app.on_event("startup")
async def startup_event():
    """Initialize hybrid Redis + Database cache system on server startup"""
    environment = os.getenv("ENVIRONMENT", "development").lower()
    print(f"🚀 Starting up Internship Matcher [{environment.upper()}] with Hybrid Cache System...")

    # Initialize hybrid cache (Redis + Database)
    cache_available = job_cache.init_redis()

    if cache_available:
        # Check cache status
        cache_info = job_cache.get_cache_info()

        # Try to get cached jobs
        cached_jobs = job_cache.get_cached_jobs()

        # Determine if we should refresh cache on startup
        should_refresh = False

        if environment == "development":
            # In development: check if cache needs refresh (older than 6 hours)
            if cached_jobs:
                db_info = cache_info.get('database', {})
                last_update = db_info.get('last_update')

                if last_update:
                    # Parse last update time and check if it's stale
                    from datetime import datetime, timedelta
                    try:
                        last_update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                        time_since_update = datetime.now(last_update_time.tzinfo) - last_update_time

                        # Refresh if cache is older than 6 hours in dev
                        if time_since_update > timedelta(hours=6):
                            print(f"🔄 Cache is {time_since_update.total_seconds() / 3600:.1f} hours old - refreshing...")
                            should_refresh = True
                        else:
                            print(f"📦 Using existing cache: {len(cached_jobs)} jobs (updated {time_since_update.total_seconds() / 3600:.1f} hours ago)")
                    except Exception as e:
                        print(f"⚠️ Error parsing cache timestamp: {e}")
                        should_refresh = False
                else:
                    print(f"📦 Using existing cache: {len(cached_jobs)} jobs available")
            else:
                # No cache - always refresh
                should_refresh = True
                print("📥 No cached jobs found - initializing cache...")
        else:
            # Production: only initialize if cache is empty
            if cached_jobs:
                print(f"📦 Using existing cache: {len(cached_jobs)} jobs available")
                print(f"🔍 Cache status: {cache_info.get('hybrid', {}).get('message', 'Unknown')}")
            else:
                should_refresh = True
                print("📥 No cached jobs found - initializing cache...")

        # Perform cache refresh if needed
        if should_refresh:
            try:
                # Use smart scraping (auto-detects incremental vs full)
                # Default to 30-day filter to only get recent jobs
                jobs = await scrape_jobs(max_days_old=30)
                if jobs:
                    # Store in hybrid cache system
                    cache_result = job_cache.set_cached_jobs(jobs, cache_type='startup')
                    if cache_result.get('database_success') or cache_result.get('redis_success'):
                        print(f"✅ Startup cache initialized: {cache_result.get('new_jobs', 0)} new jobs, {len(jobs)} total")
                    else:
                        print("⚠️ Cache initialization failed")
                else:
                    print("⚠️ No jobs scraped on startup")
            except Exception as e:
                print(f"❌ Error during startup scraping: {e}")
    else:
        print("❌ Hybrid cache system unavailable - jobs will be scraped per request")
    
    # Print final cache status
    try:
        final_info = job_cache.get_cache_info()
        if final_info.get('database', {}).get('status') == 'active':
            db_info = final_info['database']
            print(f"📊 Database: {db_info.get('active_jobs', 0)} active jobs")
        if final_info.get('redis', {}).get('status') == 'active':
            redis_info = final_info['redis']
            print(f"⚡ Redis: {redis_info.get('job_count', 0)} jobs cached")
    except Exception as e:
        print(f"⚠️ Error getting final cache status: {e}")
    
    print("✅ Startup complete!")

    # Start background task for daily cache refresh
    asyncio.create_task(daily_cache_refresh_task())
    print("🕒 Daily cache refresh scheduler started")

async def daily_cache_refresh_task():
    """
    Background task that automatically refreshes the cache every 24 hours.
    This ensures jobs stay fresh without manual intervention.
    """
    while True:
        try:
            # Wait 24 hours before first refresh (cache was just initialized on startup)
            await asyncio.sleep(24 * 60 * 60)  # 24 hours in seconds

            print(f"🔄 [Scheduled] Starting daily cache refresh at {datetime.utcnow().isoformat()}")

            # Perform smart scraping with 30-day filter
            jobs = await scrape_jobs(max_days_old=30)

            if jobs:
                # Store in hybrid cache system
                cache_result = job_cache.set_cached_jobs(jobs, cache_type='daily_scheduled')
                new_jobs = cache_result.get('new_jobs', 0)
                total_jobs = cache_result.get('total_jobs', len(jobs))

                if cache_result.get('database_success') or cache_result.get('redis_success'):
                    print(f"✅ [Scheduled] Daily refresh complete: {new_jobs} new jobs, {total_jobs} total active jobs")
                else:
                    print(f"⚠️ [Scheduled] Cache refresh failed")
            else:
                print("📝 [Scheduled] No new jobs found in daily refresh")

        except asyncio.CancelledError:
            print("🛑 Daily cache refresh task cancelled")
            break
        except Exception as e:
            print(f"❌ [Scheduled] Error in daily cache refresh: {e}")
            # Continue running even if one refresh fails
            continue

async def get_jobs_with_cache():
    """
    Get jobs using hybrid cache system (Redis + Database).
    This function is used by all endpoints to get job data efficiently.
    """
    # Try to get from hybrid cache system
    cached_jobs = job_cache.get_cached_jobs()
    
    if cached_jobs:
        print(f"⚡ Using {len(cached_jobs)} jobs from hybrid cache")
        return cached_jobs
    
    # Cache miss - use smart scraping strategy
    print("🌐 Cache miss - using smart scraping strategy...")
    try:
        # Smart scraping automatically detects incremental vs full
        # Default to 30-day filter to only get recent jobs
        jobs = await scrape_jobs(max_days_old=30)
        
        # Store in hybrid cache system
        if jobs:
            cache_result = job_cache.set_cached_jobs(jobs, cache_type='on_demand')
            new_jobs = cache_result.get('new_jobs', 0)
            total_jobs = cache_result.get('total_jobs', len(jobs))
            
            if cache_result.get('database_success') or cache_result.get('redis_success'):
                print(f"✅ Scraped and cached: {new_jobs} new jobs, {total_jobs} total")
            else:
                print(f"⚠️ Scraping successful but caching failed: {total_jobs} jobs")
            
            # Return all active jobs from cache for consistency
            return job_cache.get_cached_jobs() or jobs
        else:
            print("⚠️ No jobs scraped")
            return []
            
    except Exception as e:
        print(f"❌ Error during smart scraping: {e}")
        # Try to get any available jobs from database as fallback
        try:
            from job_cache import get_jobs_for_matching
            fallback_jobs = get_jobs_for_matching()
            if fallback_jobs:
                print(f"🔄 Using {len(fallback_jobs)} fallback jobs from database")
                return fallback_jobs
        except Exception as fallback_error:
            print(f"❌ Fallback also failed: {fallback_error}")
        
        return []

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page - redirects to dashboard"""
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
            print(f"❌ Error reading file: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error reading the uploaded file: {str(e)}"
            })

        print(f"📥 Uploaded: {resume.filename}")
        print(f"📊 File size: {len(file_content)} bytes")
        print(f"🔍 File type: {resume.content_type}")

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
            print(f"❌ Error parsing resume: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error parsing your resume: {str(e)}"
            })

        print(f"🔍 Extracted resume skills: {resume_skills}")
        print(f"📊 Resume analysis: {resume_metadata.get('experience_level', 'unknown')} level")
        
        # Validate resume content
        if resume_text and not is_valid_resume(resume_text):
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": "The uploaded file does not appear to be a valid resume. Please upload a document that contains relevant professional information."
            })

        # Get jobs from cache or scrape
        try:
            print("🌐 Fetching internship opportunities...")
            jobs = await get_jobs_with_cache()
            if not jobs:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "Unable to fetch internship opportunities at this time. Please try again later."
                })
            print(f"📋 Total jobs available: {len(jobs)}")
        except Exception as e:
            print(f"❌ Error fetching jobs: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error fetching internship opportunities: {str(e)}"
            })

        # Match resume to jobs
        try:
            print("🎯 Starting job matching...")
            matched_jobs = match_resume_to_jobs(resume_skills, jobs, resume_text)
            if not matched_jobs:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "No matching internship opportunities were found for your skills. Consider updating your resume with more relevant technical skills."
                })
            print(f"✅ Final matched jobs: {len(matched_jobs)}")
        except Exception as e:
            print(f"❌ Error matching jobs: {e}")
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
        print(f"❌ Unexpected error in match_resume: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "results": None,
            "error": f"An unexpected error occurred: {str(e)}. Please try again or contact support if the problem persists."
        })


@app.post("/api/match")
async def api_match_resume(resume: UploadFile = File(...), think_deeper: str = Form("true")):
    """API endpoint for React frontend - returns JSON instead of HTML"""
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
            print(f"❌ Error reading file: {e}")
            raise HTTPException(status_code=400, detail=f"Error reading the uploaded file: {str(e)}")

        print(f"📥 Uploaded: {resume.filename}")
        print(f"📊 File size: {len(file_content)} bytes")
        print(f"🔍 File type: {resume.content_type}")

        # Upload file to S3
        s3_key = None
        try:
            print("☁️ Uploading resume to S3...")
            s3_key = upload_resume_to_s3(file_content, resume.filename)
            print(f"✅ Resume uploaded to S3: {s3_key}")
        except Exception as e:
            print(f"❌ S3 upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to upload resume: {str(e)}")

        # Download file from S3 for processing
        try:
            print("📥 Downloading resume from S3 for processing...")
            downloaded_content, original_filename = download_resume_from_s3(s3_key)
            print(f"✅ Downloaded {len(downloaded_content)} bytes from S3")
        except Exception as e:
            print(f"❌ S3 download failed: {e}")
            # Clean up S3 file if download fails
            if s3_key:
                delete_resume_from_s3(s3_key)
            raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")

        # Parse resume using selected method (returns skills, text, and metadata)
        try:
            use_llm = think_deeper.lower() == "true"
            if use_llm:
                print("📄 Step 1/4: Analyzing your resume with AI (GPT-5)...")
            else:
                print("📄 Step 1/4: Analyzing your resume with text-based parsing...")
            resume_skills, resume_text, resume_metadata = parse_resume(downloaded_content, original_filename, use_llm)
            if not resume_skills:
                raise HTTPException(
                    status_code=400, 
                    detail="No skills were detected in your resume. Please make sure your resume includes technical skills, programming languages, or relevant experience."
                )
        except Exception as e:
            print(f"❌ Error parsing resume: {e}")
            raise HTTPException(status_code=400, detail=f"Error parsing your resume: {str(e)}")

        print(f"✅ Step 1 complete: Extracted {len(resume_skills)} skills from resume")
        print(f"🔍 Skills found: {resume_skills}")
        print(f"📊 Candidate level: {resume_metadata.get('experience_level', 'unknown')}")
        
        # Validate resume content
        if resume_text and not is_valid_resume(resume_text):
            raise HTTPException(
                status_code=400, 
                detail="The uploaded file does not appear to be a valid resume. Please upload a document that contains relevant professional information."
            )

        # Get jobs from cache or scrape
        try:
            print("🌐 Step 2/4: Fetching internship opportunities...")
            jobs = await get_jobs_with_cache()
            if not jobs:
                raise HTTPException(
                    status_code=500, 
                    detail="Unable to fetch internship opportunities at this time. Please try again later."
                )
            print(f"✅ Step 2 complete: Found {len(jobs)} internship opportunities")
        except Exception as e:
            print(f"❌ Error fetching jobs: {e}")
            raise HTTPException(status_code=500, detail=f"Error fetching internship opportunities: {str(e)}")

        # Match resume to jobs with intelligent prefiltering
        try:
            print("🤖 Step 3/4: Analyzing job requirements with AI...")
            print(f"🔍 Your skills: {resume_skills}")
            print(f"📊 Intelligent prefiltering will select top 50 jobs from {len(jobs)} total jobs based on your skills")
            
            # Pass ALL jobs - intelligent_prefilter_jobs will filter from 1000s → 50 based on THIS resume's skills
            print("🎯 Step 4/4: Matching your skills to job requirements...")
            matched_jobs = match_resume_to_jobs(resume_skills, jobs, resume_text)
            
            print(f"✅ Matching complete: Found {len(matched_jobs)} relevant opportunities")
            
            # Filter jobs with score > 0 for the final response
            jobs_with_matches = [job for job in matched_jobs if job.get('match_score', 0) > 0]
            
            if not jobs_with_matches:
                # Show all jobs with their scores for debugging
                print("❌ No jobs with score > 0 - showing all job scores for debugging:")
                for i, job in enumerate(matched_jobs[:5]):
                    print(f"   Job {i+1}: {job.get('company')} - {job.get('title')} (Score: {job.get('match_score', 0)})")
                    print(f"      Skills: {job.get('required_skills', [])}")
                
                return JSONResponse(content={
                    "success": True,
                    "message": "No matching internship opportunities were found for your skills. Consider updating your resume with more relevant technical skills.",
                    "jobs": matched_jobs[:5],  # Return jobs with scores for debugging
                    "skills_found": resume_skills,
                    "debug_info": {
                        "total_jobs_scraped": len(jobs),
                        "jobs_processed": len(jobs_to_process),
                        "skills_extracted": len(resume_skills),
                        "all_job_scores": [{"company": job.get('company'), "title": job.get('title'), "score": job.get('match_score', 0)} for job in matched_jobs[:5]]
                    }
                })
            
            # Use jobs with matches for the success response
            matched_jobs = jobs_with_matches
            print(f"✅ Final matched jobs: {len(matched_jobs)}")
        except Exception as e:
            print(f"❌ Error matching jobs: {e}")
            raise HTTPException(status_code=500, detail=f"Error matching your resume to jobs: {str(e)}")

        # Clean up S3 file after processing
        if s3_key:
            try:
                delete_resume_from_s3(s3_key)
                print(f"🗑️ Cleaned up S3 file: {s3_key}")
            except Exception as cleanup_error:
                print(f"⚠️ Failed to clean up S3 file {s3_key}: {cleanup_error}")

        # Return JSON response for React frontend
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(matched_jobs)} matching opportunities!",
            "jobs": matched_jobs,
            "skills_found": resume_skills
        })

    except HTTPException:
        # Clean up S3 file on error
        if 's3_key' in locals() and s3_key:
            try:
                delete_resume_from_s3(s3_key)
                print(f"🗑️ Cleaned up S3 file after error: {s3_key}")
            except Exception as cleanup_error:
                print(f"⚠️ Failed to clean up S3 file {s3_key}: {cleanup_error}")
        raise
    except Exception as e:
        # Clean up S3 file on unexpected error
        if 's3_key' in locals() and s3_key:
            try:
                delete_resume_from_s3(s3_key)
                print(f"🗑️ Cleaned up S3 file after error: {s3_key}")
            except Exception as cleanup_error:
                print(f"⚠️ Failed to clean up S3 file {s3_key}: {cleanup_error}")
        
        print(f"❌ Unexpected error in api_match_resume: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"An unexpected error occurred: {str(e)}. Please try again or contact support if the problem persists."
        )

@app.post("/api/match-stream")
async def stream_match_resume(resume: UploadFile = File(...), think_deeper: str = Form("true")):
    """Streaming endpoint that provides real-time progress updates"""
    
    # IMPORTANT: Read all file data BEFORE the generator function
    # to avoid "i/o operation on closed file" errors
    try:
        # Validate file
        if not resume:
            async def error_response():
                yield f"data: {json.dumps({'error': 'No file was uploaded'})}\n\n"
            return StreamingResponse(
                error_response(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream",
                }
            )

        file_extension = resume.filename.split('.')[-1].lower() if resume.filename else ''
        allowed_extensions = ['pdf', 'png', 'jpg', 'jpeg']
        
        if file_extension not in allowed_extensions:
            async def error_response():
                yield f"data: {json.dumps({'error': f'Invalid file type: {file_extension}'})}\n\n"
            return StreamingResponse(
                error_response(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream",
                }
            )

        # Read file content ONCE, before the generator
        file_content = await resume.read()
        filename = resume.filename
        content_type = resume.content_type
        
        if not file_content:
            async def error_response():
                yield f"data: {json.dumps({'error': 'Empty file uploaded'})}\n\n"
            return StreamingResponse(
                error_response(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream",
                }
            )

        # Upload file to S3 ONCE, before the generator
        try:
            s3_key = upload_resume_to_s3(file_content, filename)
            print(f"✅ Stream: Resume uploaded to S3: {s3_key}")
        except Exception as e:
            print(f"❌ Stream: S3 upload failed: {e}")
            async def error_response():
                yield f"data: {json.dumps({'error': f'S3 upload failed: {str(e)}'})}\n\n"
            return StreamingResponse(
                error_response(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream",
                }
            )
    except Exception as e:
        async def error_response():
            yield f"data: {json.dumps({'error': f'File upload error: {str(e)}'})}\n\n"
        return StreamingResponse(
            error_response(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            }
        )
    
    async def generate_progress():
        try:
            # Convert think_deeper parameter to boolean
            use_llm = think_deeper.lower() == "true"
            
            yield f"data: {json.dumps({'step': 1, 'message': 'File uploaded to S3 successfully', 'progress': 10})}\n\n"

            # Download file from S3 for processing
            try:
                yield f"data: {json.dumps({'step': 2, 'message': 'Downloading resume from S3...', 'progress': 15})}\n\n"
                downloaded_content, original_filename = download_resume_from_s3(s3_key)
                yield f"data: {json.dumps({'step': 3, 'message': 'Resume downloaded successfully', 'progress': 20})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': f'S3 download failed: {str(e)}'})}\n\n"
                return

            # Step 3: Parse resume using selected method
            if use_llm:
                yield f"data: {json.dumps({'step': 4, 'message': 'Analyzing your resume with AI (GPT-5)...', 'progress': 25})}\n\n"
            else:
                yield f"data: {json.dumps({'step': 4, 'message': 'Analyzing your resume with text-based parsing...', 'progress': 25})}\n\n"
            
            try:
                resume_skills, resume_text, resume_metadata = parse_resume(downloaded_content, original_filename, use_llm)
                if not resume_skills:
                    yield f"data: {json.dumps({'error': 'No skills detected in resume'})}\n\n"
                    return
                
                exp_level = resume_metadata.get('experience_level', 'unknown')
                yield f"data: {json.dumps({'step': 5, 'message': f'Found {len(resume_skills)} skills - {exp_level} level', 'skills': resume_skills, 'progress': 40})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Resume parsing failed: {str(e)}'})}\n\n"
                # Clean up S3 file on error
                try:
                    delete_resume_from_s3(s3_key)
                except:
                    pass
                return

            # Step 6: Get jobs from cache or scrape
            yield f"data: {json.dumps({'step': 6, 'message': 'Loading internship opportunities...', 'progress': 50})}\n\n"
            
            try:
                jobs = await get_jobs_with_cache()
                if not jobs:
                    yield f"data: {json.dumps({'error': 'No jobs found'})}\n\n"
                    # Clean up S3 file on error
                    try:
                        delete_resume_from_s3(s3_key)
                    except:
                        pass
                    return
                    
                yield f"data: {json.dumps({'step': 7, 'message': f'Found {len(jobs)} internship opportunities', 'progress': 60})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Job loading failed: {str(e)}'})}\n\n"
                # Clean up S3 file on error
                try:
                    delete_resume_from_s3(s3_key)
                except:
                    pass
                return

            # Step 8: Use intelligent prefiltering + batch LLM matching
            yield f"data: {json.dumps({'step': 8, 'message': f'Intelligently filtering from {len(jobs)} jobs based on your skills...', 'progress': 70})}\n\n"
            
            try:
                # Pass ALL jobs - intelligent prefiltering will select top 50 for THIS resume
                matched_jobs = match_resume_to_jobs(resume_skills, jobs, resume_text)
                
                yield f"data: {json.dumps({'step': 9, 'message': 'Deep career fit analysis in progress...', 'progress': 85})}\n\n"
                
                # Convert to the format expected by frontend
                formatted_jobs = []
                for job in matched_jobs:
                    # Handle timestamp conversion - could be datetime or string
                    first_seen = job.get('first_seen')
                    last_seen = job.get('last_seen')

                    # Convert to ISO string if datetime object
                    if first_seen and hasattr(first_seen, 'isoformat'):
                        first_seen = first_seen.isoformat()
                    elif first_seen and not isinstance(first_seen, str):
                        first_seen = str(first_seen)

                    if last_seen and hasattr(last_seen, 'isoformat'):
                        last_seen = last_seen.isoformat()
                    elif last_seen and not isinstance(last_seen, str):
                        last_seen = str(last_seen)

                    job_result = {
                        'company': job.get('company', 'Unknown'),
                        'title': job.get('title', 'Unknown'),
                        'location': job.get('location', 'Unknown'),
                        'apply_link': job.get('apply_link', '#'),
                        'match_score': job.get('match_score', 0),
                        'match_description': job.get('match_description', ''),
                        'ai_reasoning': job.get('ai_reasoning'),  # Include AI reasoning data
                        'required_skills': job.get('required_skills', []),
                        'first_seen': first_seen,
                        'last_seen': last_seen
                    }
                    formatted_jobs.append(job_result)
                
                jobs_with_matches = [job for job in formatted_jobs if job['match_score'] > 0]
                
                # For think deeper mode: return all results since LLM processed all jobs
                # For regular mode: limit to 10 results for speed
                if use_llm:
                    final_results = formatted_jobs  # Return all LLM-analyzed jobs
                else:
                    final_results = formatted_jobs[:10] if len(formatted_jobs) >= 10 else formatted_jobs
                
                # Debug logging
                print(f"🔍 Streaming final results: {len(final_results)} jobs")
                for i, job in enumerate(final_results):
                    print(f"   Job {i+1}: {job['company']} - {job['title']} (Score: {job['match_score']})")
                
                # Update completion message based on mode and results
                if use_llm:
                    completion_message = f'Think Deeper analysis complete! Found {len(jobs_with_matches)} matches out of {len(final_results)} jobs analyzed.'
                else:
                    completion_message = f'Quick matching complete! Showing top {len(final_results)} results.'
                
                # Clean up S3 file after successful processing
                try:
                    delete_resume_from_s3(s3_key)
                    print(f"🗑️ Stream: Cleaned up S3 file: {s3_key}")
                except Exception as cleanup_error:
                    print(f"⚠️ Stream: Failed to clean up S3 file {s3_key}: {cleanup_error}")

                yield f"data: {json.dumps({'step': 10, 'message': completion_message, 'final_results': final_results, 'matches_found': len(jobs_with_matches), 'total_results': len(final_results), 'progress': 100, 'complete': True})}\n\n"
                
            except Exception as e:
                print(f"❌ Error in intelligent matching: {e}")
                # Fallback to legacy approach if new system fails
                yield f"data: {json.dumps({'step': 9, 'message': 'Using fallback matching system...', 'progress': 85})}\n\n"
                
                from matching.matcher import match_resume_to_jobs_legacy
                # Even in fallback, use intelligent prefiltering - pass all jobs
                matched_jobs = match_resume_to_jobs_legacy(resume_skills, jobs, resume_text)
                
                # Format results
                formatted_jobs = []
                for job in matched_jobs:
                    # Handle timestamp conversion - could be datetime or string
                    first_seen = job.get('first_seen')
                    last_seen = job.get('last_seen')

                    # Convert to ISO string if datetime object
                    if first_seen and hasattr(first_seen, 'isoformat'):
                        first_seen = first_seen.isoformat()
                    elif first_seen and not isinstance(first_seen, str):
                        first_seen = str(first_seen)

                    if last_seen and hasattr(last_seen, 'isoformat'):
                        last_seen = last_seen.isoformat()
                    elif last_seen and not isinstance(last_seen, str):
                        last_seen = str(last_seen)

                    job_result = {
                        'company': job.get('company', 'Unknown'),
                        'title': job.get('title', 'Unknown'),
                        'location': job.get('location', 'Unknown'),
                        'apply_link': job.get('apply_link', '#'),
                        'match_score': job.get('match_score', 0),
                        'match_description': job.get('match_description', ''),
                        'ai_reasoning': job.get('ai_reasoning'),  # Include AI reasoning data
                        'required_skills': job.get('required_skills', []),
                        'first_seen': first_seen,
                        'last_seen': last_seen
                    }
                    formatted_jobs.append(job_result)
                
                jobs_with_matches = [job for job in formatted_jobs if job['match_score'] > 0]
                
                # Fallback uses legacy matching - keep 10 result limit for speed
                final_results = formatted_jobs[:10] if len(formatted_jobs) >= 10 else formatted_jobs
                
                # Clean up S3 file after fallback processing
                try:
                    delete_resume_from_s3(s3_key)
                    print(f"🗑️ Stream: Cleaned up S3 file after fallback: {s3_key}")
                except Exception as cleanup_error:
                    print(f"⚠️ Stream: Failed to clean up S3 file {s3_key}: {cleanup_error}")

                yield f"data: {json.dumps({'step': 10, 'message': 'Matching complete!', 'final_results': final_results, 'matches_found': len(jobs_with_matches), 'total_results': len(final_results), 'progress': 100, 'complete': True})}\n\n"

        except Exception as e:
            # Clean up S3 file on unexpected error
            try:
                delete_resume_from_s3(s3_key)
                print(f"🗑️ Stream: Cleaned up S3 file after error: {s3_key}")
            except Exception as cleanup_error:
                print(f"⚠️ Stream: Failed to clean up S3 file {s3_key}: {cleanup_error}")
            
            yield f"data: {json.dumps({'error': f'Unexpected error: {str(e)}'})}\n\n"

    return StreamingResponse(
        generate_progress(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )

@app.get("/api/cache-status")
async def cache_status():
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
        print(f"❌ Test matching error: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "system_info": {
                "llm_enabled": bool(os.getenv("OPENAI_API_KEY"))
            }
        })

@app.post("/api/refresh-cache")
async def refresh_cache(force_full: bool = False, max_days_old: int = 30):
    """
    Manually refresh the hybrid cache system (admin endpoint)

    Args:
        force_full: If True, performs full scrape. If False, uses smart detection
        max_days_old: Filter to only get jobs posted within N days (default: 30 days for last month)
    """
    try:
        scrape_type = "full" if force_full else "smart"
        date_filter_msg = f" (last {max_days_old} days)" if max_days_old else ""
        print(f"🔄 Manual cache refresh requested ({scrape_type} scrape{date_filter_msg})...")
        
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
        print(f"❌ Error refreshing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Cache refresh failed: {str(e)}")

@app.post("/api/refresh-cache-incremental")
async def refresh_cache_incremental(max_days_old: int = 30):
    """
    Force incremental cache refresh (only new jobs)

    Args:
        max_days_old: Filter to only get jobs posted within N days (default: 30 days for last month)
    """
    try:
        date_filter_msg = f" (last {max_days_old} days)" if max_days_old else ""
        print(f"🔄 Incremental cache refresh requested{date_filter_msg}...")
        
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
        print(f"❌ Error in incremental refresh: {e}")
        raise HTTPException(status_code=500, detail=f"Incremental refresh failed: {str(e)}")

@app.get("/api/database-stats")
async def database_stats():
    """Get detailed database statistics"""
    try:
        from job_database import get_database_stats
        stats = get_database_stats()
        
        return JSONResponse({
            "success": True,
            "database_stats": stats,
            "available": job_cache.is_database_available()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

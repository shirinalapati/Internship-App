import os
import secrets
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from dotenv import load_dotenv
import io
import json

# Import our modules
from resume_parser import parse_resume, is_valid_resume
from job_scrapers.dispatcher import scrape_jobs
from matching.matcher import match_resume_to_jobs
from matching.metadata_matcher import extract_resume_metadata
import job_cache

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

# Startup event to initialize Redis and cache jobs
@app.on_event("startup")
async def startup_event():
    """Initialize Redis and pre-load job cache on server startup"""
    print("🚀 Starting up Internship Matcher...")
    
    # Initialize Redis connection
    redis_connected = job_cache.init_redis()
    
    if redis_connected:
        # Check if cache exists
        cached_jobs = job_cache.get_cached_jobs()
        
        if cached_jobs:
            cache_info = job_cache.get_cache_info()
            print(f"📦 Using existing cache: {cache_info['message']}")
        else:
            # Cache is empty - scrape jobs and populate cache
            print("📥 Cache empty - scraping jobs on startup...")
            try:
                jobs = await scrape_jobs()
                if jobs:
                    job_cache.set_cached_jobs(jobs)
                    print(f"✅ Startup cache populated with {len(jobs)} jobs")
                else:
                    print("⚠️ No jobs scraped on startup")
            except Exception as e:
                print(f"❌ Error scraping jobs on startup: {e}")
    else:
        print("⚠️ Running without Redis - jobs will be scraped per request")
    
    print("✅ Startup complete!")

async def get_jobs_with_cache():
    """
    Get jobs from cache if available, otherwise scrape and cache them.
    This function is used by all endpoints to get job data efficiently.
    """
    # Try to get from cache first
    cached_jobs = job_cache.get_cached_jobs()
    
    if cached_jobs:
        print(f"⚡ Using {len(cached_jobs)} cached jobs")
        return cached_jobs
    
    # Cache miss - scrape jobs
    print("🌐 Cache miss - scraping jobs...")
    jobs = await scrape_jobs()
    
    # Try to cache the results for next time
    if jobs:
        job_cache.set_cached_jobs(jobs)
        print(f"✅ Scraped and cached {len(jobs)} jobs")
    
    return jobs

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

        # Parse resume
        try:
            resume_skills = parse_resume(file_content, resume.filename)
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

        # Validate resume content
        try:
            resume_text = ""
            if resume.content_type == "application/pdf":
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    resume_text = " ".join([page.extract_text() or "" for page in pdf.pages])
            else:
                # For images, we'll skip text validation since we're using OCR
                resume_text = "Image resume - OCR processing used"
            
            if resume_text and not is_valid_resume(resume_text):
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "The uploaded file does not appear to be a valid resume. Please upload a document that contains relevant professional information."
                })
        except Exception as e:
            print(f"⚠️ Warning: Could not validate resume text: {e}")
            # Continue anyway since we have skills extracted

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
async def api_match_resume(resume: UploadFile = File(...)):
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

        # Parse resume
        try:
            print("📄 Step 1/4: Analyzing your resume with AI...")
            resume_skills = parse_resume(file_content, resume.filename)
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

        # Validate resume content
        try:
            resume_text = ""
            if resume.content_type == "application/pdf":
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    resume_text = " ".join([page.extract_text() or "" for page in pdf.pages])
            else:
                # For images, we'll skip text validation since we're using OCR
                resume_text = "Image resume - OCR processing used"
            
            if resume_text and not is_valid_resume(resume_text):
                raise HTTPException(
                    status_code=400, 
                    detail="The uploaded file does not appear to be a valid resume. Please upload a document that contains relevant professional information."
                )
        except Exception as e:
            print(f"⚠️ Warning: Could not validate resume text: {e}")
            # Continue anyway since we have skills extracted

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

        # Match resume to jobs with timeout handling
        try:
            print("🤖 Step 3/4: Analyzing job requirements with AI...")
            print(f"🔍 Your skills: {resume_skills}")
            
            # Limit jobs to prevent timeout (process max 20 jobs)
            jobs_to_process = jobs[:20] if len(jobs) > 20 else jobs
            if len(jobs) > 20:
                print(f"⚡ Processing first {len(jobs_to_process)} jobs to prevent timeout")
            
            print("🎯 Step 4/4: Matching your skills to job requirements...")
            matched_jobs = match_resume_to_jobs(resume_skills, jobs_to_process, resume_text)
            
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

        # Return JSON response for React frontend
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(matched_jobs)} matching opportunities!",
            "jobs": matched_jobs,
            "skills_found": resume_skills
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error in api_match_resume: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"An unexpected error occurred: {str(e)}. Please try again or contact support if the problem persists."
        )

@app.post("/api/match-stream")
async def stream_match_resume(resume: UploadFile = File(...)):
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
            yield f"data: {json.dumps({'step': 1, 'message': 'File uploaded successfully', 'progress': 10})}\n\n"

            # Step 1: Parse resume
            yield f"data: {json.dumps({'step': 2, 'message': 'Analyzing your resume with AI...', 'progress': 20})}\n\n"
            
            try:
                resume_skills = parse_resume(file_content, filename)
                if not resume_skills:
                    yield f"data: {json.dumps({'error': 'No skills detected in resume'})}\n\n"
                    return
                    
                yield f"data: {json.dumps({'step': 3, 'message': f'Found {len(resume_skills)} skills in your resume', 'skills': resume_skills, 'progress': 40})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Resume parsing failed: {str(e)}'})}\n\n"
                return

            # Get resume text for matching
            resume_text = ""
            if content_type == "application/pdf":
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    resume_text = " ".join([page.extract_text() or "" for page in pdf.pages])

            # Step 2: Get jobs from cache or scrape
            yield f"data: {json.dumps({'step': 4, 'message': 'Loading internship opportunities...', 'progress': 50})}\n\n"
            
            try:
                jobs = await get_jobs_with_cache()
                if not jobs:
                    yield f"data: {json.dumps({'error': 'No jobs found'})}\n\n"
                    return
                    
                yield f"data: {json.dumps({'step': 5, 'message': f'Found {len(jobs)} internship opportunities', 'progress': 60})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Job loading failed: {str(e)}'})}\n\n"
                return

            # Step 3: Use our new two-stage intelligent matching system
            yield f"data: {json.dumps({'step': 6, 'message': 'Analyzing your profile with AI...', 'progress': 70})}\n\n"
            
            try:
                # Use the new two-stage matching approach
                matched_jobs = match_resume_to_jobs(resume_skills, jobs, resume_text)
                
                yield f"data: {json.dumps({'step': 7, 'message': 'Deep career fit analysis in progress...', 'progress': 85})}\n\n"
                
                # Convert to the format expected by frontend
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
                
                jobs_with_matches = [job for job in formatted_jobs if job['match_score'] > 0]
                
                # Ensure we always return exactly 10 results for consistency
                final_results = formatted_jobs[:10] if len(formatted_jobs) >= 10 else formatted_jobs
                
                # Debug logging
                print(f"🔍 Streaming final results: {len(final_results)} jobs")
                for i, job in enumerate(final_results):
                    print(f"   Job {i+1}: {job['company']} - {job['title']} (Score: {job['match_score']})")
                
                yield f"data: {json.dumps({'step': 8, 'message': 'Intelligent matching complete!', 'final_results': final_results, 'matches_found': len(jobs_with_matches), 'total_results': len(final_results), 'progress': 100, 'complete': True})}\n\n"
                
            except Exception as e:
                print(f"❌ Error in two-stage matching: {e}")
                # Fallback to legacy approach if new system fails
                yield f"data: {json.dumps({'step': 7, 'message': 'Using fallback matching system...', 'progress': 85})}\n\n"
                
                from matching.matcher import match_resume_to_jobs_legacy
                jobs_to_process = jobs[:20] if len(jobs) > 20 else jobs
                matched_jobs = match_resume_to_jobs_legacy(resume_skills, jobs_to_process, resume_text)
                
                # Format results
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
                
                jobs_with_matches = [job for job in formatted_jobs if job['match_score'] > 0]
                
                # Ensure we always return exactly 10 results for consistency
                final_results = formatted_jobs[:10] if len(formatted_jobs) >= 10 else formatted_jobs
                
                yield f"data: {json.dumps({'step': 8, 'message': 'Matching complete!', 'final_results': final_results, 'matches_found': len(jobs_with_matches), 'total_results': len(final_results), 'progress': 100, 'complete': True})}\n\n"

        except Exception as e:
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
    """Get current cache status and information"""
    cache_info = job_cache.get_cache_info()
    redis_available = job_cache.is_redis_available()
    
    return JSONResponse({
        "redis_connected": redis_available,
        "cache_info": cache_info,
        "cache_key": job_cache.CACHE_KEY,
        "ttl_hours": job_cache.CACHE_TTL / 3600
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
async def refresh_cache():
    """Manually refresh the job cache (admin endpoint)"""
    try:
        print("🔄 Manual cache refresh requested...")
        
        # Clear existing cache
        job_cache.clear_cache()
        
        # Scrape fresh jobs
        jobs = await scrape_jobs()
        
        if not jobs:
            raise HTTPException(status_code=500, detail="No jobs scraped")
        
        # Cache the new jobs
        job_cache.set_cached_jobs(jobs)
        
        return JSONResponse({
            "success": True,
            "message": f"Cache refreshed successfully with {len(jobs)} jobs",
            "job_count": len(jobs),
            "ttl_hours": 24
        })
    except Exception as e:
        print(f"❌ Error refreshing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Cache refresh failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import os

# Import real logic
from resume_parser.parse_resume import parse_resume
from job_scrapers.dispatcher import scrape_all_company_sites
from matching.matcher import match_job_to_resume

# Import authentication
from auth.oauth import oauth, get_user_info_google, get_user_info_apple
from auth.session import session_manager

app = FastAPI()

# Add session middleware (required for OAuth)
app.add_middleware(SessionMiddleware, secret_key=os.getenv('SECRET_KEY', 'your-secret-key-change-in-production'))

# Template directory
templates = Jinja2Templates(directory="templates")

# Upload directory
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def is_valid_resume(text):
    """
    Check if the uploaded file contains resume-like content.
    Returns True if it looks like a resume, False otherwise.
    """
    if not text or len(text.strip()) < 50:
        return False
    
    # Convert to lowercase for easier checking
    text_lower = text.lower()
    
    # Resume indicators (positive signals)
    resume_indicators = [
        "resume", "cv", "curriculum vitae", "education", "experience", 
        "skills", "work history", "employment", "job", "position",
        "university", "college", "degree", "bachelor", "master", "phd",
        "internship", "project", "achievement", "certification"
    ]
    
    # Book/document indicators (negative signals)
    book_indicators = [
        "chapter", "table of contents", "index", "bibliography", "references",
        "preface", "introduction", "conclusion", "appendix", "glossary",
        "copyright", "published by", "author", "editor", "publisher",
        "isbn", "edition", "volume", "page", "paragraph"
    ]
    
    # Count positive and negative indicators
    resume_score = sum(1 for indicator in resume_indicators if indicator in text_lower)
    book_score = sum(1 for indicator in book_indicators if indicator in text_lower)
    
    # Check for common resume sections
    has_education = any(word in text_lower for word in ["education", "academic", "degree", "university", "college"])
    has_experience = any(word in text_lower for word in ["experience", "work", "employment", "job", "position"])
    has_skills = any(word in text_lower for word in ["skills", "technologies", "programming", "languages"])
    
    # If it has book-like structure, it's probably not a resume
    if book_score > 2:
        return False
    
    # If it has resume-like structure, it's probably a resume
    if resume_score > 1 and (has_education or has_experience):
        return True
    
    # If it has skills section, it's likely a resume
    if has_skills and (has_education or has_experience):
        return True
    
    # Default: if it has some resume indicators, accept it
    return resume_score > 0

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Root endpoint - redirect to login or dashboard based on auth status"""
    if session_manager.is_authenticated(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard - accessible with or without login"""
    user = session_manager.get_current_user(request)
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "results": None,
        "user": user
    })

@app.get("/auth/{provider}")
async def oauth_login(request: Request, provider: str):
    """Initiate OAuth login"""
    if provider != "google":
        raise HTTPException(status_code=400, detail="Only Google OAuth is supported")
    
    try:
        from auth.oauth import get_google_oauth_client, get_authorization_url
        import secrets
        
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        request.session["oauth_state"] = state
        
        # Get the redirect URI based on the request
        if request.url.hostname == "localhost":
            redirect_uri = "http://localhost:8000/auth/google/callback"
        else:
            redirect_uri = f"{request.url.scheme}://{request.url.netloc}/auth/google/callback"
        
        # Create OAuth client and get authorization URL
        client = await get_google_oauth_client()
        authorization_url = await get_authorization_url(client, redirect_uri, state)
        
        return RedirectResponse(url=authorization_url, status_code=302)
        
    except ValueError as e:
        # OAuth not configured properly
        return RedirectResponse(url="/dashboard?message=oauth_setup_required", status_code=302)
    except Exception as e:
        print(f"❌ OAuth error: {e}")
        raise HTTPException(status_code=500, detail="OAuth configuration error")

@app.get("/auth/{provider}/callback")
async def oauth_callback(request: Request, provider: str, code: str = None, state: str = None, error: str = None):
    """Handle OAuth callback"""
    if provider != "google":
        raise HTTPException(status_code=400, detail="Only Google OAuth is supported")
    
    # Check for OAuth errors
    if error:
        print(f"❌ OAuth error: {error}")
        return RedirectResponse(url="/login?error=oauth_error", status_code=302)
    
    # Verify state parameter
    stored_state = request.session.get("oauth_state")
    if not state or state != stored_state:
        print("❌ Invalid state parameter")
        return RedirectResponse(url="/login?error=invalid_state", status_code=302)
    
    # Clear the state from session
    request.session.pop("oauth_state", None)
    
    if not code:
        return RedirectResponse(url="/login?error=no_code", status_code=302)
    
    try:
        from auth.oauth import get_google_oauth_client, exchange_code_for_token, get_user_info
        
        # Get the redirect URI
        if request.url.hostname == "localhost":
            redirect_uri = "http://localhost:8000/auth/google/callback"
        else:
            redirect_uri = f"{request.url.scheme}://{request.url.netloc}/auth/google/callback"
        
        # Exchange code for token
        client = await get_google_oauth_client()
        token = await exchange_code_for_token(client, code, redirect_uri)
        
        if not token:
            return RedirectResponse(url="/login?error=token_exchange_failed", status_code=302)
        
        # Get user information
        user_info = await get_user_info(token)
        
        if not user_info:
            return RedirectResponse(url="/login?error=user_info_failed", status_code=302)
        
        # Create user session
        user = {
            "id": user_info.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "picture": user_info.get("picture"),
            "provider": "google"
        }
        
        request.session["user"] = user
        print(f"✅ User logged in successfully: {user['email']}")
        
        return RedirectResponse(url="/dashboard", status_code=302)
        
    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        return RedirectResponse(url="/login?error=oauth_callback_error", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    """Logout user"""
    session_id = request.session.get('session_id')
    if session_id:
        session_manager.delete_session(session_id)
        request.session.clear()
    
    return RedirectResponse(url="/login", status_code=302)

@app.post("/match", response_class=HTMLResponse)
async def match_resume(request: Request, resume: UploadFile = File(...)):
    """
    Accepts a resume upload and returns matching internships with detailed analysis.
    """
    user = session_manager.get_current_user(request)
    
    # Validate file type
    allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg']
    file_extension = os.path.splitext(resume.filename)[1].lower()
    
    if file_extension not in allowed_extensions:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "results": None,
            "error": "Please upload a valid file (PDF, PNG, JPG, or JPEG).",
            "user": user
        })
    
    # Save uploaded file
    file_location = os.path.join(UPLOAD_FOLDER, resume.filename) 
    with open(file_location, "wb") as f:
        f.write(await resume.read())
    
    print(f"📥 Uploaded: {resume.filename}")

    # Parse the resume
    try:
        resume_data = parse_resume(file_location)
        resume_skills = resume_data["skills"]
        resume_text = resume_data.get("raw_text", "")
        
        # Validate that this is actually a resume
        if not is_valid_resume(resume_text):
            return templates.TemplateResponse("index.html", {
                "request": request,
                "results": None,
                "error": "A valid resume wasn't uploaded. Please try again with a proper resume file.",
                "user": user
            })
        
        print("🔍 Extracted resume skills:", resume_skills)
        
        # Check if any skills were extracted
        if not resume_skills:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "results": None,
                "error": "No skills were detected in your resume. Please make sure your resume includes technical skills, programming languages, or relevant experience.",
                "user": user
            })
        
    except Exception as e:
        print(f"❌ Error parsing resume: {e}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "results": None,
            "error": "Error processing your resume. Please make sure the file is not corrupted and try again.",
            "user": user
        })
    
    # Scrape internships from multiple sources
    print("🌐 Starting job scraping...")
    jobs = scrape_all_company_sites(keyword="software engineering intern")
    print(f"📋 Total jobs scraped: {len(jobs)}")
    
    if len(jobs) == 0:
        print("❌ No jobs were scraped - this is the problem!")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "results": [],
            "error": "Unable to fetch internship opportunities at the moment. Please try again later.",
            "user": user
        })
    
    print("🔍 Sample job data:")
    for i, job in enumerate(jobs[:3]):  # Show first 3 jobs
        print(f"  Job {i+1}: {job.get('title', 'No title')} - Skills: {job.get('required_skills', [])}")
    
    matched_jobs = []
    for job in jobs:
        score, description = match_job_to_resume(job, resume_skills, resume_text)
        print(f"🎯 Matching {job.get('title', 'Unknown')}: Score = {score}")
        print(f"📝 Description: {description}")
        
        # Only include jobs with a meaningful match (score > 0)
        if score > 0:
            matched_jobs.append({
                "title": job["title"],
                "score": score,
                "description": job.get("description", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "apply_link": job.get("apply_link", ""),
                "match_description": description
            })

    print(f"✅ Final matched jobs: {len(matched_jobs)}")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "results": matched_jobs,
        "user": user
    })

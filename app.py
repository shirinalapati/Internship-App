import os
import secrets
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.sessions import SessionMiddleware
import uvicorn
from dotenv import load_dotenv

# Import our modules
from resume_parser import parse_resume, is_valid_resume
from job_scrapers.dispatcher import scrape_jobs
from matching.skill_matcher import match_resume_to_jobs
from matching.metadata_matcher import extract_resume_metadata

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(title="Internship Matcher", version="1.0.0")

# Add session middleware for basic session support
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-secret-key-here"))

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create upload folder if it doesn't exist
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    """
    Accepts a resume upload and returns matching internships with detailed analysis.
    """
    try:
        # Validate file type
        allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg']
        file_extension = os.path.splitext(resume.filename)[1].lower()
        
        if file_extension not in allowed_extensions:
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": "Please upload a valid file (PDF, PNG, JPG, or JPEG)."
            })
        
        # Save uploaded file
        file_location = os.path.join(UPLOAD_FOLDER, resume.filename) 
        with open(file_location, "wb") as f:
            content = await resume.read()
            f.write(content)
        
        print(f"📥 Uploaded: {resume.filename}")

        # Parse the resume
        try:
            resume_data = parse_resume(file_location)
            resume_skills = resume_data["skills"]
            resume_text = resume_data.get("raw_text", "")
            
            # Validate that this is actually a resume
            if not is_valid_resume(resume_text):
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "The uploaded file does not appear to be a valid resume. Please upload a document that contains relevant professional information."
                })
            
            print("🔍 Extracted resume skills:", resume_skills)
            
            # Check if we have skills
            if not resume_skills:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "No skills were detected in your resume. Please make sure your resume includes technical skills, programming languages, or relevant experience."
                })
            
            # Scrape jobs
            print("🌐 Starting job scraping...")
            jobs = scrape_jobs()
            
            if not jobs:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "Unable to fetch job listings at this time. Please try again later."
                })
            
            # Match resume to jobs
            print("🎯 Starting job matching...")
            matched_jobs = match_resume_to_jobs(resume_skills, jobs)
            
            if not matched_jobs:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "No matching internships found for your skills. Try updating your resume with more technical skills or programming languages."
                })
            
            print(f"✅ Final matched jobs: {len(matched_jobs)}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": matched_jobs
            })
            
        except Exception as e:
            print(f"❌ Resume parsing error: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error processing your resume: {str(e)}"
            })
            
    except Exception as e:
        print(f"❌ General error in /match: {e}")
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "results": None,
            "error": "There was an error processing your request. Please try again."
        })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

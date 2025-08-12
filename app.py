import os
import secrets
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.sessions import SessionMiddleware
import uvicorn
from dotenv import load_dotenv
import io

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

        # Scrape jobs
        try:
            print("🌐 Starting job scraping...")
            jobs = await scrape_jobs()
            if not jobs:
                return templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "results": None,
                    "error": "Unable to fetch internship opportunities at this time. Please try again later."
                })
            print(f"📋 Total jobs scraped: {len(jobs)}")
        except Exception as e:
            print(f"❌ Error scraping jobs: {e}")
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "results": None,
                "error": f"Error fetching internship opportunities: {str(e)}"
            })

        # Match resume to jobs
        try:
            print("🎯 Starting job matching...")
            matched_jobs = match_resume_to_jobs(resume_skills, jobs)
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

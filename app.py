from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os

# Import real logic
from resume_parser.parse_resume import parse_resume
from job_scrapers.dispatcher import scrape_all_company_sites
from matching.matcher import match_job_to_resume

app = FastAPI()

# Template directory
templates = Jinja2Templates(directory="templates")

# Upload directory
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "results": None})

@app.post("/match", response_class=HTMLResponse)
async def match_resume(request: Request, resume: UploadFile = File(...)):
    """
    Accepts a resume upload and returns matching internships with detailed analysis.
    """
    # Save uploaded file
    file_location = os.path.join(UPLOAD_FOLDER, resume.filename) 
    with open(file_location, "wb") as f:
        f.write(await resume.read())
    
    print(f"📥 Uploaded: {resume.filename}")

    # Real logic for matching jobs
    resume_data = parse_resume(file_location)
    resume_skills = resume_data["skills"]
    resume_text = resume_data.get("text", "")
    print("🔍 Extracted resume skills:", resume_skills)
    
    # Scrape internships from multiple sources
    print("🌐 Starting job scraping...")
    jobs = scrape_all_company_sites(keyword="software engineering intern")
    print(f"📋 Total jobs scraped: {len(jobs)}")
    
    if len(jobs) == 0:
        print("❌ No jobs were scraped - this is the problem!")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "results": []
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
        "results": matched_jobs
    })

#!/usr/bin/env python3

from job_scrapers.scrape_github_internships import scrape_github_internships
from matching.matcher import match_job_to_resume, extract_skills_from_text

def test_github_only():
    print("Testing GitHub internships scraper only...")
    
    # Simulate a computer science student's resume
    resume_skills = ['Python', 'Java', 'Computer Science', 'Programming', 'Software Engineering']
    
    # Get jobs from GitHub scraper only
    jobs = scrape_github_internships('intern', max_results=10)
    print(f"Found {len(jobs)} jobs from GitHub")
    
    print("\nTesting skill matching:")
    technical_jobs = []
    business_jobs = []
    
    for job in jobs:
        score = match_job_to_resume(job, resume_skills)
        title = job.get('title', 'Unknown')
        company = job.get('company', 'Unknown')
        location = job.get('location', 'Unknown')
        
        print(f"  {title} at {company} - {location} - Score: {score}")
        
        if score > 0:
            technical_jobs.append((title, company, score))
        else:
            business_jobs.append((title, company, score))
    
    print(f"\n✅ Technical jobs (score > 0): {len(technical_jobs)}")
    for title, company, score in technical_jobs:
        print(f"  - {title} at {company} - Score: {score}")
    
    print(f"\n❌ Business jobs (score = 0): {len(business_jobs)}")
    for title, company, score in business_jobs:
        print(f"  - {title} at {company} - Score: {score}")

if __name__ == "__main__":
    test_github_only() 
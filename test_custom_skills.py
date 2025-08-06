#!/usr/bin/env python3

from job_scrapers.scrape_github_internships import scrape_github_internships
from matching.matcher import match_job_to_resume

def test_custom_skills():
    print("Testing GitHub scraper with custom resume skills...")
    
    # Test with different resume skills
    resume_skills = [
        'Python', 'Java', 'C++', 'JavaScript', 'React', 'Node.js', 
        'Machine Learning', 'AI', 'Computer Vision', 'Data Science',
        'Software Engineering', 'Computer Science', 'Programming'
    ]
    
    print(f"Resume skills: {resume_skills}")
    
    # Get jobs from GitHub scraper
    jobs = scrape_github_internships('intern', max_results=15)
    print(f"\nFound {len(jobs)} jobs from GitHub")
    
    print("\n=== MATCHING RESULTS ===")
    technical_jobs = []
    
    for job in jobs:
        score = match_job_to_resume(job, resume_skills)
        title = job.get('title', 'Unknown')
        company = job.get('company', 'Unknown')
        location = job.get('location', 'Unknown')
        
        # Only show jobs with score > 0
        if score > 0:
            technical_jobs.append((title, company, location, score))
            print(f"✅ {title} at {company}")
            print(f"   📍 Location: {location}")
            print(f"   🎯 Matching Score: {score}")
            print(f"   🔗 Apply: {job.get('apply_link', 'N/A')}")
            print()
    
    print(f"\n📊 SUMMARY:")
    print(f"✅ Technical jobs found: {len(technical_jobs)}")
    print(f"❌ Jobs filtered out (score = 0): {len(jobs) - len(technical_jobs)}")

if __name__ == "__main__":
    test_custom_skills() 
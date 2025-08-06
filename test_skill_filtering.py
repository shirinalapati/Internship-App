#!/usr/bin/env python3

from job_scrapers.dispatcher import scrape_all_company_sites
from matching.matcher import match_job_to_resume, extract_skills_from_text

def test_skill_filtering():
    print("Testing skill filtering for computer science resume...")
    
    # Simulate a computer science student's resume
    resume_skills = ['Python', 'Java', 'Computer Science', 'Programming', 'Software Engineering']
    
    # Get jobs from working scrapers
    jobs = scrape_all_company_sites('intern', max_results=10)
    print(f"Found {len(jobs)} total jobs")
    
    print("\nTesting skill matching:")
    technical_jobs = []
    business_jobs = []
    
    for job in jobs:
        score = match_job_to_resume(job, resume_skills)
        title = job.get('title', 'Unknown')
        company = job.get('company', 'Unknown')
        description = job.get('description', 'Unknown')
        
        # Debug: Extract skills from the actual job data
        all_text = f"{title} {description}"
        extracted_skills = extract_skills_from_text(all_text)
        
        # Debug: Check which skills match
        matched_skills = []
        for job_skill in extracted_skills:
            for resume_skill in resume_skills:
                # Check for exact match or partial match
                if (job_skill.lower() in resume_skill.lower() or 
                    resume_skill.lower() in job_skill.lower() or
                    job_skill.lower() == resume_skill.lower()):
                    matched_skills.append(job_skill)
                    break  # Don't double-count the same skill
        
        print(f"  {title} ({company}) - Score: {score}")
        print(f"    Description: {description[:100]}...")
        print(f"    Extracted skills: {extracted_skills}")
        print(f"    Matched skills: {matched_skills}")
        print(f"    Resume skills: {resume_skills}")

        if score > 0:
            technical_jobs.append((title, company, score))
        else:
            business_jobs.append((title, company, score))
    
    print(f"\n✅ Technical jobs (score > 0): {len(technical_jobs)}")
    for title, company, score in technical_jobs:
        print(f"  - {title} ({company}) - Score: {score}")
    
    print(f"\n❌ Business jobs (score = 0): {len(business_jobs)}")
    for title, company, score in business_jobs:
        print(f"  - {title} ({company}) - Score: {score}")

if __name__ == "__main__":
    test_skill_filtering() 
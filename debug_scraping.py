#!/usr/bin/env python3
"""
Debug script to test job scraping and matching pipeline.
This will help identify where the issue is occurring.
"""

import asyncio
from job_scrapers.dispatcher import scrape_jobs
from matching.matcher import match_resume_to_jobs, match_job_to_resume

async def debug_job_scraping():
    """Debug the job scraping process."""
    
    print("🔍 DEBUGGING JOB SCRAPING PIPELINE")
    print("=" * 60)
    
    # Step 1: Test job scraping
    print("\n📋 Step 1: Testing job scraping...")
    try:
        jobs = await scrape_jobs(keyword="intern", max_results=5)
        print(f"✅ Scraped {len(jobs)} jobs")
        
        if not jobs:
            print("❌ No jobs scraped - this is the problem!")
            return
        
        # Show sample jobs
        print("\n📋 Sample scraped jobs:")
        for i, job in enumerate(jobs[:3]):
            print(f"\nJob {i+1}:")
            print(f"  Company: {job.get('company', 'Unknown')}")
            print(f"  Title: {job.get('title', 'Unknown')}")
            print(f"  Location: {job.get('location', 'Unknown')}")
            print(f"  Description: {job.get('description', 'No description')}")
            print(f"  Required Skills: {job.get('required_skills', [])}")
            print(f"  Apply Link: {job.get('apply_link', 'No link')}")
            
    except Exception as e:
        print(f"❌ Job scraping failed: {e}")
        return
    
    # Step 2: Test skill extraction from jobs
    print("\n🤖 Step 2: Testing skill extraction from jobs...")
    for i, job in enumerate(jobs[:3]):
        print(f"\nJob {i+1} skill extraction:")
        try:
            from job_scrapers.scrape_github_internships import extract_skills_from_job
            extracted_skills = extract_skills_from_job(job)
            print(f"  Original skills: {job.get('required_skills', [])}")
            print(f"  LLM extracted skills: {extracted_skills}")
            
            # Update job with extracted skills
            job['required_skills'] = extracted_skills
            
        except Exception as e:
            print(f"  ❌ Skill extraction failed: {e}")
    
    # Step 3: Test matching with sample resume
    print("\n🎯 Step 3: Testing job matching...")
    sample_resume_skills = ["Python", "JavaScript", "React", "SQL", "Git"]
    sample_resume_text = "Computer Science student with experience in Python, JavaScript, and React development."
    
    print(f"Sample resume skills: {sample_resume_skills}")
    
    try:
        matched_jobs = match_resume_to_jobs(sample_resume_skills, jobs, sample_resume_text)
        print(f"✅ Matching completed: {len(matched_jobs)} jobs matched")
        
        if matched_jobs:
            print("\n🎯 Top matches:")
            for i, job in enumerate(matched_jobs[:3]):
                print(f"\nMatch {i+1}:")
                print(f"  Company: {job.get('company')}")
                print(f"  Title: {job.get('title')}")
                print(f"  Match Score: {job.get('match_score', 'No score')}")
                print(f"  Required Skills: {job.get('required_skills', [])}")
        else:
            print("❌ No matches found - investigating individual job matching...")
            
            # Test individual job matching
            for i, job in enumerate(jobs[:3]):
                print(f"\nTesting job {i+1} individually:")
                try:
                    score, description = match_job_to_resume(job, sample_resume_skills, sample_resume_text)
                    print(f"  Score: {score}")
                    print(f"  Description: {description[:200]}...")
                except Exception as e:
                    print(f"  ❌ Individual matching failed: {e}")
                    
    except Exception as e:
        print(f"❌ Job matching failed: {e}")

def test_github_scraper_directly():
    """Test the GitHub scraper directly."""
    
    print("\n🔍 TESTING GITHUB SCRAPER DIRECTLY")
    print("=" * 60)
    
    try:
        from job_scrapers.scrape_github_internships import scrape_github_internships
        
        print("📋 Testing GitHub internships scraper...")
        jobs = scrape_github_internships(keyword="intern", max_results=5)
        
        print(f"✅ Direct scraper returned {len(jobs)} jobs")
        
        if jobs:
            print("\n📋 Sample job from direct scraper:")
            job = jobs[0]
            for key, value in job.items():
                print(f"  {key}: {value}")
        else:
            print("❌ Direct scraper returned no jobs")
            
    except Exception as e:
        print(f"❌ Direct scraper failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Starting Scraping Debug Session")
    print("=" * 60)
    
    # Test direct scraper first
    test_github_scraper_directly()
    
    # Test full pipeline
    asyncio.run(debug_job_scraping())
    
    print("\n✅ Debug session completed!")
    print("\n🎯 SUMMARY:")
    print("1. Check if jobs are being scraped")
    print("2. Check if skills are being extracted from jobs") 
    print("3. Check if matching logic is working")
    print("4. Identify the exact point of failure")

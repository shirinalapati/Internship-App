from resume_parser.parse_resume import parse_resume
from job_scrapers.dispatcher import scrape_all_company_sites
from matching.matcher import match_job_to_resume
from email_sender.generate_email import generate_email


def main():
    resume = parse_resume("data/Murali Resume.png")
    resume_skills = resume["skills"]
    print("✅ Parsed Resume Skills:", resume_skills)

    jobs = scrape_all_company_sites(keyword="software engineering intern")
    print(f"\n🔍 Found {len(jobs)} job(s). With match scores:\n")

    for job in jobs:
        score = match_job_to_resume(job, resume_skills)
        print(f"- {job['title']} at {job['company']} ({job['location']})")
        print(f"  Match Score: {score}%")
        print(f"  Link: {job['apply_link']}\n")
        # Removed email preview generation and print
        print("-" * 40)

if __name__ == "__main__":
    main() 
    
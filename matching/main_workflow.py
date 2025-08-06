# main_workflow.py

resume_data = prepare_resume_node("data/resume.pdf")
profile = get_user_profile_node(resume_data)
jobs = get_scraped_jobs_node(keyword="software engineering intern")
results = llm_processing_node(profile, jobs)

# Print results
for job in results:
    print(f"{job['title']} at {job['company']} ({job['location']}) - Match Score: {job['match_score']}%")
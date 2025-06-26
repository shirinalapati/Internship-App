def generate_email(job, resume_skills, applicant_name="Shirin"):
    title = job["title"]
    company = job["company"]
    job_skills = job.get("required_skills", [])

    matched_skills = [
        skill for skill in job_skills
        if skill.lower() in [r.lower() for r in resume_skills]
    ]

    body = f"""Dear Hiring Team at {company},

I am writing to express my interest in the {title} position. Based on the description, I believe my background aligns well with the role — particularly my experience with {', '.join(matched_skills)}.

I’ve attached my resume and would welcome the opportunity to contribute to {company}'s team. Thank you for your consideration.

Best regards,  
{applicant_name}
"""
    return body

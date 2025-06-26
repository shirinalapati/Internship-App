def match_job_to_resume(job, resume_skills):
    job_skills = job.get("required_skills", [])
    if not job_skills:
        return 0  # can't match with no skill data

    matched = [
        skill for skill in job_skills
        if skill.lower() in [r.lower() for r in resume_skills]
    ]
    score = round(100 * len(matched) / len(job_skills))
    return score

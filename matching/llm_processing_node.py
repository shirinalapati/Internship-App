# llm_processing_node.py

from matching.matcher import match_job_to_resume

def llm_processing_node(profile, jobs):
    """
    Matches jobs to the user's profile using your existing matcher.
    Returns a list of jobs with match scores.
    """
    results = []
    for job in jobs:
        score = match_job_to_resume(job, profile["skills"])
        job_with_score = job.copy()
        job_with_score["match_score"] = score
        results.append(job_with_score)
    return results
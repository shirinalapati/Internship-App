#!/usr/bin/env python3

from matching.matcher import match_job_to_resume, extract_skills_from_text

def test_simple_matching():
    print("Testing simple skill matching...")
    
    # Test resume skills
    resume_skills = ['Python', 'Java', 'Computer Science', 'Programming', 'Software Engineering']
    print(f"Resume skills: {resume_skills}")
    
    # Test job 1: Google Student Researcher
    job1 = {
        "title": "Student Researcher, BS/MS, Fall 2025",
        "description": "Currently enrolled in a Bachelor's or Master's degree in Computer Science, Linguistics, Statistics, Biostatistics, Applied Mathematics, Operations Research, Economics, Natural Sciences, or related technical field.",
        "required_skills": []
    }
    
    # Test job 2: Meta Research Scientist
    job2 = {
        "title": "Research Scientist Intern, Holography & Material (PhD)",
        "description": "Research position in holography and material science.",
        "required_skills": []
    }
    
    # Extract skills from job descriptions
    job1_skills = extract_skills_from_text(f"{job1['title']} {job1['description']}")
    job2_skills = extract_skills_from_text(f"{job2['title']} {job2['description']}")
    
    print(f"\nJob 1 skills extracted: {job1_skills}")
    print(f"Job 2 skills extracted: {job2_skills}")
    
    # Test matching
    score1 = match_job_to_resume(job1, resume_skills)
    score2 = match_job_to_resume(job2, resume_skills)
    
    print(f"\nJob 1 score: {score1}")
    print(f"Job 2 score: {score2}")

if __name__ == "__main__":
    test_simple_matching() 
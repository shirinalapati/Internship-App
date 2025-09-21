import re

def is_skill_match(job_skill, resume_skill):
    """
    DEPRECATED: This function used hardcoded skill synonyms.
    Now replaced with LLM-based dynamic skill matching in llm_skill_extractor.py
    
    This function is kept for backward compatibility but should not be used.
    Use match_skills_dynamically() from llm_skill_extractor instead.
    """
    # Simple fallback for backward compatibility
    return job_skill.lower().strip() == resume_skill.lower().strip()

def extract_user_experience_level(resume_skills, resume_text=""):
    """
    Extract user's experience level from resume skills and text.
    Returns: 'student', 'recent_graduate', 'entry_level', 'experienced'
    """
    resume_text_lower = resume_text.lower()
    
    # Check for student indicators
    student_indicators = [
        "student", "university", "college", "bachelor", "master", "phd", "degree",
        "graduation", "academic", "campus", "freshman", "sophomore", "junior", "senior",
        "undergraduate", "graduate", "thesis", "research", "internship", "co-op"
    ]
    
    # Check for recent graduate indicators
    recent_graduate_indicators = [
        "recent graduate", "new graduate", "entry level", "junior", "0-2 years",
        "less than 2 years", "first job", "career starter"
    ]
    
    # Check for experienced indicators
    experienced_indicators = [
        "senior", "lead", "principal", "staff", "architect", "manager", "director",
        "5+ years", "10+ years", "extensive experience", "expert", "advanced",
        "seasoned", "veteran", "leadership", "mentor", "coach", "supervise"
    ]
    
    # Check resume text for experience indicators
    for indicator in experienced_indicators:
        if indicator in resume_text_lower:
            return "experienced"
    
    for indicator in recent_graduate_indicators:
        if indicator in resume_text_lower:
            return "recent_graduate"
    
    for indicator in student_indicators:
        if indicator in resume_text_lower:
            return "student"
    
    # Default to student if no clear indicators
    return "student"

def analyze_job_requirements(job_title, job_description, required_skills):
    """
    Analyze job requirements and return qualification level and key requirements.
    """
    text = f"{job_title} {job_description}".lower()
    
    # Check for senior/experienced requirements
    senior_indicators = [
        "senior", "lead", "principal", "staff", "architect", "manager", "director",
        "10+ years", "12+ years", "15+ years", "20+ years", "extensive experience",
        "expert", "advanced", "seasoned", "veteran", "senior level", "leadership",
        "mentor", "coach", "supervise", "manage", "oversee", "strategic"
    ]
    
    # Check for entry-level indicators
    entry_level_indicators = [
        "entry level", "junior", "intern", "student", "recent graduate", "new graduate",
        "0-2 years", "less than 2 years", "first job", "career starter", "training"
    ]
    
    # Determine qualification level
    qualification_level = "mid_level"  # default
    
    for indicator in senior_indicators:
        if indicator in text:
            qualification_level = "senior"
            break
    
    for indicator in entry_level_indicators:
        if indicator in text:
            qualification_level = "entry_level"
            break
    
    # Extract experience requirements
    experience_patterns = [
        r'(\d+)\+?\s*years?\s*experience',
        r'(\d+)\+?\s*years?\s*in\s*the\s*field',
        r'(\d+)\+?\s*years?\s*of\s*development',
        r'(\d+)\+?\s*years?\s*of\s*software',
        r'(\d+)\+?\s*years?\s*of\s*programming'
    ]
    
    required_years = 0
    for pattern in experience_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                years = int(match)
                required_years = max(required_years, years)
            except ValueError:
                continue
    
    return {
        "qualification_level": qualification_level,
        "required_years": required_years,
        "required_skills": required_skills
    }

def match_job_to_resume(job, resume_skills, resume_text=""):
    """
    Match a job to resume skills with comprehensive analysis including metadata.
    Returns: (score, description)
    """
    from .metadata_matcher import (
        extract_resume_metadata, 
        extract_job_metadata, 
        calculate_metadata_match_score,
        combine_match_scores
    )
    
    job_skills = job.get("required_skills", [])
    job_title = job.get("title", "").lower()
    job_description = job.get("description", "").lower()
    
    # Extract metadata from resume and job
    resume_metadata = extract_resume_metadata(resume_skills, resume_text)
    job_metadata = extract_job_metadata(job)
    
    # Calculate metadata match score
    metadata_score, metadata_description = calculate_metadata_match_score(resume_metadata, job_metadata)
    
    # Analyze user's experience level
    user_experience = extract_user_experience_level(resume_skills, resume_text)
    
    # Analyze job requirements
    requirements = analyze_job_requirements(job_title, job_description, job_skills)
    
    # Check for senior/experienced requirements that are not suitable for interns/students
    senior_indicators = [
        "senior", "lead", "principal", "staff", "architect", "manager", "director",
        "10+ years", "12+ years", "15+ years", "20+ years", "extensive experience",
        "expert", "advanced", "seasoned", "veteran", "senior level", "leadership",
        "mentor", "coach", "supervise", "manage", "oversee", "strategic"
    ]
    
    # Check if job title or description indicates senior/experienced role
    for indicator in senior_indicators:
        if indicator in job_title or indicator in job_description:
            return 0, f"❌ This position requires senior-level experience ({indicator}). Not suitable for {user_experience} candidates."
    
    # Check for experience requirements that are too high
    if requirements["required_years"] >= 5:
        return 0, f"❌ This position requires {requirements['required_years']}+ years of experience. Too high for {user_experience} candidates."
    
    # If no skills data available, try to extract from title and description
    if not job_skills:
        # Extract skills from job title and description
        all_text = f"{job_title} {job_description}"
        job_skills = extract_skills_from_text(all_text)

    if not job_skills:
        return 0, "❌ Unable to determine required skills for this position."

    # Use dynamic LLM-based skill matching instead of hardcoded logic
    from matching.llm_skill_extractor import match_skills_dynamically
    
    print(f"🔍 Dynamic skill matching - Job skills: {job_skills}")
    print(f"🔍 Dynamic skill matching - Resume skills: {resume_skills}")
    
    # Get dynamic matches with similarity scores
    skill_matches = match_skills_dynamically(job_skills, resume_skills, threshold=0.7)
    matched_skills = [match["job_skill"] for match in skill_matches]

    if not matched_skills:
        return 0, f"❌ No matching skills found. Required: {', '.join(job_skills[:5])}. Your skills: {', '.join(resume_skills[:5])}."

    skill_score = round(100 * len(matched_skills) / len(job_skills))

    # Bonus points for strong matches
    bonus = 0
    if len(matched_skills) >= 3:
        bonus = 10
    elif len(matched_skills) >= 2:
        bonus = 5

    skill_score = min(100, skill_score + bonus)

    # Combine skill score with metadata score
    final_score = combine_match_scores(skill_score, metadata_score, skill_weight=0.7, metadata_weight=0.3)

    # Generate detailed description with both skill and metadata analysis
    skill_description = ""
    if skill_score >= 80:
        skill_description = f"✅ Excellent skill match! You have {len(matched_skills)} out of {len(job_skills)} required skills."
    elif skill_score >= 60:
        skill_description = f"✅ Good skill match! You have {len(matched_skills)} out of {len(job_skills)} required skills."
    elif skill_score >= 40:
        skill_description = f"⚠️ Moderate skill match. You have {len(matched_skills)} out of {len(job_skills)} required skills."
    elif skill_score >= 20:
        skill_description = f"⚠️ Weak skill match. You have {len(matched_skills)} out of {len(job_skills)} required skills."
    else:
        skill_description = f"❌ Poor skill match. You have {len(matched_skills)} out of {len(job_skills)} required skills."

    # Combine descriptions
    combined_description = f"{skill_description}\n\n📋 Job Requirements: {', '.join(job_skills)}\n🎯 Your matching skills: {', '.join(matched_skills)}\n\n📊 Metadata Analysis:\n{metadata_description}\n\n🎯 Final Score: {final_score}/100 (Skills: {skill_score}/100, Metadata: {metadata_score}/100)"

    return final_score, combined_description

def extract_skills_from_text(text):
    """Extract skills from text using LLM-based analysis instead of hardcoded keywords."""
    from matching.llm_skill_extractor import extract_job_skills_with_llm
    
    # Use LLM to extract skills from the text
    # Treat the text as a job description for skill extraction
    skills = extract_job_skills_with_llm("", text, "")
    
    return skills

def match_resume_to_jobs(resume_skills, jobs, resume_text=""):
    """
    Match resume skills to a list of jobs and return the best matches.
    Returns a list of jobs sorted by match score.
    """
    matched_jobs = []
    
    print(f"🎯 Starting matching process with {len(jobs)} jobs and {len(resume_skills)} resume skills")
    
    for i, job in enumerate(jobs):
        print(f"🔍 Matching job {i+1}/{len(jobs)}: {job.get('company', 'Unknown')} - {job.get('title', 'Unknown')}")
        
        score, description = match_job_to_resume(job, resume_skills, resume_text)
        
        print(f"   Score: {score}, Skills: {job.get('required_skills', [])}")
        
        # Include ALL jobs with scores (even 0) for debugging
        job_with_score = job.copy()
        job_with_score['match_score'] = score
        job_with_score['match_description'] = description
        matched_jobs.append(job_with_score)
    
    # Sort by match score in descending order
    matched_jobs.sort(key=lambda x: x['match_score'], reverse=True)
    
    print(f"🎯 Matching complete: {len(matched_jobs)} total jobs, {len([j for j in matched_jobs if j['match_score'] > 0])} with score > 0")
    
    # Return all jobs (not just matches) so we can see scores
    return matched_jobs[:10]

# resume for user ready to pass to LLM
#  get profile for user
# get scraped jobs data and pass to LLM 
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
    job_location = job.get("location", "").lower()
    
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
    
    # Add differentiation factors based on job-specific characteristics
    # This prevents all jobs with identical skills from having identical scores
    differentiation_bonus = 0
    
    # Bonus for specific job titles (more specific = better signal)
    title_lower = job_title.lower()
    if any(word in title_lower for word in ['frontend', 'backend', 'full stack', 'mobile', 'data', 'ml', 'ai', 'devops', 'cloud', 'security']):
        differentiation_bonus += 3  # Specific role mentioned
    
    # Bonus for remote/hybrid positions (highly sought after)
    if 'remote' in job_location:
        differentiation_bonus += 3
    elif 'hybrid' in job_location:
        differentiation_bonus += 2
    
    # Bonus for detailed job descriptions (quality signal)
    description_length = len(job_description)
    if description_length > 500:
        differentiation_bonus += 2
    elif description_length > 200:
        differentiation_bonus += 1
    
    # Bonus for number of specific tech keywords in job title
    tech_keywords = ['react', 'python', 'java', 'aws', 'kubernetes', 'typescript', 'node', 'angular', 'vue']
    tech_in_title = sum(1 for tech in tech_keywords if tech in title_lower)
    differentiation_bonus += min(tech_in_title * 2, 4)  # Up to 4 points
    
    # Apply differentiation bonus to final score
    skill_score = min(100, skill_score + differentiation_bonus)

    # Combine skill score with metadata score
    final_score = combine_match_scores(skill_score, metadata_score, skill_weight=0.7, metadata_weight=0.3)

    # Generate UNIQUE, PERSONALIZED description for THIS SPECIFIC JOB
    # Include company, title, and location to make each description unique
    company_name = job.get('company', 'Unknown Company')
    full_title = job.get('title', 'Unknown Position')
    location = job.get('location', 'Location not specified')
    
    # Create opening line specific to this job
    if skill_score >= 80:
        opening = f"🎯 **{company_name}** - This {full_title} position is an excellent match for your profile!"
    elif skill_score >= 60:
        opening = f"✅ **{company_name}** - This {full_title} role aligns well with your skills."
    elif skill_score >= 40:
        opening = f"⚠️ **{company_name}** - This {full_title} position is a moderate match."
    else:
        opening = f"📊 **{company_name}** - This {full_title} role has some matching elements."
    
    # Build skill match details
    skill_match_detail = f"\n\n**Your Skill Match:** {len(matched_skills)} out of {len(job_skills)} required skills"
    
    if matched_skills:
        skill_match_detail += f"\n- ✅ **Your matching skills:** {', '.join(matched_skills[:5])}"
        if len(matched_skills) > 5:
            skill_match_detail += f" (+{len(matched_skills) - 5} more)"
    
    missing_skills = [skill for skill in job_skills if skill not in matched_skills]
    if missing_skills:
        skill_match_detail += f"\n- 📚 **Skills to develop:** {', '.join(missing_skills[:3])}"
        if len(missing_skills) > 3:
            skill_match_detail += f" (+{len(missing_skills) - 3} more)"
    
    # Add location info
    location_info = f"\n\n**📍 Location:** {location}"
    
    # Add metadata insights
    metadata_info = f"\n\n**📊 Additional Insights:**\n{metadata_description}"
    
    # Add final score breakdown
    score_breakdown = f"\n\n**🎯 Match Score: {final_score}/100**\n- Skill Match: {skill_score}/100\n- Profile Compatibility: {metadata_score}/100"
    
    # Combine everything into a unique description
    combined_description = opening + skill_match_detail + location_info + metadata_info + score_breakdown

    return final_score, combined_description

def extract_skills_from_text(text):
    """Extract skills from text using LLM-based analysis instead of hardcoded keywords."""
    from matching.llm_skill_extractor import extract_job_skills_with_llm
    
    # Use LLM to extract skills from the text
    # Treat the text as a job description for skill extraction
    skills = extract_job_skills_with_llm("", text, "")
    
    return skills

def fast_job_score(job, resume_skills):
    """
    Ultra-fast job scoring for pre-filtering without LLM calls.
    Uses basic skill matching and cached job skills.
    """
    from matching.llm_skill_extractor import match_skills_dynamically, extract_job_skills_with_llm
    
    # Get job skills (uses caching)
    job_skills = job.get("required_skills", [])
    if not job_skills:
        # Only extract if not already cached
        job_skills = extract_job_skills_with_llm(
            job.get("title", ""), 
            job.get("description", ""), 
            job.get("company", "")
        )
        job["required_skills"] = job_skills  # Cache in job object
    
    if not job_skills or not resume_skills:
        return 0
    
    # Fast skill matching without LLM
    matches = match_skills_dynamically(job_skills, resume_skills, threshold=0.7)
    matched_skills = [match["job_skill"] for match in matches]
    
    if not matched_skills:
        return 0
    
    # Simple ratio-based scoring for pre-filtering
    skill_score = round(100 * len(matched_skills) / len(job_skills))
    
    # Basic bonus for good matches
    if len(matched_skills) >= 3:
        skill_score += 10
    elif len(matched_skills) >= 2:
        skill_score += 5
    
    return min(100, skill_score)

def match_resume_to_jobs(resume_skills, jobs, resume_text=""):
    """
    Two-stage intelligent job matching:
    1. Fast pre-filtering to get top 30 candidates (no LLM calls)
    2. LLM deep analysis to rank and return top 10
    """
    if not jobs:
        return []
    
    print(f"🎯 Starting two-stage matching with {len(jobs)} jobs and {len(resume_skills)} resume skills")
    
    # Stage 1: Analyze candidate profile once (cached)
    from matching.llm_skill_extractor import analyze_candidate_profile_with_llm
    
    print("🧠 Stage 1: Analyzing candidate profile...")
    candidate_profile = analyze_candidate_profile_with_llm(resume_skills, resume_text)
    
    # Stage 2: Fast pre-filtering using basic scoring (NO expensive LLM calls per job)
    print("⚡ Stage 2: Fast pre-filtering jobs...")
    matched_jobs = []
    
    for i, job in enumerate(jobs):
        if i % 100 == 0:  # Progress indicator for large datasets
            print(f"   Processing job {i+1}/{len(jobs)}")
        
        # Use fast scoring instead of full match_job_to_resume
        score = fast_job_score(job, resume_skills)
        
        # Only include jobs with non-zero scores for efficiency
        if score > 0:
            job_with_score = job.copy()
            job_with_score['match_score'] = score
            job_with_score['match_description'] = f"Pre-filtered match (score: {score})"
            matched_jobs.append(job_with_score)
    
    # Sort by match score and take top 30
    matched_jobs.sort(key=lambda x: x['match_score'], reverse=True)
    top_30_jobs = matched_jobs[:30]
    
    print(f"⚡ Pre-filtering complete: {len(matched_jobs)} matches found, analyzing top {len(top_30_jobs)}")
    
    if not top_30_jobs:
        print("❌ No matching jobs found in pre-filtering stage")
        return []
    
    # Stage 3: LLM deep ranking of top 30 to get best 10
    print("🤖 Stage 3: Deep LLM analysis and ranking...")
    from matching.llm_skill_extractor import llm_deep_ranking
    
    try:
        final_ranked_jobs = llm_deep_ranking(candidate_profile, top_30_jobs)
        
        if final_ranked_jobs:
            print(f"✅ Two-stage matching complete: Returning {len(final_ranked_jobs)} intelligently ranked jobs")
            return final_ranked_jobs
        else:
            print("⚠️ LLM ranking failed, falling back to score-based top 10")
            return top_30_jobs[:10]
            
    except Exception as e:
        print(f"❌ Error in deep ranking: {e}")
        print("🔄 Falling back to fast matching results")
        return top_30_jobs[:10]

def match_resume_to_jobs_legacy(resume_skills, jobs, resume_text=""):
    """
    LEGACY: Original one-stage matching for comparison/fallback.
    Match resume skills to a list of jobs and return the best matches.
    Returns a list of jobs sorted by match score.
    """
    matched_jobs = []
    
    print(f"🎯 Starting legacy matching process with {len(jobs)} jobs and {len(resume_skills)} resume skills")
    
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
    
    print(f"🎯 Legacy matching complete: {len(matched_jobs)} total jobs, {len([j for j in matched_jobs if j['match_score'] > 0])} with score > 0")
    
    # Return all jobs (not just matches) so we can see scores
    return matched_jobs[:10]

# resume for user ready to pass to LLM
#  get profile for user
# get scraped jobs data and pass to LLM 
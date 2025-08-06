import re

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
    Match a job to resume skills with comprehensive analysis.
    Returns: (score, description)
    """
    job_skills = job.get("required_skills", [])
    job_title = job.get("title", "").lower()
    job_description = job.get("description", "").lower()
    
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

    # Calculate skill match score
    matched_skills = []
    for job_skill in job_skills:
        for resume_skill in resume_skills:
            # Strict matching - only exact matches or very close matches
            job_skill_lower = job_skill.lower().strip()
            resume_skill_lower = resume_skill.lower().strip()
            
            # Exact match
            if job_skill_lower == resume_skill_lower:
                matched_skills.append(job_skill)
                break
            # Very close match (one is contained within the other, but not just a single letter)
            elif (len(job_skill_lower) > 2 and len(resume_skill_lower) > 2 and
                  (job_skill_lower in resume_skill_lower or resume_skill_lower in job_skill_lower)):
                # Additional check to prevent false matches like "R" matching "Engineering"
                # Only allow if the shorter skill is at least 3 characters or it's a known programming language
                shorter_skill = job_skill_lower if len(job_skill_lower) < len(resume_skill_lower) else resume_skill_lower
                longer_skill = job_skill_lower if len(job_skill_lower) > len(resume_skill_lower) else resume_skill_lower
                
                # Known programming languages and tools that are short but valid
                known_short_skills = ['r', 'go', 'c++', 'c#', 'js', 'ts', 'sql', 'aws', 'gcp', 'ai', 'ml', 'git', 'rust', 'less']
                
                # Only match if the shorter skill is at least 3 characters OR it's a known short skill
                if len(shorter_skill) >= 3 or shorter_skill in known_short_skills:
                    # Additional check: make sure it's not just a single letter matching a longer word
                    if len(shorter_skill) == 1 and len(longer_skill) > 3:
                        continue  # Skip single letter matches with longer words
                    
                    matched_skills.append(job_skill)
                    break

    if not matched_skills:
        return 0, f"❌ No matching skills found. Required: {', '.join(job_skills[:5])}. Your skills: {', '.join(resume_skills[:5])}."

    skill_score = round(100 * len(matched_skills) / len(job_skills))

    # Bonus points for strong matches
    bonus = 0
    if len(matched_skills) >= 3:
        bonus = 10
    elif len(matched_skills) >= 2:
        bonus = 5

    final_score = min(100, skill_score + bonus)

    # Generate detailed description with actual job requirements
    if final_score >= 80:
        description = f"✅ Excellent match! You have {len(matched_skills)} out of {len(job_skills)} required skills.\n\n📋 Job Requirements: {', '.join(job_skills)}\n\n🎯 Your matching skills: {', '.join(matched_skills)}\n\nPerfect for {user_experience} candidates."
    elif final_score >= 60:
        description = f"✅ Good match! You have {len(matched_skills)} out of {len(job_skills)} required skills.\n\n📋 Job Requirements: {', '.join(job_skills)}\n\n🎯 Your matching skills: {', '.join(matched_skills)}\n\nSuitable for {user_experience} candidates."
    elif final_score >= 40:
        description = f"⚠️ Moderate match. You have {len(matched_skills)} out of {len(job_skills)} required skills.\n\n📋 Job Requirements: {', '.join(job_skills)}\n\n🎯 Your matching skills: {', '.join(matched_skills)}\n\nConsider applying but may need to develop additional skills."
    elif final_score >= 20:
        description = f"⚠️ Weak match. You have {len(matched_skills)} out of {len(job_skills)} required skills.\n\n📋 Job Requirements: {', '.join(job_skills)}\n\n🎯 Your matching skills: {', '.join(matched_skills)}\n\nConsider if you're willing to learn the missing skills."
    else:
        description = f"❌ Poor match. You have {len(matched_skills)} out of {len(job_skills)} required skills.\n\n📋 Job Requirements: {', '.join(job_skills)}\n\n🎯 Your matching skills: {', '.join(matched_skills)}\n\nNot recommended for {user_experience} candidates."

    # Filter out jobs with very low scores (less than 5)
    if final_score < 5:
        return 0, "❌ Very poor match. Not recommended for your skill level."

    return final_score, description

def extract_skills_from_text(text):
    """Extract skills from text using keyword matching."""
    skill_keywords = [
        "Python", "Java", "SQL", "React", "TensorFlow", "Data Analysis", "C++", "JavaScript",
        "Computer Science", "Technical", "Programming", "Software", "Engineering", "Data", 
        "Machine Learning", "AI", "Cloud", "Leadership", "Communication", "Teamwork", 
        "Problem Solving", "Frontend", "Backend", "Full Stack", "DevOps", "Database",
        "API", "Web Development", "Mobile Development", "iOS", "Android", "Node.js",
        "Angular", "Vue.js", "Django", "Flask", "Spring", "AWS", "Azure", "GCP",
        "Docker", "Kubernetes", "Git", "Agile", "Scrum", "Testing", "QA",
        "Research", "PhD", "Holography", "Material", "Physics", "Mathematics", "Statistics",
        "Computer Vision", "Deep Learning", "Neural Networks", "Algorithms", "Data Structures",
        "Optimization", "Simulation", "Modeling", "Scientific Computing", "Numerical Analysis",
        "Student", "Researcher", "Intern", "BS", "MS", "Bachelor", "Master", "Degree",
        "Computer", "Science", "Technology", "Developer", "Engineer", "Scientist",
        "Academic", "University", "College", "Education", "Learning", "Study", "Analysis"
    ]
    found_skills = []
    for skill in skill_keywords:
        if skill.lower() in text.lower():
            found_skills.append(skill)
    return found_skills

# resume for user ready to pass to LLM
#  get profile for user
# get scraped jobs data and pass to LLM 
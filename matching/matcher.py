import re
import os
import json
from openai import OpenAI

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

def generate_llm_based_description(job, llm_analysis, resume_skills):
    """
    Generate rich career fit description based on LLM analysis data.
    This replaces the legacy match_job_to_resume description with LLM-based insights.
    """
    company_name = job.get('company', 'Unknown Company')
    full_title = job.get('title', 'Unknown Position')
    location = job.get('location', 'Location not specified')
    score = llm_analysis.get('score', 0)
    complexity = llm_analysis.get('resume_complexity', 'UNKNOWN')
    experience_match = llm_analysis.get('experience_match', 'unknown')
    skill_count = llm_analysis.get('skill_match_count', 0)
    reasoning = llm_analysis.get('reasoning', 'No analysis available')
    
    # Create opening line based on score and complexity
    if score >= 80:
        if complexity == 'ADVANCED':
            opening = f"🎯 **{company_name}** - Excellent match! This {full_title} position aligns perfectly with your advanced profile."
        else:
            opening = f"🎯 **{company_name}** - Great match! This {full_title} role is well-suited for your background."
    elif score >= 60:
        opening = f"✅ **{company_name}** - Good fit! This {full_title} position shows strong alignment with your skills."
    elif score >= 40:
        opening = f"⚠️ **{company_name}** - Moderate match. This {full_title} role has some promising elements."
    else:
        opening = f"📊 **{company_name}** - Limited match. This {full_title} position has minimal alignment."
    
    # Add LLM reasoning insights
    reasoning_section = f"\n\n**🤖 AI Analysis:** {reasoning}"
    
    # Add complexity and experience insights
    profile_section = f"\n\n**📊 Profile Match:**"
    profile_section += f"\n- Resume Complexity: **{complexity}** level"
    profile_section += f"\n- Experience Alignment: **{experience_match}**"
    
    if skill_count > 0:
        profile_section += f"\n- Skills Matched: **{skill_count}** relevant skills identified"
    
    # Add location info
    location_info = f"\n\n**📍 Location:** {location}"
    
    # Add final score with context
    score_context = f"\n\n**🎯 Match Score: {score}/100**"
    if score >= 70:
        score_context += " - **Highly Recommended**"
    elif score >= 40:
        score_context += " - **Worth Considering**"
    else :
        score_context += " - **May Not Be Ideal**"
    
    # Combine everything
    return opening + reasoning_section + profile_section + location_info + score_context

def intelligent_resume_based_scoring(job, resume_skills, resume_text=""):
    """
    LLM-based intelligent job scoring that analyzes resume complexity and candidate fit.
    This replaces rule-based scoring with AI-powered matching that considers:
    1. Resume complexity and sophistication
    2. Experience level appropriateness
    3. Skill matching quality
    4. Career trajectory alignment
    
    Returns: score (0-100)
    """
    if not resume_text or not resume_text.strip():
        print("⚠️ No resume text provided for intelligent scoring, using fallback")
        return fast_job_score_fallback(job, resume_skills)
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Prepare job information
        job_title = job.get("title", "Unknown Position")
        job_company = job.get("company", "Unknown Company")
        job_description = job.get("description", "No description available")
        job_location = job.get("location", "Location not specified")
        job_skills = job.get("required_skills", [])
        
        # Create comprehensive prompt for intelligent matching
        prompt = f"""
You are an expert **career advisor and technical resume analyst**. Your task is to evaluate how well a candidate’s resume matches a specific job opportunity.

You must output a structured JSON assessment that is **precise, consistent, and parsable**.

---

## INPUT

**CANDIDATE RESUME**
- Skills: {resume_skills}
- Text (truncated to first 2000 chars): {resume_text[:2000]}

**JOB OPPORTUNITY**
- Company: {job_company}
- Title: {job_title}
- Location: {job_location}
- Description (truncated to first 1000 chars): {job_description[:1000]}
- Required Skills: {job_skills}

---

## EVALUATION FRAMEWORK

You will assign a **final score (0–100)** using the following weighted components:

### 1. RESUME COMPLEXITY (40% weight — MOST IMPORTANT)
Evaluate the candidate’s technical and experiential sophistication.

**Advanced Resume (80–100 range):**
- Multiple technically complex projects (e.g., AI agents, distributed systems, production-grade apps)
- Work at reputable companies, startups, or internships
- Leadership, mentorship, or technical ownership experience
- Published research or open-source contributions
- Awards, hackathon wins, or recognized achievements
- Demonstrated depth (e.g., “Implemented Flask API with caching + CI/CD pipeline,” not just “used Flask”)

**Intermediate Resume (50–79 range):**
- Some real-world experience or strong personal projects
- Decent technical coverage but lacking in depth or complexity
- Limited leadership or research exposure

**Beginner Resume (0–49 range):**
- Only academic projects or class assignments
- Minimal or no professional experience
- Vague skill descriptions without technical detail
- Generic language: “Used JavaScript for websites” with no measurable output

---

### 2. EXPERIENCE LEVEL MATCHING (30% weight)
Determine if the job level matches the candidate’s level.

**Rules:**
- If job includes “senior”, “lead”, “principal”, “architect”, “manager”, “5+ years”, or “10+ years”
  AND candidate is BEGINNER or INTERMEDIATE → **Immediate disqualification (score 0)**
- Entry-level candidates → good match for intern/entry roles
- Advanced candidates → poor match for entry-level roles
- Aim for “calibrated fit”: the job should challenge but not exceed or undershoot the resume’s demonstrated level.

---

### 3. SKILL ALIGNMENT (20% weight)
Compare required job skills with resume skills.

**Evaluation criteria:**
- Count how many required skills are present AND demonstrated (not just listed)
- 0–1 overlapping skills → score 0
- 2–3 overlapping skills → acceptable (50–70)
- 4+ well-demonstrated skills → strong alignment (80–100)
- Consider relevance (e.g., “React” matches “ReactJS” but not “Vue”)

---

### 4. CAREER FIT (10% weight)
Assess whether the role aligns with the candidate’s next logical step:
- Does this job advance their current trajectory?
- Is it in the same or a natural evolution of their domain?
- Would this role reasonably leverage and expand their current skills?

---

## SCORING RULES

| Situation | Action |
|------------|---------|
| Senior-level job + beginner resume | **Return 0 (disqualified)** |
| Job requires 5+ years, resume < 2 years | **Return 0 (disqualified)** |
| <2 required skills matched | **Return 0 (disqualified)** |
| Role clearly misaligned with candidate level | **Return ≤ 30 (red flag)** |
| Poor general fit | **Return 1–40 (not recommended)** |
| Adequate fit | **Return 41–70 (reasonable)** |
| Excellent alignment | **Return 71–100 (strong recommendation)** |

---

## OUTPUT FORMAT (STRICT JSON ONLY)

Return exactly this structure:

{{
  "score": <integer 0–100>,
  "resume_complexity": "<ADVANCED | INTERMEDIATE | BEGINNER>",
  "complexity_score": <integer 0–100>,
  "experience_match": "<excellent | good | acceptable | poor | disqualified>",
  "skill_match_count": <integer>,
  "reasoning": "<1–3 concise sentences summarizing reasoning>",
  "red_flags": ["<any disqualifying issues, or empty array if none>"]
}}

---

## EXAMPLES

**Example 1: Excellent Match**
- Resume: 2 internships, built AI SaaS project, led hackathon team
- Job: Junior AI Developer (Python, Flask, ML)
- Output:
{{
  "score": 92,
  "resume_complexity": "ADVANCED",
  "complexity_score": 88,
  "experience_match": "excellent",
  "skill_match_count": 5,
  "reasoning": "Strong technical depth, 2 relevant internships, direct Python/Flask/ML experience aligns perfectly.",
  "red_flags": []
}}

**Example 2: Poor Match — Overqualified**
- Resume: Senior backend engineer, 10+ years experience
- Job: Intern software developer
- Output:
{{
  "score": 25,
  "resume_complexity": "ADVANCED",
  "complexity_score": 95,
  "experience_match": "poor",
  "skill_match_count": 4,
  "reasoning": "Candidate far exceeds role requirements; this position is below their demonstrated level.",
  "red_flags": ["Overqualified for position"]
}}

**Example 3: Disqualified — Lacks Skill Alignment**
- Resume: Web designer with HTML/CSS
- Job: Backend Engineer (Java, SQL, Spring Boot)
- Output:
{{
  "score": 0,
  "resume_complexity": "INTERMEDIATE",
  "complexity_score": 60,
  "experience_match": "disqualified",
  "skill_match_count": 0,
  "reasoning": "No overlap in required backend technologies; lacks Java or SQL experience.",
  "red_flags": ["Missing required skills"]
}}

**Example 4: Acceptable — Beginner for Entry Role**
- Resume: 2 university projects (React, Node.js)
- Job: Frontend Intern (React, HTML, CSS)
- Output:
{{
  "score": 68,
  "resume_complexity": "BEGINNER",
  "complexity_score": 45,
  "experience_match": "good",
  "skill_match_count": 3,
  "reasoning": "Beginner-level candidate matches well for entry-level React internship.",
  "red_flags": []
}}

---

## NOTES
- Keep reasoning concise and factual (avoid opinions or restating data).
- Use conservative scoring — reward clear depth, penalize vagueness.
- Never include non-JSON text in output.
"""

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert career advisor who analyzes resume complexity and job fit. You heavily weight resume sophistication when determining if a job is appropriate for a candidate. You prevent mismatches by filtering out senior roles for beginners and entry roles for advanced candidates."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,  # Low for consistency
            max_tokens=400,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        score = result.get("score", 0)
        complexity = result.get("resume_complexity", "UNKNOWN")
        reasoning = result.get("reasoning", "No reasoning provided")
        
        print(f"🤖 Intelligent Scoring: {job_company} - {job_title}")
        print(f"   Score: {score}/100 | Complexity: {complexity}")
        print(f"   Reasoning: {reasoning}")
        
        # Return full analysis object instead of just score
        return {
            "score": score,
            "resume_complexity": complexity,
            "complexity_score": result.get("complexity_score", score),
            "experience_match": result.get("experience_match", "unknown"),
            "skill_match_count": result.get("skill_match_count", 0),
            "reasoning": reasoning,
            "red_flags": result.get("red_flags", [])
        }
        
    except Exception as e:
        print(f"❌ Error in intelligent scoring for {job.get('title', 'Unknown')}: {e}")
        # Fallback to rule-based scoring if LLM fails
        fallback_score = fast_job_score_fallback(job, resume_skills)
        return {
            "score": fallback_score,
            "resume_complexity": "UNKNOWN",
            "complexity_score": fallback_score,
            "experience_match": "fallback",
            "skill_match_count": 0,
            "reasoning": "LLM analysis failed, using fallback scoring",
            "red_flags": []
        }

def fast_job_score_fallback(job, resume_skills):
    """
    Fallback rule-based scoring when LLM is unavailable.
    This is the original fast_job_score logic.
    """
    from matching.llm_skill_extractor import match_skills_dynamically, extract_job_skills_with_llm
    
    # CRITICAL: Filter out senior/experienced roles
    job_title = job.get("title", "").lower()
    job_description = job.get("description", "").lower()
    
    # Check for senior/experienced indicators
    senior_indicators = [
        "senior", "lead", "principal", "staff", "architect", "manager", "director",
        "10+ years", "12+ years", "15+ years", "20+ years", "extensive experience",
        "expert", "advanced", "seasoned", "veteran", "senior level", "leadership"
    ]
    
    for indicator in senior_indicators:
        if indicator in job_title or indicator in job_description:
            return 0
    
    # Check for high experience requirements
    experience_patterns = [
        r'(\d+)\+?\s*years?\s*(?:of\s+)?experience',
        r'(\d+)\+?\s*years?\s*(?:of\s+)?(?:software|development|programming)'
    ]
    
    for pattern in experience_patterns:
        matches = re.findall(pattern, f"{job_title} {job_description}")
        for match in matches:
            try:
                years = int(match)
                if years >= 5:
                    return 0
            except ValueError:
                continue
    
    # Get job skills
    job_skills = job.get("required_skills", [])
    if not job_skills:
        job_skills = extract_job_skills_with_llm(
            job.get("title", ""), 
            job.get("description", ""), 
            job.get("company", "")
        )
        job["required_skills"] = job_skills
    
    if not job_skills or not resume_skills:
        return 0
    
    # Fast skill matching
    matches = match_skills_dynamically(job_skills, resume_skills, threshold=0.7)
    matched_skills = [match["job_skill"] for match in matches]
    
    if len(matched_skills) < 2:
        return 0
    
    # Simple ratio-based scoring
    skill_score = round(100 * len(matched_skills) / len(job_skills))
    
    if len(matched_skills) >= 3:
        skill_score += 10
    elif len(matched_skills) >= 2:
        skill_score += 5
    
    return min(100, skill_score)

def intelligent_prefilter_jobs(jobs, resume_skills, resume_metadata, target_count=50):
    """
    Sophisticated multi-layer pre-filtering to select the best job candidates
    from the full cache for LLM analysis. Preserves accuracy while being efficient.
    """
    if len(jobs) <= target_count:
        print(f"⚡ Only {len(jobs)} jobs available, returning all for analysis")
        return jobs
    
    print(f"🔍 Pre-filtering {len(jobs)} jobs to top {target_count} candidates...")
    
    # Stage 1A: Hard requirement filtering
    experience_level = resume_metadata.get('experience_level', 'student')
    years_experience = resume_metadata.get('years_of_experience', 0)
    is_student = resume_metadata.get('is_student', True)
    
    filtered_jobs = []
    for job in jobs:
        job_title = job.get('title', '').lower()
        job_description = job.get('description', '').lower()
        
        # Filter out senior/inappropriate roles
        senior_indicators = ['senior', 'lead', 'principal', 'staff', 'architect', 'manager', 'director']
        if any(indicator in job_title for indicator in senior_indicators):
            if experience_level in ['student', 'recent_graduate'] or years_experience < 3:
                continue  # Skip senior roles for junior candidates
        
        # Filter out high experience requirements
        import re
        exp_patterns = [r'(\d+)\+?\s*years?\s*(?:of\s+)?experience', r'(\d+)\+?\s*years?\s*(?:of\s+)?(?:software|development|programming)']
        skip_job = False
        for pattern in exp_patterns:
            matches = re.findall(pattern, f"{job_title} {job_description}")
            for match in matches:
                try:
                    required_years = int(match)
                    if required_years >= 5 and years_experience < 3:
                        skip_job = True
                        break
                except ValueError:
                    continue
            if skip_job:
                break
        
        if skip_job:
            continue
            
        filtered_jobs.append(job)
    
    print(f"   After requirement filtering: {len(filtered_jobs)} jobs remain")
    
    # Stage 1B: Smart skill-based scoring
    scored_jobs = []
    for job in filtered_jobs:
        score = calculate_prefilter_score(job, resume_skills, resume_metadata)
        scored_jobs.append((job, score))
    
    # Sort by score and take top candidates
    scored_jobs.sort(key=lambda x: x[1], reverse=True)
    top_jobs = [job for job, score in scored_jobs[:target_count]]
    
    print(f"   After intelligent filtering: {len(top_jobs)} jobs selected for LLM analysis")
    return top_jobs

def calculate_prefilter_score(job, resume_skills, resume_metadata):
    """
    Calculate a preliminary score for job filtering based on multiple factors.
    """
    job_title = job.get('title', '').lower()
    job_description = job.get('description', '').lower()
    company = job.get('company', '').lower()
    location = job.get('location', '').lower()
    
    score = 0
    
    # Factor 1: Direct skill matches in job title (highest weight)
    title_skills = 0
    for skill in resume_skills:
        skill_lower = skill.lower()
        if skill_lower in job_title:
            title_skills += 15  # High bonus for skill in title
        elif any(variant in job_title for variant in [skill_lower.replace('.', ''), skill_lower.replace('js', 'javascript')]):
            title_skills += 10  # Bonus for skill variants
    
    score += min(title_skills, 45)  # Cap at 45 points
    
    # Factor 2: Skill matches in description
    description_skills = 0
    for skill in resume_skills:
        skill_lower = skill.lower()
        if skill_lower in job_description:
            description_skills += 5
        elif any(variant in job_description for variant in [skill_lower.replace('.', ''), skill_lower.replace('js', 'javascript')]):
            description_skills += 3
    
    score += min(description_skills, 25)  # Cap at 25 points
    
    # Factor 3: Domain alignment
    domain_keywords = {
        'frontend': ['frontend', 'front-end', 'react', 'angular', 'vue', 'javascript', 'html', 'css'],
        'backend': ['backend', 'back-end', 'server', 'api', 'node', 'python', 'java', 'database'],
        'fullstack': ['fullstack', 'full-stack', 'full stack'],
        'mobile': ['mobile', 'ios', 'android', 'react native', 'flutter', 'swift', 'kotlin'],
        'data': ['data', 'analytics', 'machine learning', 'ai', 'python', 'sql', 'pandas'],
        'devops': ['devops', 'cloud', 'aws', 'azure', 'docker', 'kubernetes', 'infrastructure']
    }
    
    user_domains = set()
    for domain, keywords in domain_keywords.items():
        if any(keyword.lower() in [skill.lower() for skill in resume_skills] for keyword in keywords):
            user_domains.add(domain)
    
    job_domains = set()
    job_text = f"{job_title} {job_description}"
    for domain, keywords in domain_keywords.items():
        if any(keyword in job_text for keyword in keywords):
            job_domains.add(domain)
    
    domain_overlap = len(user_domains.intersection(job_domains))
    score += domain_overlap * 8  # 8 points per domain match
    
    # Factor 4: Company quality indicators
    quality_indicators = ['google', 'microsoft', 'amazon', 'apple', 'meta', 'netflix', 'uber', 'airbnb', 'stripe', 'spotify']
    if any(indicator in company for indicator in quality_indicators):
        score += 10  # Bonus for top-tier companies
    
    # Factor 5: Remote/location preferences
    if 'remote' in location:
        score += 5  # Bonus for remote positions
    elif 'hybrid' in location:
        score += 3
    
    # Factor 6: Internship indicators
    internship_indicators = ['intern', 'internship', 'summer', 'co-op', 'new grad', 'entry level']
    if any(indicator in job_title for indicator in internship_indicators):
        score += 8  # Bonus for clearly marked internships
    
    return score

def batch_analyze_jobs_with_llm(filtered_jobs, resume_skills, resume_text, resume_metadata):
    """
    Comprehensive batch LLM analysis of pre-filtered jobs.
    Single LLM call to analyze all jobs with detailed scoring and reasoning.
    """
    if not filtered_jobs:
        return []
    
    print(f"🤖 Starting batch LLM analysis of {len(filtered_jobs)} jobs...")
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Create candidate profile summary
        experience_level = resume_metadata.get('experience_level', 'student')
        years_experience = resume_metadata.get('years_of_experience', 0)
        
        # Format jobs for batch analysis
        jobs_summary = []
        for i, job in enumerate(filtered_jobs):
            job_summary = {
                "job_id": i + 1,
                "company": job.get('company', 'Unknown'),
                "title": job.get('title', 'Unknown'),
                "location": job.get('location', 'Unknown'),
                "description": job.get('description', '')[:500]  # Limit description length
            }
            jobs_summary.append(job_summary)
        
        # Create comprehensive batch analysis prompt
        prompt = f"""You are an expert technical recruiter and career advisor who values REAL-WORLD IMPACT and PROJECT DEPTH over keyword matching.

CANDIDATE PROFILE:
Resume Skills: {resume_skills}
Experience Level: {experience_level} ({years_experience} years)
Full Resume Context: {resume_text[:1500]}

JOBS TO ANALYZE ({len(filtered_jobs)} positions):
{json.dumps(jobs_summary, indent=2)}

YOUR TASK - COMPREHENSIVE BATCH ANALYSIS:

For EACH job, provide detailed analysis using this WEIGHTED SCORING SYSTEM:

🏆 SCORING WEIGHTS (Total = 100 points):

1. **PROJECT DEPTH & REAL-WORLD IMPACT (35% - HIGHEST PRIORITY)**
   Look for evidence of:
   - ✅ PRODUCTION DEPLOYMENTS: "deployed to production", "live users", "in production"
   - ✅ REAL USER IMPACT: Actual user counts, engagement metrics, downloads, usage stats
   - ✅ TECHNICAL COMPLEXITY: System design, scalability, architecture, performance optimization
   - ✅ PROBLEM-SOLVING DEPTH: Specific technical challenges solved (not just "built a website")
   - ✅ PROJECT SCALE: Team size, codebase size, duration, iterations
   - ✅ TANGIBLE RESULTS: Revenue generated, users acquired, performance improvements (e.g., "reduced load time by 40%")
   
   🚫 IGNORE KEYWORD RESUMES: If resume just lists technologies without depth ("Built app using React, Node.js") = LOW SCORE
   ⭐ REWARD DEPTH: "Deployed React app to AWS with 500+ daily users, implemented Redis caching reducing API latency by 60%" = HIGH SCORE

2. **WORK EXPERIENCE QUALITY (25%)**
   - Real internships/jobs at actual companies >> Academic projects
   - Startup/company experience >> Side projects >> Coursework
   - Leadership roles, mentoring, team collaboration
   - Open source contributions, published work
   - Research with publications or citations

3. **SKILL ALIGNMENT WITH JOB (20%)**
   - How many DEMONSTRATED skills (not just mentioned) match the role?
   - Quality over quantity: Deep expertise in 2-3 technologies > Surface knowledge of 10
   - Consider technology stack alignment (e.g., React experience for React role)

4. **EXPERIENCE LEVEL APPROPRIATENESS (15%)**
   - Is this role suitable for candidate's level?
   - CRITICAL: Senior roles for juniors = 0 score
   - Entry-level roles for advanced candidates = lower score (they'd be bored)

5. **CAREER TRAJECTORY & GROWTH POTENTIAL (5%)**
   - Does this role advance their career?
   - Learning opportunities in the role
   - Company reputation and mentorship

📊 SCORING EXAMPLES:

HIGH SCORE (80-95):
- "Deployed full-stack e-commerce platform with 1000+ users, integrated Stripe payments, built CI/CD pipeline with GitHub Actions" → 85
- "Interned at Microsoft on Azure team, shipped feature used by 10K+ developers, reduced deployment time by 50%" → 92

MEDIUM SCORE (50-70):
- "Built multiple React projects including todo app and weather app with API integration" → 55
- "Completed 3 academic projects: database system, mobile app, web scraper" → 60

LOW SCORE (20-40):
- "Familiar with React, Node.js, Python, Java, AWS, Docker..." (just keywords, no depth) → 25
- "Course projects using various technologies" (no specifics) → 30

2. **REASONING** (2-3 sentences): Be SPECIFIC about:
   - What production/real-world experience stands out?
   - Which demonstrated skills (with depth) match this role?
   - Why this score vs higher/lower?

3. **RED_FLAGS**: Note if:
   - Resume is all keywords with no substance
   - Experience level mismatch
   - No evidence of actual deployments or real work

4. **SKILL_MATCHES**: Only list skills with DEMONSTRATED depth (not just mentioned)
5. **SKILL_GAPS**: Important skills for the role they don't show evidence of

⚠️ CRITICAL REQUIREMENTS:
- NO two jobs should have identical scores (vary based on specifics)
- HEAVILY PENALIZE keyword-only resumes without depth
- HEAVILY REWARD production deployments and real-world impact
- Value 1 production project > 10 tutorial projects
- Look for metrics, users, performance improvements, business impact
- Consider: "Would I hire this person based on proven results, not buzzwords?"

Return ONLY valid JSON:
{{
  "analysis_summary": "Overall assessment of candidate's market fit",
  "job_scores": [
    {{
      "job_id": 1,
      "company": "Company Name",
      "title": "Job Title",
      "match_score": 85,
      "reasoning": "Candidate deployed production app with 500+ users using React/Node stack matching role requirements. Demonstrated scaling and performance optimization experience. Strong fit for this full-stack internship.",
      "red_flags": [],
      "skill_matches": ["React", "Node.js", "AWS", "PostgreSQL"],
      "skill_gaps": ["TypeScript", "GraphQL"]
    }}
  ]
}}"""

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert technical recruiter who values DEMONSTRATED IMPACT over buzzwords. You heavily weight: production deployments, real users, measurable results, technical depth, and proven problem-solving. You penalize keyword-stuffed resumes without substance. You ensure scoring diversity by carefully weighing each candidate's real-world accomplishments."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,  # Some creativity for diverse scoring
            max_tokens=4000,   # Large response for comprehensive analysis
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        job_scores = result.get("job_scores", [])
        
        print(f"✅ Batch LLM analysis complete: {len(job_scores)} jobs analyzed")
        print(f"📊 Score range: {min([j['match_score'] for j in job_scores])}-{max([j['match_score'] for j in job_scores])}")
        
        return job_scores
        
    except Exception as e:
        print(f"❌ Error in batch LLM analysis: {e}")
        
        # Fallback: use enhanced rule-based scoring
        print("🔄 Using enhanced fallback scoring...")
        fallback_scores = []
        for i, job in enumerate(filtered_jobs):
            fallback_score = fast_job_score_fallback(job, resume_skills)
            fallback_scores.append({
                "job_id": i + 1,
                "company": job.get('company', 'Unknown'),
                "title": job.get('title', 'Unknown'),
                "match_score": fallback_score,
                "reasoning": f"Fallback analysis - {fallback_score}% skill match",
                "red_flags": [],
                "skill_matches": [],
                "skill_gaps": []
            })
        
        return fallback_scores

def enhance_batch_results(llm_scores, original_jobs, resume_skills=None):
    """
    Enhance LLM batch results with original job data and create rich descriptions.
    """
    enhanced_jobs = []
    
    for score_data in llm_scores:
        job_id = score_data.get("job_id", 1) - 1  # Convert to 0-based index
        
        if job_id < len(original_jobs):
            original_job = original_jobs[job_id]
            
            # Create enhanced job object
            enhanced_job = original_job.copy()
            enhanced_job['match_score'] = score_data.get('match_score', 0)
            
            # Create rich AI reasoning object with meaningful data
            match_score = score_data.get('match_score', 0)
            skill_matches = score_data.get('skill_matches', [])
            skill_gaps = score_data.get('skill_gaps', [])
            reasoning = score_data.get('reasoning', '').lower()
            
            # Fallback: If LLM didn't provide skill matches/gaps, extract them manually
            if not skill_matches and not skill_gaps:
                job_skills = original_job.get('required_skills', [])
                if job_skills and resume_skills:
                    # Use dynamic skill matching to get actual matches
                    try:
                        from matching.llm_skill_extractor import match_skills_dynamically
                        # Get real skill matches using the dynamic matching system
                        matches = match_skills_dynamically(job_skills, resume_skills, threshold=0.7)
                        skill_matches = [match["job_skill"] for match in matches]
                        
                        # Skills that weren't matched are gaps
                        skill_gaps = [skill for skill in job_skills if skill not in skill_matches]
                    except:
                        # Final fallback based on score
                        if match_score > 0:
                            # If there's a score > 0, assume some matches exist
                            skill_matches = job_skills[:min(2, len(job_skills))]
                            skill_gaps = job_skills[len(skill_matches):]
                        else:
                            # No matches, all skills are gaps
                            skill_matches = []
                            skill_gaps = job_skills[:5]  # Limit to 5 for display
                elif job_skills:
                    # No resume skills available, treat all job skills as gaps
                    skill_matches = []
                    skill_gaps = job_skills[:5]  # Limit to 5 for display
            
            # Determine resume complexity based on score, skills, AND real-world impact indicators
            # Look for production/impact keywords in the reasoning
            production_indicators = [
                'production', 'deployed', 'users', 'live', 'published', 'shipped',
                'performance', 'scale', 'optimization', 'real-world', 'impact',
                'metrics', 'revenue', 'intern', 'company', 'team', 'enterprise'
            ]
            
            impact_count = sum(1 for indicator in production_indicators if indicator in reasoning)
            
            # Advanced: High score + many skills + production impact
            if match_score >= 75 and len(skill_matches) >= 4 and impact_count >= 2:
                resume_complexity = "ADVANCED"
            # Intermediate: Good score + decent skills OR strong production impact
            elif match_score >= 60 or len(skill_matches) >= 3 or impact_count >= 3:
                resume_complexity = "INTERMEDIATE"
            else:
                resume_complexity = "ENTRY_LEVEL"
            
            # Determine experience match description based on score and impact
            if match_score >= 80:
                if impact_count >= 3:
                    experience_match = "Excellent - Proven production experience aligns perfectly"
                else:
                    experience_match = "Excellent - Your skills align perfectly with this role"
            elif match_score >= 70:
                if impact_count >= 2:
                    experience_match = "Strong - Real-world experience matches key requirements"
                else:
                    experience_match = "Strong - You have most key qualifications"
            elif match_score >= 60:
                experience_match = "Good - Solid foundation with room to grow"
            elif match_score >= 40:
                experience_match = "Moderate - Some gaps but achievable with effort"
            else:
                experience_match = "Limited - Significant skill development needed"
            
            enhanced_job['ai_reasoning'] = {
                "score": match_score,
                "resume_complexity": resume_complexity,
                "complexity_score": match_score,
                "experience_match": experience_match,
                "skill_match_count": len(skill_matches),
                "reasoning": score_data.get('reasoning', ''),
                "red_flags": score_data.get('red_flags', []),
                "skill_matches": skill_matches,
                "skill_gaps": skill_gaps
            }
            
            # Ensure we always have meaningful skill data for display
            if not enhanced_job['ai_reasoning']['skill_matches']:
                enhanced_job['ai_reasoning']['skill_matches'] = []
            if not enhanced_job['ai_reasoning']['skill_gaps']:
                enhanced_job['ai_reasoning']['skill_gaps'] = []
            
            # Create rich match description
            enhanced_job['match_description'] = create_rich_match_description(
                original_job, score_data, enhanced_job['ai_reasoning']
            )
            
            enhanced_jobs.append(enhanced_job)
    
    # Sort by match score
    enhanced_jobs.sort(key=lambda x: x['match_score'], reverse=True)
    
    return enhanced_jobs

def create_rich_match_description(job, score_data, ai_reasoning):
    """
    Create rich, detailed match description from LLM analysis.
    """
    company = job.get('company', 'Unknown Company')
    title = job.get('title', 'Unknown Position')
    location = job.get('location', 'Location not specified')
    score = score_data.get('match_score', 0)
    reasoning = score_data.get('reasoning', '')
    skill_matches = score_data.get('skill_matches', [])
    skill_gaps = score_data.get('skill_gaps', [])
    red_flags = score_data.get('red_flags', [])
    
    # Create opening based on score
    if score >= 80:
        opening = f"🎯 **{company}** - Excellent match! This {title} position is highly recommended for your profile."
    elif score >= 60:
        opening = f"✅ **{company}** - Strong fit! This {title} role aligns well with your background."
    elif score >= 40:
        opening = f"⚠️ **{company}** - Moderate match. This {title} position has potential but some gaps."
    else:
        opening = f"📊 **{company}** - Limited fit. This {title} role may not be ideal for your current profile."
    
    # Add AI reasoning
    ai_section = f"\n\n**🤖 AI Analysis:** {reasoning}"
    
    # Add skill analysis
    skill_section = f"\n\n**🎯 Skill Analysis:**"
    if skill_matches:
        skill_section += f"\n- ✅ **Your matching skills:** {', '.join(skill_matches)}"
    if skill_gaps:
        skill_section += f"\n- 📚 **Skills to develop:** {', '.join(skill_gaps[:3])}"
        if len(skill_gaps) > 3:
            skill_section += f" (+{len(skill_gaps) - 3} more)"
    
    # Add red flags if any
    red_flag_section = ""
    if red_flags:
        red_flag_section = f"\n\n**⚠️ Considerations:**"
        for flag in red_flags[:2]:  # Limit to 2 red flags
            red_flag_section += f"\n- {flag}"
    
    # Add location
    location_section = f"\n\n**📍 Location:** {location}"
    
    # Add final score
    score_section = f"\n\n**🎯 Match Score: {score}/100**"
    if score >= 70:
        score_section += " - **Highly Recommended**"
    elif score >= 40:
        score_section += " - **Worth Considering**"
    else:
        score_section += " - **May Not Be Ideal**"
    
    return opening + ai_section + skill_section + red_flag_section + location_section + score_section

def match_resume_to_jobs(resume_skills, jobs, resume_text=""):
    """
    Ultra-efficient 3-stage job matching with single LLM call.
    Stage 1: Pre-filter jobs (free, fast)
    Stage 2: Batch LLM analysis (single call)
    Stage 3: Enhanced results
    """
    if not jobs:
        return []
    
    print(f"🎯 Starting efficient 3-stage matching with {len(jobs)} jobs and {len(resume_skills)} resume skills")
    
    # Extract resume metadata for filtering (should already be available from parse_resume)
    resume_metadata = {
        'experience_level': extract_user_experience_level(resume_skills, resume_text),
        'years_of_experience': 0,  # Default for now, could be extracted
        'is_student': True  # Default assumption for internships
    }
    
    # STAGE 1: Intelligent Pre-filtering (FREE, <1 second)
    print("🔍 Stage 1: Pre-filtering jobs with intelligent criteria...")
    filtered_jobs = intelligent_prefilter_jobs(jobs, resume_skills, resume_metadata, target_count=50)
    
    if not filtered_jobs:
        print("❌ No jobs passed pre-filtering criteria")
        return []
    
    # STAGE 2: Batch LLM Analysis (Single LLM call, ~$0.08-0.15)
    print("🤖 Stage 2: Comprehensive batch LLM analysis...")
    llm_scores = batch_analyze_jobs_with_llm(filtered_jobs, resume_skills, resume_text, resume_metadata)
    
    if not llm_scores:
        print("❌ LLM analysis failed, using fallback")
        # Fallback to legacy approach
        return match_resume_to_jobs_legacy(resume_skills, filtered_jobs[:20], resume_text)
    
    # STAGE 3: Enhanced Results Processing
    print("✨ Stage 3: Enhancing results with rich descriptions...")
    enhanced_jobs = enhance_batch_results(llm_scores, filtered_jobs, resume_skills)
    
    # Quality assurance
    unique_scores = len(set([job['match_score'] for job in enhanced_jobs]))
    total_jobs = len(enhanced_jobs)
    diversity_ratio = unique_scores / total_jobs if total_jobs > 0 else 0
    
    print(f"✅ Efficient matching complete: {len(enhanced_jobs)} jobs analyzed")
    print(f"📊 Score diversity: {unique_scores} unique scores out of {total_jobs} jobs ({diversity_ratio:.1%})")
    print(f"💰 Cost: Single LLM call (~$0.08-0.15) vs {len(jobs)} individual calls (~${len(jobs) * 0.02:.2f})")
    
    return enhanced_jobs

def match_resume_to_jobs_legacy_fallback(resume_skills, jobs, resume_text=""):
    """
    Ultra-efficient 3-stage job matching with single LLM call - LEGACY VERSION.
    This is the old expensive approach kept for fallback.
    Uses intelligent prefiltering before LLM analysis.
    """
    if not jobs:
        return []
    
    print(f"⚠️ Using legacy expensive matching with {len(jobs)} jobs and {len(resume_skills)} resume skills")
    
    # Extract resume metadata for filtering
    resume_metadata = {
        'experience_level': extract_user_experience_level(resume_skills, resume_text),
        'years_of_experience': 0,
        'is_student': True
    }
    
    # STAGE 0: Intelligent Pre-filtering (to reduce LLM costs)
    print("🔍 Stage 0: Pre-filtering jobs with intelligent criteria...")
    filtered_jobs = intelligent_prefilter_jobs(jobs, resume_skills, resume_metadata, target_count=50)
    
    if not filtered_jobs:
        print("❌ No jobs passed pre-filtering criteria")
        return []
    
    print(f"✅ Pre-filtered to {len(filtered_jobs)} jobs from {len(jobs)} total")
    
    # Stage 1: Analyze candidate profile once (cached)
    from matching.llm_skill_extractor import analyze_candidate_profile_with_llm
    
    print("🧠 Stage 1: Analyzing candidate profile...")
    try:
        candidate_profile = analyze_candidate_profile_with_llm(resume_skills, resume_text)
    except:
        print("❌ Candidate profile analysis failed, continuing without it")
        candidate_profile = None
    
    # Stage 2: Intelligent LLM-based scoring with resume complexity analysis
    print("🤖 Stage 2: Intelligent resume-based scoring (analyzing complexity)...")
    matched_jobs = []
    
    for i, job in enumerate(filtered_jobs):
        if i % 10 == 0:  # Progress indicator (every 10 jobs since we're using LLM)
            print(f"   Processing job {i+1}/{len(filtered_jobs)}")
        
        # Use intelligent LLM-based scoring that heavily weights resume complexity
        llm_analysis = intelligent_resume_based_scoring(job, resume_skills, resume_text)
        score = llm_analysis["score"]
        
        # Generate rich description from LLM analysis data instead of calling legacy matcher
        detailed_description = generate_llm_based_description(job, llm_analysis, resume_skills)
        
        # Include ALL jobs with their scores and enhanced data
        job_with_score = job.copy()
        job_with_score['match_score'] = score
        job_with_score['ai_reasoning'] = llm_analysis
        job_with_score['match_description'] = detailed_description  # Rich LLM-based description
        matched_jobs.append(job_with_score)
    
    # Sort by match score (highest first)
    matched_jobs.sort(key=lambda x: x['match_score'], reverse=True)
    
    print(f"✅ Legacy matching complete: Returning all {len(matched_jobs)} jobs with scores")
    print(f"📊 Score distribution: {len([j for j in matched_jobs if j['match_score'] > 0])} jobs with score > 0")
    
    return matched_jobs

def match_resume_to_jobs_legacy(resume_skills, jobs, resume_text=""):
    """
    LEGACY: Original one-stage matching for comparison/fallback.
    Uses intelligent prefiltering before matching.
    Returns a list of jobs sorted by match score.
    """
    if not jobs:
        return []
    
    print(f"🎯 Starting legacy matching process with {len(jobs)} jobs and {len(resume_skills)} resume skills")
    
    # Extract resume metadata for filtering
    resume_metadata = {
        'experience_level': extract_user_experience_level(resume_skills, resume_text),
        'years_of_experience': 0,
        'is_student': True
    }
    
    # STAGE 1: Intelligent Pre-filtering (even for legacy mode)
    print("🔍 Stage 1: Pre-filtering jobs with intelligent criteria...")
    filtered_jobs = intelligent_prefilter_jobs(jobs, resume_skills, resume_metadata, target_count=50)
    
    if not filtered_jobs:
        print("❌ No jobs passed pre-filtering criteria")
        return []
    
    print(f"✅ Pre-filtered to {len(filtered_jobs)} jobs from {len(jobs)} total")
    
    # STAGE 2: Match each prefiltered job
    matched_jobs = []
    
    for i, job in enumerate(filtered_jobs):
        print(f"🔍 Matching job {i+1}/{len(filtered_jobs)}: {job.get('company', 'Unknown')} - {job.get('title', 'Unknown')}")
        
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
    
    # Return all jobs with scores for pagination and filtering
    return matched_jobs

# resume for user ready to pass to LLM
#  get profile for user
# get scraped jobs data and pass to LLM 
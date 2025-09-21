"""
LLM-based skill extraction for job descriptions.
This replaces all hardcoded skill lists with dynamic, AI-powered extraction.
"""

import os
import json
import hashlib
from openai import OpenAI
from typing import List, Dict, Any

# Simple in-memory cache for job skills to avoid re-processing
_job_skills_cache = {}

def extract_job_skills_with_llm(job_title: str, job_description: str, company: str = "") -> List[str]:
    """
    Use GPT-4o to dynamically extract required skills from job postings.
    This replaces all hardcoded skill lists with intelligent extraction.
    Includes caching to prevent timeouts.
    """
    # Create cache key from job content
    cache_key = hashlib.md5(f"{job_title}{job_description}{company}".encode()).hexdigest()
    
    # Check cache first
    if cache_key in _job_skills_cache:
        print(f"🔄 Using cached skills for job: {job_title}")
        return _job_skills_cache[cache_key]
    
    # If job description is too short, use fallback
    if len(job_description.strip()) < 50:
        print(f"⚡ Job description too short, using fast fallback for: {job_title}")
        skills = extract_job_skills_fallback(job_title, job_description)
        _job_skills_cache[cache_key] = skills
        return skills
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
You are an expert job requirements analyzer. Extract ONLY the technical and professional skills that are explicitly required or strongly preferred for this job position.

CRITICAL INSTRUCTIONS:
1. Extract skills that are ACTUALLY mentioned in the job posting
2. Focus on concrete, actionable skills (not vague terms like "good communication")
3. Include both technical skills (programming languages, tools, frameworks) and relevant soft skills
4. Use standard industry names for technologies (e.g., "JavaScript" not "JS")
5. Don't infer skills that aren't mentioned - only extract what's explicitly stated
6. Include experience levels only if specifically mentioned (e.g., "3+ years Python")

SKILL CATEGORIES TO LOOK FOR:
- Programming Languages & Technologies
- Frameworks & Libraries  
- Databases & Data Tools
- Cloud Platforms & DevOps Tools
- Development Tools & IDEs
- Methodologies (Agile, Scrum, etc.)
- Domain-specific knowledge
- Relevant soft skills (if explicitly mentioned)

Return your response as a JSON object with this exact structure:
{{
    "required_skills": [
        "skill1",
        "skill2", 
        "skill3"
    ],
    "preferred_skills": [
        "skill4",
        "skill5"
    ],
    "experience_requirements": [
        "requirement1",
        "requirement2"
    ],
    "extraction_confidence": "high/medium/low",
    "notes": "Brief explanation of extraction approach"
}}

Job Information:
Company: {company}
Title: {job_title}
Description: {job_description}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise job requirements analyzer that extracts only explicitly mentioned skills from job postings. You never hallucinate or add skills that aren't clearly stated in the job description."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Combine required and preferred skills
        all_skills = result.get("required_skills", []) + result.get("preferred_skills", [])
        
        print(f"🤖 LLM extracted {len(all_skills)} skills from job: {job_title}")
        print(f"🤖 Skills: {all_skills}")
        print(f"🤖 Confidence: {result.get('extraction_confidence', 'unknown')}")
        
        # Cache the result
        _job_skills_cache[cache_key] = all_skills
        
        return all_skills
        
    except Exception as e:
        print(f"❌ Error with LLM job skill extraction: {e}")
        print("🔄 Falling back to basic text analysis...")
        skills = extract_job_skills_fallback(job_title, job_description)
        _job_skills_cache[cache_key] = skills
        return skills

def extract_job_skills_fallback(job_title: str, job_description: str) -> List[str]:
    """
    Fallback method that uses basic text analysis when LLM fails.
    This is much more conservative than the old hardcoded approach.
    """
    import re
    
    # Only the most common, unambiguous technical terms
    common_tech_terms = [
        "Python", "Java", "JavaScript", "TypeScript", "React", "Angular", "Vue",
        "HTML", "CSS", "SQL", "Git", "Docker", "AWS", "Azure", "Node.js",
        "Machine Learning", "Data Analysis", "API", "REST", "GraphQL"
    ]
    
    text = f"{job_title} {job_description}".lower()
    found_skills = []
    
    for skill in common_tech_terms:
        # Use word boundaries to avoid partial matches
        if re.search(r'\b' + re.escape(skill.lower()) + r'\b', text):
            found_skills.append(skill)
    
    print(f"🔄 Fallback extracted {len(found_skills)} skills from job: {job_title}")
    return found_skills

def calculate_skill_similarity(skill1: str, skill2: str) -> float:
    """
    Calculate similarity between two skills using LLM.
    This replaces hardcoded synonym matching with intelligent comparison.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
Compare these two technical skills and determine if they represent the same or very similar capabilities:

Skill 1: "{skill1}"
Skill 2: "{skill2}"

Consider:
- Are they the same technology with different names? (e.g., "JS" vs "JavaScript")
- Are they closely related technologies? (e.g., "React" vs "ReactJS")
- Are they different versions of the same thing? (e.g., "Python" vs "Python3")
- Are they part of the same ecosystem? (e.g., "MySQL" vs "SQL")

Return a JSON object:
{{
    "similarity_score": 0.95,
    "are_equivalent": true,
    "reasoning": "Brief explanation"
}}

Similarity score: 0.0 (completely different) to 1.0 (identical/equivalent)
Are equivalent: true if they should be considered the same skill for job matching
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use mini for faster/cheaper similarity checks
            messages=[
                {
                    "role": "system",
                    "content": "You are a technical skill comparison expert. You understand technology relationships and can identify when different terms refer to the same or equivalent skills."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get("similarity_score", 0.0)
        
    except Exception as e:
        print(f"❌ Error calculating skill similarity: {e}")
        # Fallback to simple string comparison
        skill1_lower = skill1.lower().strip()
        skill2_lower = skill2.lower().strip()
        
        if skill1_lower == skill2_lower:
            return 1.0
        elif skill1_lower in skill2_lower or skill2_lower in skill1_lower:
            return 0.8
        else:
            return 0.0

def match_skills_dynamically(job_skills: List[str], resume_skills: List[str], threshold: float = 0.7) -> List[Dict[str, Any]]:
    """
    Dynamically match job skills to resume skills using optimized similarity matching.
    Uses fast fallback logic to prevent timeouts.
    """
    matches = []
    
    print(f"🔍 Dynamic skill matching - Job: {job_skills}, Resume: {resume_skills}")
    
    # First try fast exact and partial matching
    for job_skill in job_skills:
        best_match = None
        best_score = 0.0
        
        for resume_skill in resume_skills:
            # Fast exact match
            if job_skill.lower().strip() == resume_skill.lower().strip():
                best_match = resume_skill
                best_score = 1.0
                break
            
            # Fast partial match for common cases
            fast_score = calculate_fast_similarity(job_skill, resume_skill)
            if fast_score > best_score and fast_score >= threshold:
                best_score = fast_score
                best_match = resume_skill
        
        if best_match:
            matches.append({
                "job_skill": job_skill,
                "resume_skill": best_match,
                "similarity_score": best_score
            })
            print(f"✅ Match: {job_skill} ↔ {best_match} (score: {best_score:.2f})")
    
    return matches

def calculate_fast_similarity(skill1: str, skill2: str) -> float:
    """
    Fast similarity calculation using string matching instead of LLM.
    This prevents timeouts while still providing good matching.
    """
    skill1_lower = skill1.lower().strip()
    skill2_lower = skill2.lower().strip()
    
    # Exact match
    if skill1_lower == skill2_lower:
        return 1.0
    
    # Common synonyms (minimal hardcoded list for speed)
    synonyms = {
        'javascript': ['js', 'javascript', 'ecmascript'],
        'typescript': ['ts', 'typescript'],
        'python': ['python', 'python3', 'py'],
        'machine learning': ['ml', 'machine learning', 'ai', 'artificial intelligence'],
        'react': ['react', 'reactjs', 'react.js'],
        'node.js': ['nodejs', 'node.js', 'node'],
        'sql': ['sql', 'mysql', 'postgresql', 'postgres'],
        'git': ['git', 'github', 'version control'],
        'aws': ['aws', 'amazon web services'],
        'docker': ['docker', 'containerization'],
    }
    
    # Check synonyms
    for canonical, variants in synonyms.items():
        if skill1_lower in variants and skill2_lower in variants:
            return 0.95
    
    # Partial matching
    if len(skill1_lower) > 3 and len(skill2_lower) > 3:
        if skill1_lower in skill2_lower or skill2_lower in skill1_lower:
            shorter = skill1_lower if len(skill1_lower) < len(skill2_lower) else skill2_lower
            if len(shorter) >= 3:  # Avoid single letter matches
                return 0.8
    
    return 0.0

def extract_job_metadata_with_llm(job_title: str, job_description: str, company: str = "") -> Dict[str, Any]:
    """
    Extract job metadata (experience level, location preferences, etc.) using LLM.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
Analyze this job posting and extract key metadata for matching purposes.

EXTRACT THE FOLLOWING:
1. Experience level required (entry_level, mid_level, senior_level, student/intern)
2. Years of experience required (if mentioned)
3. Education requirements (if any)
4. Work arrangement (remote, hybrid, on-site, flexible)
5. Job type (internship, full-time, part-time, contract)
6. Industry/domain focus
7. Team size or company size hints
8. Urgency indicators

Return JSON:
{{
    "experience_level": "entry_level",
    "years_required": 2,
    "education_requirements": ["Bachelor's degree"],
    "work_arrangement": "hybrid",
    "job_type": "internship", 
    "industry": "technology",
    "urgency": "high",
    "team_size": "small",
    "extraction_confidence": "high"
}}

Job Information:
Company: {company}
Title: {job_title}
Description: {job_description}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a job posting analyzer that extracts metadata for matching purposes."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        print(f"❌ Error extracting job metadata: {e}")
        return {
            "experience_level": "entry_level",  # Default for internships
            "years_required": 0,
            "work_arrangement": "unknown",
            "job_type": "internship",
            "extraction_confidence": "low"
        }

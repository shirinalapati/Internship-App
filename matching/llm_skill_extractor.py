"""
LLM-based skill extraction for job descriptions.
This replaces all hardcoded skill lists with dynamic, AI-powered extraction.
"""

import os
import json
import hashlib
from dotenv import load_dotenv
from openai import OpenAI
from typing import List, Dict, Any

# Load environment variables from .env file
load_dotenv()

# Simple in-memory cache for job skills to avoid re-processing
_job_skills_cache = {}

def extract_job_skills_with_llm(job_title: str, job_description: str, company: str = "") -> List[str]:
    """
    Use GPT-5 to dynamically extract required skills from job postings.
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
You are an expert job requirements analyzer. Analyze this internship role and extract the SPECIFIC technical skills required.

CRITICAL INSTRUCTIONS:
1. PAY CLOSE ATTENTION to the job title - it reveals the role's focus (Frontend, Backend, Mobile, Data, Security, etc.)
2. If the job title mentions specific technologies (e.g., "React", "Python", "AWS"), ALWAYS include them
3. Infer role-specific skills based on the job title:
   - Frontend/Front-End → JavaScript, React/Angular/Vue, HTML, CSS, TypeScript
   - Backend/Back-End → Python/Java/Go, SQL, API Development, Microservices
   - Full Stack → JavaScript, Python/Java, SQL, React, Backend, Frontend
   - Mobile → Swift, Kotlin, Java, Mobile Development, iOS/Android
   - Data Scientist/Analyst → Python, SQL, Data Analysis, Machine Learning, Statistics
   - Data Engineer → Python, SQL, ETL, Data Pipelines, Spark
   - DevOps/Cloud → AWS/Azure/GCP, Docker, Kubernetes, CI/CD, Terraform
   - Security/Cybersecurity → Security, Cryptography, Network Security, Python
   - ML/AI → Python, Machine Learning, TensorFlow/PyTorch, Deep Learning
   - QA/Test → Testing, Automation, Selenium, Python/Java
4. Extract any specific technologies mentioned in the description
5. Return 5-8 concrete, specific skills (not generic terms like "programming")

Return JSON format:
{{
    "required_skills": ["skill1", "skill2", "skill3", ...],
    "role_type": "frontend/backend/fullstack/mobile/data/security/devops/general",
    "confidence": "high/medium/low"
}}

Job Information:
Company: {company}
Title: {job_title}
Description: {job_description}
"""

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You are a technical recruiter who understands what skills are needed for different software engineering roles. You infer specific technical requirements from job titles and descriptions."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,  # Slightly higher for more varied extraction
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Get required skills
        all_skills = result.get("required_skills", [])
        
        # If LLM returned too few skills or generic ones, enhance with role-based inference
        if len(all_skills) < 3 or all(skill.lower() in ['programming', 'algorithms', 'data structures'] for skill in all_skills):
            print(f"⚡ LLM skills too generic, enhancing with role-based inference...")
            role_skills = infer_skills_from_role_type(job_title, result.get("role_type", "general"))
            # Merge but prioritize LLM skills
            all_skills = list(dict.fromkeys(all_skills + role_skills))  # Remove duplicates, keep order
        
        print(f"🤖 LLM extracted {len(all_skills)} skills from job: {job_title}")
        print(f"🤖 Skills: {all_skills}")
        print(f"🤖 Role: {result.get('role_type', 'unknown')}, Confidence: {result.get('confidence', 'unknown')}")
        
        # Cache the result
        _job_skills_cache[cache_key] = all_skills
        
        return all_skills
        
    except Exception as e:
        print(f"❌ Error with LLM job skill extraction: {e}")
        print("🔄 Falling back to basic text analysis...")
        skills = extract_job_skills_fallback(job_title, job_description)
        _job_skills_cache[cache_key] = skills
        return skills

def infer_skills_from_role_type(job_title: str, role_type: str) -> List[str]:
    """
    Infer specific technical skills based on role type and job title.
    """
    title_lower = job_title.lower()
    
    # Check for specific technologies in title
    specific_tech = []
    tech_keywords = {
        'react': 'React', 'angular': 'Angular', 'vue': 'Vue',
        'python': 'Python', 'java': 'Java', 'javascript': 'JavaScript',
        'typescript': 'TypeScript', 'go': 'Go', 'rust': 'Rust',
        'c++': 'C++', 'c#': 'C#', 'swift': 'Swift', 'kotlin': 'Kotlin',
        'aws': 'AWS', 'azure': 'Azure', 'gcp': 'GCP',
        'docker': 'Docker', 'kubernetes': 'Kubernetes',
        'tensorflow': 'TensorFlow', 'pytorch': 'PyTorch',
        'sql': 'SQL', 'mongodb': 'MongoDB', 'redis': 'Redis'
    }
    
    for keyword, skill in tech_keywords.items():
        if keyword in title_lower:
            specific_tech.append(skill)
    
    # Role-based skills
    role_skills = []
    
    if 'frontend' in title_lower or 'front-end' in title_lower or 'front end' in title_lower:
        role_skills = ['JavaScript', 'React', 'HTML', 'CSS', 'TypeScript', 'Frontend Development']
    elif 'backend' in title_lower or 'back-end' in title_lower or 'back end' in title_lower:
        role_skills = ['Python', 'Java', 'SQL', 'API Development', 'Backend Development', 'REST APIs']
    elif 'full stack' in title_lower or 'fullstack' in title_lower or 'full-stack' in title_lower:
        role_skills = ['JavaScript', 'Python', 'SQL', 'React', 'Node.js', 'Full Stack Development']
    elif 'mobile' in title_lower:
        role_skills = ['Mobile Development', 'Swift', 'Kotlin', 'Java', 'iOS', 'Android']
    elif 'data scien' in title_lower or 'data analy' in title_lower:
        role_skills = ['Python', 'SQL', 'Data Analysis', 'Machine Learning', 'Statistics', 'Pandas']
    elif 'data engineer' in title_lower:
        role_skills = ['Python', 'SQL', 'ETL', 'Data Pipelines', 'Spark', 'Data Engineering']
    elif 'machine learning' in title_lower or 'ml engineer' in title_lower or ' ai ' in title_lower:
        role_skills = ['Python', 'Machine Learning', 'TensorFlow', 'PyTorch', 'Deep Learning', 'Neural Networks']
    elif 'devops' in title_lower or 'sre' in title_lower:
        role_skills = ['AWS', 'Docker', 'Kubernetes', 'CI/CD', 'Linux', 'DevOps']
    elif 'cloud' in title_lower:
        role_skills = ['AWS', 'Azure', 'Cloud Computing', 'Docker', 'Kubernetes']
    elif 'security' in title_lower or 'cybersecurity' in title_lower:
        role_skills = ['Cybersecurity', 'Network Security', 'Python', 'Security Analysis', 'Cryptography']
    elif 'qa' in title_lower or 'test' in title_lower or 'sdet' in title_lower:
        role_skills = ['Testing', 'Test Automation', 'Selenium', 'Python', 'Java', 'QA']
    elif 'embedded' in title_lower or 'firmware' in title_lower:
        role_skills = ['C++', 'C', 'Embedded Systems', 'Firmware', 'Hardware']
    elif 'ios' in title_lower:
        role_skills = ['Swift', 'iOS', 'Xcode', 'Mobile Development']
    elif 'android' in title_lower:
        role_skills = ['Kotlin', 'Java', 'Android', 'Mobile Development']
    else:
        # Generic software engineering
        role_skills = ['Programming', 'Algorithms', 'Data Structures', 'Software Development', 'Problem Solving']
    
    # Combine specific tech from title with role-based skills
    combined = specific_tech + [s for s in role_skills if s not in specific_tech]
    return combined[:8]  # Limit to 8 skills

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
You are an expert skill-matching system that compares two technical skills and determines how closely related they are.

Your goal: evaluate whether these skills represent the *same*, *similar*, or *different* capabilities in a technical or professional context.

---

### Input
Skill 1: "{skill1}"  
Skill 2: "{skill2}"

---

### Step-by-step reasoning guidelines
1. **Direct Synonyms / Aliases**
   - Example: "JS" vs "JavaScript" → identical
   - Example: "Node" vs "Node.js" → identical
   - Example: "PostgreSQL" vs "Postgres" → identical

2. **Closely Related Variants (within same technology)**
   - Example: "React" vs "ReactJS" → same framework
   - Example: "TensorFlow" vs "TensorFlow 2" → different versions
   - Example: "Python" vs "Python3" → version update
   - Example: "C++" vs "C" → not equivalent, but related language lineage

3. **Ecosystem Relationships**
   - Example: "MySQL" vs "SQL" → related (SQL is the language, MySQL is an implementation)
   - Example: "AWS Lambda" vs "Amazon Web Services" → part of same ecosystem, not equivalent
   - Example: "Pandas" vs "NumPy" → complementary but distinct libraries in Python

4. **Different / Unrelated Technologies**
   - Example: "Java" vs "JavaScript" → completely different
   - Example: "React" vs "Vue" → both frontend frameworks, but different technologies
   - Example: "Excel" vs "Python" → unrelated tools
   - Example: "Kubernetes" vs "Docker" → often used together, but distinct functions

5. **Domain Context**
   - If both are from the same *domain* (e.g., cloud, frontend, data science), reflect that in reasoning even if they aren’t equivalent.

---

### Output Format
Return a JSON object only:
{{
  "similarity_score": <float between 0.0 and 1.0>,
  "are_equivalent": <true|false>,
  "category": "<'identical' | 'similar' | 'related' | 'different'>",
  "reasoning": "<brief but precise explanation of relationship>"
}}

### Examples

**Example 1**
Skill 1: "JS"
Skill 2: "JavaScript"
Output:
{{
  "similarity_score": 1.0,
  "are_equivalent": true,
  "category": "identical",
  "reasoning": "JS is a common abbreviation for JavaScript; they are the same language."
}}

**Example 2**
Skill 1: "Python"
Skill 2: "Python3"
Output:
{{
  "similarity_score": 0.95,
  "are_equivalent": true,
  "category": "identical",
  "reasoning": "Python3 is a version of Python; both indicate the same core skill."
}}

**Example 3**
Skill 1: "MySQL"
Skill 2: "SQL"
Output:
{{
  "similarity_score": 0.7,
  "are_equivalent": false,
  "category": "related",
  "reasoning": "SQL is the language; MySQL is a database that uses it."
}}

**Example 4**
Skill 1: "Java"
Skill 2: "JavaScript"
Output:
{{
  "similarity_score": 0.1,
  "are_equivalent": false,
  "category": "different",
  "reasoning": "Despite similar names, they are unrelated languages."
}}

**Example 5**
Skill 1: "AWS Lambda"
Skill 2: "Amazon Web Services"
Output:
{{
  "similarity_score": 0.6,
  "are_equivalent": false,
  "category": "related",
  "reasoning": "AWS Lambda is a compute service within the AWS ecosystem."
}}

---

### Evaluation Criteria
- Focus on *functional similarity* — whether someone with one skill likely possesses the other.
- Give conservative equivalence: only mark `are_equivalent=true` if they clearly represent the same capability.
- Prefer short, factual reasoning (≤ 25 words).
"""

        response = client.chat.completions.create(
            model="gpt-5",  # Use mini for faster/cheaper similarity checks
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
            model="gpt-5",
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

# Simple in-memory cache for candidate profiles
_candidate_profile_cache = {}

def analyze_candidate_profile_with_llm(resume_skills: List[str], resume_text: str = "") -> Dict[str, Any]:
    """
    Analyze candidate profile once and cache the result for the session.
    This replaces repeated analysis for each job matching.
    """
    # Create cache key from resume content
    cache_key = hashlib.md5(f"{str(resume_skills)}{resume_text}".encode()).hexdigest()
    
    # Check cache first
    if cache_key in _candidate_profile_cache:
        print("🔄 Using cached candidate profile analysis")
        return _candidate_profile_cache[cache_key]
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
Analyze this candidate's profile and create a comprehensive summary for job matching.

CANDIDATE INFORMATION:
Skills: {resume_skills}
Resume Text: {resume_text}

ANALYZE AND EXTRACT:
1. Top 8-10 strongest technical skills (prioritized by proficiency/relevance)
2. Experience level (student, recent_graduate, entry_level, experienced)
3. Career interests and direction (frontend, backend, fullstack, data, mobile, etc.)
4. Learning style and adaptability indicators
5. Leadership/collaboration potential
6. Industry preferences (if any)
7. Work style preferences (startup vs big tech, remote vs office, etc.)
8. Growth potential and trajectory

Return JSON:
{{
    "top_skills": ["Python", "React", "SQL", "JavaScript", "Git"],
    "experience_level": "student",
    "career_direction": "fullstack",
    "specialization_areas": ["web development", "backend apis"],
    "learning_indicators": "strong self-learner, enjoys new technologies",
    "leadership_potential": "medium",
    "adaptability_score": "high",
    "preferred_industries": ["technology", "startups"],
    "work_style": "collaborative, prefers hands-on learning",
    "growth_trajectory": "rapid learner with strong fundamentals",
    "confidence_level": "high"
}}
"""

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert career counselor and technical recruiter who understands candidate potential and job fit."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        print(f"🤖 Analyzed candidate profile: {result.get('experience_level')} {result.get('career_direction')} developer")
        print(f"🤖 Top skills: {result.get('top_skills', [])}")
        
        # Cache the result
        _candidate_profile_cache[cache_key] = result
        
        return result
        
    except Exception as e:
        print(f"❌ Error analyzing candidate profile: {e}")
        # Fallback to basic analysis
        return {
            "top_skills": resume_skills[:8],
            "experience_level": "student",
            "career_direction": "general",
            "confidence_level": "low"
        }

def llm_deep_ranking(candidate_profile: Dict[str, Any], top_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Use LLM to intelligently rank the top 30 jobs and return the best 10.
    This replaces mechanical scoring with intelligent compatibility analysis.
    """
    if not top_jobs:
        return []
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Prepare candidate summary
        candidate_summary = f"""
Experience Level: {candidate_profile.get('experience_level', 'unknown')}
Career Direction: {candidate_profile.get('career_direction', 'general')}
Top Skills: {', '.join(candidate_profile.get('top_skills', []))}
Specializations: {', '.join(candidate_profile.get('specialization_areas', []))}
Learning Style: {candidate_profile.get('learning_indicators', 'adaptable')}
Growth Potential: {candidate_profile.get('growth_trajectory', 'steady learner')}
"""
        
        # Prepare job summaries
        job_summaries = []
        for i, job in enumerate(top_jobs, 1):
            job_summary = f"{i}. {job.get('company', 'Unknown')} - {job.get('title', 'Unknown')}"
            if job.get('required_skills'):
                job_summary += f" | Skills: {', '.join(job.get('required_skills', [])[:5])}"
            if job.get('location'):
                job_summary += f" | Location: {job.get('location', 'N/A')}"
            job_summaries.append(job_summary)
        
        prompt = f"""
You are an expert career counselor. Analyze this candidate and rank these job opportunities for the BEST CAREER FIT.

CANDIDATE PROFILE:
{candidate_summary}

JOB OPPORTUNITIES:
{chr(10).join(job_summaries)}

RANKING CRITERIA:
1. Skill alignment and transferability
2. Growth and learning opportunities  
3. Career trajectory fit
4. Company culture compatibility
5. Role progression potential
6. Learning curve appropriateness
7. Long-term career impact

Return JSON with top 10 jobs ranked by best fit:
{{
    "rankings": [
        {{
            "job_index": 1,
            "compatibility_score": 95,
            "reasoning": "Perfect skill match with excellent growth opportunities",
            "growth_potential": "high",
            "skill_development": "React, advanced JS patterns",
            "career_impact": "strong foundation for fullstack career"
        }},
        ...
    ],
    "overall_analysis": "This candidate shows strong potential for frontend development roles..."
}}

Focus on COMPATIBILITY and GROWTH, not just skill matching.
"""

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior career counselor and technical recruiter with deep understanding of career development and job fit."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        rankings = result.get("rankings", [])
        
        print(f"🤖 LLM deep ranking completed: {len(rankings)} jobs ranked")
        
        # Map rankings back to job objects with enhanced descriptions
        ranked_jobs = []
        for ranking in rankings[:10]:  # Top 10 only
            job_index = ranking.get("job_index", 1) - 1  # Convert to 0-based index
            
            if 0 <= job_index < len(top_jobs):
                job = top_jobs[job_index].copy()
                
                # Enhanced match description using LLM reasoning (frontend-friendly format)
                enhanced_description = f"🎯 Compatibility Score: {ranking.get('compatibility_score', 0)}/100\n\n✨ Why This Role Fits You:\n{ranking.get('reasoning', 'Good skill alignment')}\n\n🚀 Growth Opportunities:\n• Skill Development: {ranking.get('skill_development', 'Various technical skills')}\n• Career Impact: {ranking.get('career_impact', 'Valuable experience')}\n• Growth Potential: {ranking.get('growth_potential', 'Good')}\n\n📍 Location: {job.get('location', 'Not specified')}"
                
                job['match_score'] = ranking.get('compatibility_score', 0)
                job['match_description'] = enhanced_description.strip()
                ranked_jobs.append(job)
        
        print(f"✅ Returning {len(ranked_jobs)} intelligently ranked jobs")
        return ranked_jobs
        
    except Exception as e:
        print(f"❌ Error in LLM deep ranking: {e}")
        print("🔄 Falling back to score-based ranking")
        
        # Fallback: return jobs sorted by their existing match scores
        return sorted(top_jobs, key=lambda x: x.get('match_score', 0), reverse=True)[:10]

import logging
import re
import os
import json
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill vocabulary for deterministic text scanning (used by prefilter)
# ---------------------------------------------------------------------------

KNOWN_SKILLS_VOCAB = [
    'Python', 'JavaScript', 'TypeScript', 'Java', 'C++', 'C#', 'Go', 'Golang', 'Rust',
    'React', 'Next.js', 'Vue', 'Angular', 'Node.js',
    'FastAPI', 'Django', 'Flask', 'Spring',
    'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis',
    'GraphQL', 'REST APIs', 'gRPC',
    'AWS', 'GCP', 'Azure', 'Docker', 'Kubernetes',
    'Machine Learning', 'Deep Learning', 'LLM', 'RAG', 'NLP',
    'PyTorch', 'TensorFlow', 'scikit-learn',
    'Vector Databases', 'Langchain', 'Hugging Face',
    'TailwindCSS', 'CSS', 'HTML', 'Linux', 'Git', 'CI/CD',
    # Compound AI/LLM stack terms found in real JD required_skills after lazy fetch
    'Agent Development', 'Agentic Systems', 'Multi-Agent Systems',
    'LLM Applications', 'LLM Engineering', 'LLM Systems',
    'Workflow Orchestration', 'Pipeline Orchestration',
    'API Integration', 'API Development',
    'Evaluation Systems', 'Model Evaluation', 'LLM Evaluation',
    'Prompt Engineering', 'Fine-tuning', 'RLHF',
    'Model Context Protocol', 'MCP',
]

def extract_skills_from_text(text: str) -> List[str]:
    """Deterministic vocabulary scan — returns skills found verbatim in text.
    Word-boundary matched so 'Go' doesn't false-positive inside 'Django'."""
    text_lower = text.lower()
    return [s for s in KNOWN_SKILLS_VOCAB
            if re.search(r'\b' + re.escape(s.lower()) + r'\b', text_lower)]


# ---------------------------------------------------------------------------
# Module-level prompt constants (injectable for evals)
# ---------------------------------------------------------------------------

RESUME_PROFILE_SYSTEM_PROMPT = (
    "You are a conservative skills-extraction system. "
    "Your only job is to read a resume and return a compact JSON object for internal job-matching pre-filtering. "
    "The output is never shown to users — accuracy and conservatism are the only goals.\n\n"

    "OUTPUT SCHEMA (return ONLY this JSON object, no markdown, no extra keys):\n"
    '{"skills": <array of strings, max 15>, "experience_level": <exactly one of ["student","entry_level","experienced"]>, "years_of_experience": <integer>}\n\n'

    "FIELD RULES:\n"
    "skills:\n"
    "  - Include ONLY technologies demonstrated in code, projects, job titles, or listed work — not aspirational, not mentioned as absent\n"
    "  - Maximum 15 items. If the resume self-lists 20+ skills but projects demonstrate only 4, return the 4 demonstrated ones\n"
    "  - Do NOT include soft skills (communication, teamwork), editors, or operating systems\n"
    "experience_level:\n"
    '  - "student": currently enrolled in undergraduate or graduate program\n'
    '  - "entry_level": graduated within last 2 years OR has fewer than 2 years professional experience\n'
    '  - "experienced": 2+ years of professional software experience\n'
    "  - Use exactly one of those three strings — no variants like recent_graduate, junior, senior\n"
    "years_of_experience:\n"
    "  - Integer count of professional software work experience years (internships count)\n"
    "  - Return 0 if the candidate is a current student with no internship, or if unknown\n\n"

    "CRITICAL — NEGATIVE CONTEXT RULE:\n"
    "Skills mentioned as never used, not yet learned, wanted to learn, aspirational, or copied from a job posting the candidate applied to must NOT appear in the output.\n\n"

    "EXAMPLE A — negative context (hardest failure mode):\n"
    "Resume text: 'I have never used Python professionally. I want to learn React after graduation. "
    "The job posting asked for Node.js but I haven't used it.'\n"
    "WRONG output: {\"skills\": [\"Python\", \"React\", \"Node.js\"], ...}\n"
    "CORRECT output: {\"skills\": [], ...}  (none of those are demonstrated)\n\n"

    "EXAMPLE B — bloat suppression:\n"
    "Resume text: Self-lists 20 languages and frameworks in a skills section, but only projects show: "
    "a 'Hello World in Python' and 'Calculator in Java as a class assignment'.\n"
    "WRONG output: {\"skills\": [\"Python\", \"Java\", \"C\", \"C++\", \"JavaScript\", \"TypeScript\", \"Go\", \"Rust\", "
    "\"React\", \"Angular\", \"Vue\", \"Django\", \"Flask\", \"AWS\", \"Docker\", \"Kubernetes\", \"TensorFlow\", \"PyTorch\", ...], ...}\n"
    "CORRECT output: {\"skills\": [\"Python\", \"Java\"], \"experience_level\": \"student\", \"years_of_experience\": 0}\n\n"

    "Return ONLY the JSON object. No explanation, no markdown, no prose."
)

JOB_MATCH_SYSTEM_PROMPT = (
    "You are an expert technical recruiter at a top-tier software company. "
    "Your job is to objectively score internship job matches for a student candidate "
    "and explain your reasoning to the student so they understand exactly why each role fits or does not.\n\n"

    "## SCORING RUBRIC (0-100 integer)\n\n"
    "Score each job by how well THIS candidate's demonstrated experience maps to THAT specific role's requirements:\n\n"
    "- 0-30   Misaligned — fundamentally different skill set required (e.g., iOS/Swift when candidate has no mobile experience; "
    "defense/clearance roles; deep ML research when candidate builds LLM applications)\n"
    "- 31-55  Weak — some overlap but significant required skills are missing, or role type is a stretch\n"
    "- 56-74  Decent — candidate has the core skills but the role is generic or requires skills they have not demonstrated\n"
    "- 75-89  Strong — candidate has the primary stack and has shipped real production work relevant to this role\n"
    "- 90-100 Excellent — near-perfect match: candidate has the exact stack, production evidence at the right scope, "
    "and the role is clearly in their demonstrated domain\n\n"

    "SPREAD SCORES ACROSS THE FULL RANGE. Do NOT cluster everything between 60-80. "
    "A clearly wrong role (mobile-only for a full-stack/AI candidate) MUST score below 40. "
    "A near-perfect match MUST score above 80.\n\n"

    "## RANKING DISCRIMINATION EXAMPLES\n\n"
    "Candidate profile: Python + React + TypeScript + FastAPI + Claude API + production deployments at a YC startup.\n\n"
    "WRONG — scores bunched, no differentiation:\n"
    '  {"job_id": 1, "match_score": 68, ...}  // Full-stack React+Python role\n'
    '  {"job_id": 2, "match_score": 65, ...}  // iOS Swift-only role\n'
    '  {"job_id": 3, "match_score": 63, ...}  // ML research/PyTorch/TensorFlow role\n\n'
    "CORRECT — scores discriminate clearly:\n"
    '  {"job_id": 1, "match_score": 84, ...}  // Full-stack React+Python — candidate ships exactly this\n'
    '  {"job_id": 2, "match_score": 28, ...}  // iOS Swift-only — candidate has zero Swift/Kotlin experience\n'
    '  {"job_id": 3, "match_score": 32, ...}  // ML research — candidate uses LLM APIs, does not train models\n\n'
    "DOMAIN DISTINCTIONS — score lower for domain mismatch even when both say 'AI':\n"
    "- LLM/AI application work (Claude API, RAG, agents, prompt engineering) IS NOT the same as:\n"
    "  ML research (PyTorch, TensorFlow, model training, CUDA), Data ML (Spark, Hadoop, pipelines),\n"
    "  or DevOps/infrastructure (K8s, CI/CD, cloud ops)\n"
    "- Read the job title carefully when the description is generic. "
    "'ML model training' in a title signals research; 'AI agents' or 'LLM' signals application work.\n\n"

    "## REASONING QUALITY — USER-FACING (CRITICAL)\n\n"
    "The `reasoning` field is shown directly to the student. It must:\n"
    "  1. Reference a specific project or company from the resume (e.g., 'Burnt (YC S25)', 'Internship Matcher', 'Cold Leads Agent')\n"
    "  2. Reference the specific requirement or role type from the job\n"
    "  3. Include at least one concrete metric or evidence point where available "
    "(e.g., '1,000+ orders', '95%+ accuracy', '30K+ students', '52% latency reduction')\n\n"
    "FORBIDDEN phrases: 'Good match', 'Strong candidate', 'Relevant experience', 'Demonstrated ability', "
    "'Strong technical background', 'Solid foundation', 'various technologies'\n\n"
    "BAD reasoning: 'Good match. Candidate has relevant technical skills and experience.'\n"
    "GOOD reasoning: 'Strong fit — candidate shipped production React+Python apps at Burnt (YC S25) serving 1,000+ orders "
    "and owns internshipmatcher.com, directly matching this full-stack role.'\n\n"
    "BAD reasoning: 'Candidate lacks required mobile skills.'\n"
    "GOOD reasoning: 'Poor fit — role requires Swift/iOS; candidate's entire portfolio (Burnt, Internship Matcher, "
    "Cold Leads Agent) is React+Python+FastAPI with no mobile work.'\n\n"
    "Keep reasoning to 1-2 sentences.\n\n"

    "## SKILL ACCURACY RULES\n\n"
    "skill_matches: List demonstrated skills from the resume that are relevant to this job's stack or domain. "
    "Be specific — name the actual technology (e.g., 'FastAPI', 'PostgreSQL', 'Claude API') not generic terms "
    "('backend development', 'AI experience'). Include 2-5 items per job minimum.\n\n"
    "skill_gaps: List skills that are meaningfully required by the job AND genuinely absent from the resume. "
    "Be accurate:\n"
    "- If a skill is required AND missing → include it\n"
    "- If a skill is in the resume → do NOT include it in skill_gaps\n"
    "- For generic roles with no specific requirements beyond 'programming' → use [] for skill_gaps\n"
    "- For roles in mismatched domains (iOS, ML research, DevOps) → list the primary missing domain skills\n\n"
    "WRONG: skill_gaps: ['Python', 'React'] for a candidate who has both\n"
    "WRONG: skill_gaps: ['Kubernetes'] when the role is a generic SWE internship, not infra-focused\n"
    "CORRECT: skill_gaps: ['Swift', 'iOS SDK', 'Mobile frameworks'] for an iOS-only role\n"
    "CORRECT: skill_gaps: ['PyTorch', 'CUDA', 'Model training'] for a deep-ML research role\n"
    "CORRECT: skill_gaps: [] for a Python/React full-stack role when the candidate has both\n\n"

    "## JSON CONTRACT\n\n"
    "Return ONLY valid JSON — no markdown, no extra text before or after:\n"
    "{\n"
    '  "job_scores": [\n'
    "    {\n"
    '      "job_id": 1,\n'
    '      "match_score": 82,\n'
    '      "reasoning": "Strong fit — candidate shipped React+FastAPI at Burnt (YC S25) and owns internshipmatcher.com; '
    "this role's Python+React stack maps exactly to their production work.\",\n"
    '      "skill_matches": ["Python", "React", "FastAPI"],\n'
    '      "skill_gaps": ["GraphQL"]\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "REQUIRED for every job in the XML — no missing job_ids.\n"
    "match_score: integer 0-100 (not float, not string).\n"
    "skill_matches and skill_gaps: arrays of strings (empty array [] if none).\n"
    "reasoning: string, 1-2 sentences specific to this candidate and this job."
)


def extract_json_from_response(text: str) -> str:
    """
    Extract JSON from Claude response, handling markdown code blocks.
    Returns the cleaned JSON string ready for parsing.
    """
    # Remove markdown code blocks if present
    if "```json" in text:
        # Extract content between ```json and ```
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end == -1:
            # No closing ```, likely truncated
            return text[start:].strip()
        return text[start:end].strip()
    elif "```" in text:
        # Extract content between ``` and ```
        start = text.find("```") + 3
        end = text.find("```", start)
        if end == -1:
            # No closing ```, likely truncated
            return text[start:].strip()
        return text[start:end].strip()
    # Return as-is if no code blocks
    return text.strip()


def repair_truncated_json(json_str: str) -> str:
    """
    Attempt to repair truncated or malformed JSON.
    Handles common issues like unterminated strings, missing brackets, etc.
    """
    if not json_str:
        return "{}"

    # Remove any trailing incomplete text after last complete structure
    # Find the last valid closing brace
    last_brace = json_str.rfind('}')
    last_bracket = json_str.rfind(']')

    # Determine which one comes last
    last_valid = max(last_brace, last_bracket)

    if last_valid == -1:
        # No valid closing found, this is badly truncated
        return "{}"

    # Truncate to last valid closing
    truncated = json_str[:last_valid + 1]

    # Count opening and closing braces/brackets
    open_braces = truncated.count('{')
    close_braces = truncated.count('}')
    open_brackets = truncated.count('[')
    close_brackets = truncated.count(']')

    # Add missing closing characters
    if close_braces < open_braces:
        truncated += '}' * (open_braces - close_braces)
    if close_brackets < open_brackets:
        truncated += ']' * (open_brackets - close_brackets)

    return truncated


def validate_job_score_structure(score_obj: Dict) -> bool:
    """
    Validate that a job score object has all required fields.
    Returns True if valid, False otherwise.
    """
    required_fields = ['job_id', 'company', 'title', 'match_score', 'reasoning']

    for field in required_fields:
        if field not in score_obj:
            return False

    # Validate types
    if not isinstance(score_obj['job_id'], int):
        return False
    if not isinstance(score_obj['match_score'], int):
        return False
    if not isinstance(score_obj['reasoning'], str):
        return False

    # Validate score range
    if score_obj['match_score'] < 0 or score_obj['match_score'] > 100:
        return False

    return True


def clean_and_validate_llm_response(response_text: str, expected_job_count: int) -> Dict:
    """
    Comprehensive JSON cleaning, repair, and validation.

    Args:
        response_text: Raw JSON string from LLM
        expected_job_count: Number of jobs we expect to see scores for

    Returns:
        Parsed and validated JSON dict

    Raises:
        Exception: If JSON is irreparably malformed
    """
    # Step 1: Try to parse as-is
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        # Step 2: Try to repair truncated JSON
        repaired = repair_truncated_json(response_text)

        try:
            result = json.loads(repaired)
            logger.warning(f"JSON repair succeeded (original error: line {e.lineno}, col {e.colno})")
        except json.JSONDecodeError as e2:
            logger.error(f"JSON repair failed: {e2} (original: line {e.lineno}, col {e.colno})")
            raise Exception(f"JSON is irreparably malformed: {e}")

    # Step 3: Validate structure
    if not isinstance(result, dict):
        raise Exception(f"Expected JSON object (dict), got {type(result)}")

    if "job_scores" not in result:
        raise Exception("Missing required field 'job_scores' in response")

    job_scores = result["job_scores"]

    if not isinstance(job_scores, list):
        raise Exception(f"'job_scores' should be a list, got {type(job_scores)}")

    # Step 4: Validate and clean individual job scores
    valid_scores = []
    invalid_count = 0

    for idx, score_obj in enumerate(job_scores):
        if not isinstance(score_obj, dict):
            invalid_count += 1
            continue

        if not validate_job_score_structure(score_obj):
            invalid_count += 1
            continue

        # Ensure optional fields have defaults
        if 'red_flags' not in score_obj:
            score_obj['red_flags'] = []
        if 'skill_matches' not in score_obj:
            score_obj['skill_matches'] = []
        if 'skill_gaps' not in score_obj:
            score_obj['skill_gaps'] = []

        # Ensure arrays are actually arrays
        if not isinstance(score_obj['red_flags'], list):
            score_obj['red_flags'] = []
        if not isinstance(score_obj['skill_matches'], list):
            score_obj['skill_matches'] = []
        if not isinstance(score_obj['skill_gaps'], list):
            score_obj['skill_gaps'] = []

        valid_scores.append(score_obj)

    # Update result with cleaned scores
    result["job_scores"] = valid_scores

    # Warn if missing jobs or duplicates
    issues = []
    if invalid_count:
        issues.append(f"{invalid_count} invalid")
    if len(valid_scores) < expected_job_count:
        issues.append(f"missing {expected_job_count - len(valid_scores)}")
    job_ids = [score['job_id'] for score in valid_scores]
    if len(job_ids) != len(set(job_ids)):
        issues.append("duplicate job_ids")
    if issues:
        logger.warning(f"JSON validation: {len(valid_scores)}/{expected_job_count} valid scores — {', '.join(issues)}")
    else:
        logger.info(f"JSON validation: {len(valid_scores)}/{expected_job_count} valid scores")

    return result


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
            return "entry_level"
    
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
        logger.error("No resume text provided for intelligent scoring")
        raise Exception("Resume text is required for intelligent scoring")
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        # Prepare job information
        job_title = job.get("title", "Unknown Position")
        job_company = job.get("company", "Unknown Company")
        job_description = job.get("description", "No description available")
        job_location = job.get("location", "Location not specified")
        job_skills = job.get("required_skills", [])

        # Create comprehensive prompt for intelligent matching
        prompt = f"""You are an expert **career advisor and technical resume analyst**. Your task is to evaluate how well a candidate's resume matches a specific job opportunity.

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
Evaluate the candidate's technical and experiential sophistication.

**Advanced Resume (80–100 range):**
- Multiple technically complex projects (e.g., AI agents, distributed systems, production-grade apps)
- Work at reputable companies, startups, or internships
- Leadership, mentorship, or technical ownership experience
- Published research or open-source contributions
- Awards, hackathon wins, or recognized achievements
- Demonstrated depth (e.g., "Implemented Flask API with caching + CI/CD pipeline," not just "used Flask")

**Intermediate Resume (50–79 range):**
- Some real-world experience or strong personal projects
- Decent technical coverage but lacking in depth or complexity
- Limited leadership or research exposure

**Beginner Resume (0–49 range):**
- Only academic projects or class assignments
- Minimal or no professional experience
- Vague skill descriptions without technical detail
- Generic language: "Used JavaScript for websites" with no measurable output

---

### 2. EXPERIENCE LEVEL MATCHING (30% weight)
Determine if the job level matches the candidate's level.

**Rules:**
- If job includes "senior", "lead", "principal", "architect", "manager", "5+ years", or "10+ years"
  AND candidate is BEGINNER or INTERMEDIATE → **Immediate disqualification (score 0)**
- Entry-level candidates → good match for intern/entry roles
- Advanced candidates → poor match for entry-level roles
- Aim for "calibrated fit": the job should challenge but not exceed or undershoot the resume's demonstrated level.

---

### 3. SKILL ALIGNMENT (20% weight)
Compare required job skills with resume skills.

**Evaluation criteria:**
- Count how many required skills are present AND demonstrated (not just listed)
- 0–1 overlapping skills → score 0
- 2–3 overlapping skills → acceptable (50–70)
- 4+ well-demonstrated skills → strong alignment (80–100)
- Consider relevance (e.g., "React" matches "ReactJS" but not "Vue")

---

### 4. CAREER FIT (10% weight)
Assess whether the role aligns with the candidate's next logical step:
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

Return ONLY valid JSON (no markdown, no code blocks):

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
- Never include non-JSON text in output."""

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=400,
            system="You are an expert career advisor who analyzes resume complexity and job fit. You heavily weight resume sophistication when determining if a job is appropriate for a candidate. You prevent mismatches by filtering out senior roles for beginners and entry roles for advanced candidates. Always return valid JSON only.",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        response_text = extract_json_from_response(response.content[0].text)
        result = json.loads(response_text)
        score = result.get("score", 0)
        complexity = result.get("resume_complexity", "UNKNOWN")
        reasoning = result.get("reasoning", "No reasoning provided")
        
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
        logger.error(f"Error in intelligent scoring for {job.get('title', 'Unknown')}: {e}")
        raise Exception(f"Intelligent scoring failed: {str(e)}")


def calculate_optimal_batch_size(jobs: List[Dict], resume_text: str, min_size: int = 5, max_size: int = 30) -> int:
    """
    Dynamically calculate optimal batch size based on content length.
    Prevents truncation while maximizing throughput.

    Args:
        jobs: List of job dictionaries
        resume_text: Candidate's resume text
        min_size: Minimum jobs per batch (default: 5)
        max_size: Maximum jobs per batch (default: 30)

    Returns:
        Optimal number of jobs to process in a single batch
    """
    if not jobs:
        return min_size

    # Calculate average job description length (we truncate to 500 chars in prompt)
    total_desc_length = sum(min(len(job.get('description', '')), 500) for job in jobs)
    avg_desc_length = total_desc_length / len(jobs) if jobs else 0

    # Resume context length (we truncate to 1500 chars in prompt)
    resume_context_length = min(len(resume_text), 1500)

    # Estimate tokens per job in the response (comprehensive analysis)
    # Each job analysis includes: reasoning, skill_matches, skill_gaps, red_flags
    estimated_response_tokens_per_job = 250

    # Estimate tokens per job in the prompt based on ACTUAL average description length
    # Includes: job_id, company, title, location, description
    # Convert chars to tokens (roughly 4 chars = 1 token)
    job_metadata_chars = 100  # company, title, location, job_id
    estimated_prompt_tokens_per_job = (avg_desc_length + job_metadata_chars) // 4

    # Fixed prompt overhead (instructions, examples, formatting)
    fixed_prompt_overhead = 2500  # Base prompt tokens

    # Resume overhead
    resume_overhead = resume_context_length // 4  # chars to tokens

    # Model's max output tokens (we can request up to 16000)
    max_output_tokens = 16000

    # Calculate how many jobs we can fit
    # We need to ensure: (fixed + resume + jobs*prompt_size) + (jobs*response_size) < total_budget
    total_budget = max_output_tokens
    available_for_jobs = total_budget - fixed_prompt_overhead - resume_overhead

    # Each job uses: prompt tokens + response tokens
    tokens_per_job = estimated_prompt_tokens_per_job + estimated_response_tokens_per_job

    # Ensure we don't divide by zero
    if tokens_per_job <= 0:
        tokens_per_job = 300  # Safe default

    optimal_size = int(available_for_jobs / tokens_per_job)

    # Clamp to min/max bounds
    optimal_size = max(min_size, min(optimal_size, max_size))

    # Dynamic batch sizing calculated silently

    return optimal_size


def intelligent_prefilter_jobs(jobs, resume_skills, resume_metadata, target_count=30, progress_callback=None):
    """
    Sophisticated multi-layer pre-filtering to select the best job candidates
    from the full cache for LLM analysis. Preserves accuracy while being efficient.
    Reduced to 30 jobs max to prevent LLM token limit issues.
    """
    # Send progress: Starting pre-filtering
    if progress_callback:
        progress_callback("Pre-filtering top candidates for you...")

    if len(jobs) <= target_count:
        return jobs

    # Stage 1A: Hard requirement filtering
    experience_level = resume_metadata.get('experience_level', 'student')
    years_experience = resume_metadata.get('years_of_experience', 0)
    is_student = resume_metadata.get('is_student', True)

    filtered_jobs = [
        job for job in jobs
        if _passes_hard_filters(job, experience_level, years_experience)
    ]

    # Return all filtered jobs (no hardcoded scoring)
    return filtered_jobs[:target_count]


def _passes_hard_filters(job, experience_level, years_experience) -> bool:
    """Stage 1A hard rules: senior-role and years-required exclusions.

    Shared by intelligent_prefilter_jobs and the LLM-free prefilter_and_score
    core — keep behaviour identical for both callers.
    """
    job_title = job.get('title', '').lower()
    job_description = job.get('description', '').lower()

    # Filter out senior/inappropriate roles
    senior_indicators = ['senior', 'lead', 'principal', 'staff', 'architect', 'manager', 'director']
    if any(indicator in job_title for indicator in senior_indicators):
        if experience_level in ['student', 'entry_level'] or years_experience < 3:
            return False  # Skip senior roles for junior candidates

    # Filter out high experience requirements
    import re
    exp_patterns = [r'(\d+)\+?\s*years?\s*(?:of\s+)?experience', r'(\d+)\+?\s*years?\s*(?:of\s+)?(?:software|development|programming)']
    for pattern in exp_patterns:
        matches = re.findall(pattern, f"{job_title} {job_description}")
        for match in matches:
            try:
                required_years = int(match)
                if required_years >= 5 and years_experience < 3:
                    return False
            except ValueError:
                continue

    return True


def _passes_category_filter(job, selected_ids) -> bool:
    """Hard filter: keep a job only if its canonical category is selected.

    Empty/None selection => no filtering (all jobs pass). Jobs with no
    category stamp (pre-backfill rows) pass through rather than being
    dropped — they were ingested before category stamping was added and
    should still be visible until the next scrape re-stamps them.
    See job_categories.categorize_job — category is stamped at insert time.
    """
    if not selected_ids:
        return True
    # Prefer the first-class column; fall back to metadata blob for any rows
    # that predate the column migration.
    cat = job.get('category') or (job.get('metadata') or {}).get('category')
    if not cat:
        return True  # unstamped row → don't hide it
    return cat in selected_ids


def _filter_by_categories(jobs, categories, progress_callback=None):
    """Apply the department/category hard filter up front (before any LLM work)."""
    if not categories:
        return jobs
    selected = set(categories)
    filtered = [j for j in jobs if _passes_category_filter(j, selected)]
    if progress_callback and not filtered:
        progress_callback("No jobs found in the selected departments.")
    return filtered


def batch_analyze_jobs_with_llm(filtered_jobs, resume_skills, resume_text, resume_metadata, max_jobs_per_batch=None, use_parallel=True, model="claude-sonnet-4-5-20250929", enable_caching=True, progress_callback=None):
    """
    Comprehensive batch LLM analysis of pre-filtered jobs.
    Uses dynamic batch sizing and parallel processing for maximum speed.
    Automatically retries with smaller batches if truncation detected.

    Args:
        filtered_jobs: List of jobs to analyze
        resume_skills: List of candidate skills
        resume_text: Full resume text
        resume_metadata: Candidate metadata
        max_jobs_per_batch: Override automatic batch sizing (optional)
        use_parallel: Enable parallel processing (default: True)
        model: Claude model to use - "claude-sonnet-4-5-20250929" (default, slower but better) or "claude-haiku-3-5-20241022" (10x faster)
        enable_caching: Enable prompt caching for 40-60% speed improvement (default: True)
        progress_callback: Optional callback function to report progress (takes message string)
    """
    if not filtered_jobs:
        return []

    # Calculate optimal batch size if not provided
    if max_jobs_per_batch is None:
        max_jobs_per_batch = calculate_optimal_batch_size(filtered_jobs, resume_text)

    # If we have more jobs than max_jobs_per_batch, split into chunks
    if len(filtered_jobs) > max_jobs_per_batch:
        # Create chunks
        chunks = []
        for i in range(0, len(filtered_jobs), max_jobs_per_batch):
            chunk = filtered_jobs[i:i + max_jobs_per_batch]
            chunks.append((chunk, i + 1))  # (chunk_jobs, start_id)

        total_chunks = len(chunks)

        # Send progress: Starting batch analysis
        if progress_callback:
            progress_callback(f"Running AI career analysis (batch 1 of {total_chunks})...")

        # Process chunks in parallel or sequentially
        if use_parallel and total_chunks > 1:
            all_scores = _process_chunks_parallel(chunks, resume_skills, resume_text, resume_metadata, model, enable_caching, progress_callback=progress_callback)
        else:
            all_scores = _process_chunks_sequential(chunks, resume_skills, resume_text, resume_metadata, model, enable_caching, progress_callback=progress_callback)

        return all_scores

    # Single batch processing (no chunking needed)
    # Send progress for single batch
    if progress_callback:
        progress_callback("Running AI career analysis...")

    return _analyze_single_batch(filtered_jobs, resume_skills, resume_text, resume_metadata, start_id=1, model=model, enable_caching=enable_caching)


def _process_chunks_parallel(chunks: List[tuple], resume_skills, resume_text, resume_metadata, model, enable_caching, max_workers: int = 3, progress_callback=None) -> List[Dict]:
    """
    Process multiple chunks in parallel using ThreadPoolExecutor.

    Args:
        chunks: List of (chunk_jobs, start_id) tuples
        resume_skills: Candidate skills
        resume_text: Resume text
        resume_metadata: Metadata
        model: Claude model to use
        enable_caching: Whether to enable prompt caching
        max_workers: Maximum concurrent API calls (default: 3 to respect rate limits)
        progress_callback: Optional callback function to report progress

    Returns:
        Combined list of all job scores from all chunks
    """
    all_scores = []
    total_chunks = len(chunks)
    completed_chunks = 0

    # Use ThreadPoolExecutor for parallel API calls
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all chunks for processing
        future_to_chunk = {}
        for chunk_idx, (chunk_jobs, start_id) in enumerate(chunks):
            chunk_num = chunk_idx + 1
            future = executor.submit(
                _analyze_single_batch_with_retry,
                chunk_jobs,
                resume_skills,
                resume_text,
                resume_metadata,
                start_id,
                chunk_num,
                len(chunks),
                model,
                enable_caching
            )
            future_to_chunk[future] = (chunk_num, len(chunk_jobs))

        # Collect results as they complete
        for future in as_completed(future_to_chunk):
            chunk_num, chunk_size = future_to_chunk[future]
            try:
                chunk_scores = future.result()
                all_scores.extend(chunk_scores)
                completed_chunks += 1

                # Send progress after each batch completes (skip batch 1 since it was already reported)
                if progress_callback and completed_chunks < total_chunks:
                    next_batch = completed_chunks + 1
                    progress_callback(f"Running AI career analysis (batch {next_batch} of {total_chunks})...")

            except Exception:
                # Continue processing other chunks silently
                continue

    return all_scores


def _process_chunks_sequential(chunks: List[tuple], resume_skills, resume_text, resume_metadata, model, enable_caching, progress_callback=None) -> List[Dict]:
    """
    Process chunks one at a time (fallback for when parallel fails or is disabled).

    Args:
        chunks: List of (chunk_jobs, start_id) tuples
        resume_skills: Candidate skills
        resume_text: Resume text
        resume_metadata: Metadata
        model: Claude model to use
        enable_caching: Whether to enable prompt caching
        progress_callback: Optional callback function to report progress

    Returns:
        Combined list of all job scores from all chunks
    """
    all_scores = []

    for chunk_idx, (chunk_jobs, start_id) in enumerate(chunks):
        chunk_num = chunk_idx + 1
        total_chunks = len(chunks)

        # Send progress for each batch (skip batch 1 since it was already reported)
        if progress_callback and chunk_num > 1:
            progress_callback(f"Running AI career analysis (batch {chunk_num} of {total_chunks})...")

        try:
            chunk_scores = _analyze_single_batch_with_retry(
                chunk_jobs,
                resume_skills,
                resume_text,
                resume_metadata,
                start_id,
                chunk_num,
                total_chunks,
                model,
                enable_caching
            )
            all_scores.extend(chunk_scores)
        except Exception:
            continue

    return all_scores


def _analyze_single_batch_with_retry(chunk_jobs, resume_skills, resume_text, resume_metadata, start_id, chunk_num, total_chunks, model, enable_caching, max_retries: int = 2):
    """
    Analyze a single batch with automatic retry on failure.

    Args:
        chunk_jobs: Jobs in this chunk
        resume_skills: Candidate skills
        resume_text: Resume text
        resume_metadata: Metadata
        start_id: Starting job ID for this chunk
        chunk_num: Chunk number (for logging)
        total_chunks: Total number of chunks (for logging)
        model: Claude model to use
        enable_caching: Whether to enable prompt caching
        max_retries: Maximum retry attempts

    Returns:
        List of job scores for this chunk
    """
    for attempt in range(max_retries + 1):
        try:
            chunk_scores = _analyze_single_batch(
                chunk_jobs,
                resume_skills,
                resume_text,
                resume_metadata,
                start_id,
                model,
                enable_caching
            )
            return chunk_scores
        except Exception as e:
            if attempt < max_retries:
                # Retry with smaller batch if we have retries left
                if len(chunk_jobs) > 5:
                    smaller_batch_size = max(5, len(chunk_jobs) // 2)

                    # Split and retry recursively
                    return batch_analyze_jobs_with_llm(
                        chunk_jobs,
                        resume_skills,
                        resume_text,
                        resume_metadata,
                        max_jobs_per_batch=smaller_batch_size,
                        use_parallel=False,  # Don't use parallel for retries
                        model=model,
                        enable_caching=enable_caching
                    )
                else:
                    raise
            else:
                raise


def _analyze_single_batch(filtered_jobs, resume_skills, resume_text, resume_metadata, start_id=1, model="claude-sonnet-4-5-20250929", enable_caching=True):
    """
    Internal function to analyze a single batch of jobs.
    Separated for reusability in chunking logic.

    Args:
        filtered_jobs: Jobs to analyze in this batch
        resume_skills: Candidate's skills
        resume_text: Full resume text
        resume_metadata: Candidate metadata
        start_id: Starting job ID for this batch
        model: Claude model to use (sonnet or haiku)
        enable_caching: Enable prompt caching for speed (default: True)
    """
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        # Create candidate profile summary
        experience_level = resume_metadata.get('experience_level', 'student')
        years_experience = resume_metadata.get('years_of_experience', 0)

        # Format jobs for batch analysis
        jobs_summary = []
        for i, job in enumerate(filtered_jobs):
            job_summary = {
                "job_id": start_id + i,
                "company": job.get('company', 'Unknown'),
                "title": job.get('title', 'Unknown'),
                "location": job.get('location', 'Unknown'),
                "description": job.get('description', '')[:500]  # Limit description length
            }
            jobs_summary.append(job_summary)

        # Create comprehensive batch analysis prompt
        # Use json.dumps to safely escape all strings
        candidate_profile = {
            "resume_skills": resume_skills,
            "experience_level": experience_level,
            "years_experience": years_experience,
            "resume_context": resume_text[:1500]
        }

        # Split prompt into cacheable and non-cacheable parts for prompt caching optimization

        # CACHEABLE PART 1: Static scoring instructions (same for all batches in all sessions)
        static_instructions = """For EACH job, provide detailed analysis using this WEIGHTED SCORING SYSTEM:

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

⚠️ JSON FORMAT REQUIREMENTS (CRITICAL):
- Return ONLY valid, parsable JSON
- NO markdown code blocks (no ```)
- NO extra text before or after JSON
- MUST include ALL required fields for EVERY job
- Required fields: job_id, company, title, match_score, reasoning
- Optional fields: red_flags, skill_matches, skill_gaps (provide empty arrays if none)
- Ensure proper JSON syntax: matching quotes, braces, brackets, commas
- Use double quotes (") for strings, NOT single quotes (')
- Escape special characters in strings (quotes, backslashes, newlines)
- ANALYZE ALL {len(filtered_jobs)} JOBS - do not skip any

Return ONLY this JSON structure:
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
}}

IMPORTANT: Return complete JSON for all jobs. Do not truncate or abbreviate."""

        # CACHEABLE PART 2: Candidate profile (same for all batches in this session)
        candidate_context = f"""CANDIDATE PROFILE:
{json.dumps(candidate_profile, indent=2)}

You will analyze multiple job opportunities for this candidate using the scoring system provided."""

        # NON-CACHEABLE PART: Job-specific data (changes every batch)
        jobs_prompt = f"""JOBS TO ANALYZE ({len(filtered_jobs)} positions):
{json.dumps(jobs_summary, indent=2)}

Analyze each job and return complete JSON for all {len(filtered_jobs)} jobs."""

        # Removed debug logging for cleaner output

        # Calculate max tokens with content-aware sizing
        # Account for actual content length, not just job count
        total_job_content_length = sum(len(job.get('description', '')[:500]) for job in filtered_jobs)
        avg_job_content_length = total_job_content_length / len(filtered_jobs) if filtered_jobs else 0

        # Estimate response tokens per job (comprehensive analysis with all fields)
        estimated_response_tokens_per_job = 250

        # Estimate prompt overhead
        base_prompt_tokens = 2500  # Fixed instructions
        resume_tokens = len(resume_text[:1500]) // 4  # Resume context
        job_content_tokens = total_job_content_length // 4  # Job descriptions

        # Total estimated tokens needed
        estimated_prompt_tokens = base_prompt_tokens + resume_tokens + job_content_tokens
        estimated_response_tokens = len(filtered_jobs) * estimated_response_tokens_per_job
        estimated_total = estimated_prompt_tokens + estimated_response_tokens

        # Add 20% buffer for safety
        max_tokens = min(16000, int(estimated_response_tokens * 1.2))

        # Removed verbose token allocation logging

        # Build system message with prompt caching
        if enable_caching:
            # Use structured system message with cache control for better performance
            system_message = [
                {
                    "type": "text",
                    "text": "You are an expert technical recruiter who values DEMONSTRATED IMPACT over buzzwords. You heavily weight: production deployments, real users, measurable results, technical depth, and proven problem-solving. You penalize keyword-stuffed resumes without substance. You ensure scoring diversity by carefully weighing each candidate's real-world accomplishments. CRITICAL: Always return ONLY valid, complete, parsable JSON with no markdown formatting, no code blocks, and no extra text. Include ALL required fields for EVERY job analyzed. Never truncate or abbreviate your response.",
                    "cache_control": {"type": "ephemeral"}  # Cache system instructions
                },
                {
                    "type": "text",
                    "text": static_instructions,
                    "cache_control": {"type": "ephemeral"}  # Cache scoring criteria
                },
                {
                    "type": "text",
                    "text": candidate_context,
                    "cache_control": {"type": "ephemeral"}  # Cache candidate profile
                }
            ]
            pass  # Caching enabled silently
        else:
            # Fallback to simple string system message (no caching)
            system_message = f"You are an expert technical recruiter who values DEMONSTRATED IMPACT over buzzwords. You heavily weight: production deployments, real users, measurable results, technical depth, and proven problem-solving. You penalize keyword-stuffed resumes without substance. You ensure scoring diversity by carefully weighing each candidate's real-world accomplishments. CRITICAL: Always return ONLY valid, complete, parsable JSON with no markdown formatting, no code blocks, and no extra text. Include ALL required fields for EVERY job analyzed. Never truncate or abbreviate your response.\n\n{static_instructions}\n\n{candidate_context}"

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_message,
            messages=[
                {
                    "role": "user",
                    "content": jobs_prompt  # Only job-specific data in user message
                }
            ]
        )

        # Process LLM response
        raw_response = response.content[0].text

        # Check if response was truncated
        if response.stop_reason == "max_tokens":
            raise Exception(f"Response truncated - reduce batch size from {len(filtered_jobs)} jobs")

        # Extract JSON from response
        response_text = extract_json_from_response(raw_response)

        # Clean, repair, and validate JSON
        try:
            result = clean_and_validate_llm_response(response_text, len(filtered_jobs))
        except Exception as validation_error:
            # This is likely truncation or malformed JSON - raise for retry
            raise Exception(f"Response validation failed - reduce batch size from {len(filtered_jobs)} jobs")

        job_scores = result.get("job_scores", [])

        return job_scores

    except Exception as e:
        logger.error(f"Error in batch LLM analysis: {e}")

        # Re-raise to allow caller to handle retries
        raise Exception(f"Batch LLM analysis failed: {str(e)}")

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

# Module-level constant — built once, reused across all fuzzy_skill_match calls.
# Previously this dict was allocated and GC'd inside the function on every call
# (~26k times per match run), burning meaningful CPU.
_SKILL_VARIATIONS: dict = {
    'javascript': ['js', 'javascript', 'ecmascript'],
    'typescript': ['ts', 'typescript'],
    'react': ['react', 'reactjs', 'react.js'],
    'node.js': ['node', 'nodejs', 'node.js'],
    'vue': ['vue', 'vuejs', 'vue.js'],
    'angular': ['angular', 'angularjs', 'angular.js'],
    'python': ['python', 'python3', 'py'],
    'c++': ['c++', 'cpp', 'cplusplus'],
    'c#': ['c#', 'csharp'],
    'sql': ['sql', 'mysql', 'postgresql', 'postgres'],
    'aws': ['aws', 'amazon web services'],
    'gcp': ['gcp', 'google cloud'],
    'azure': ['azure', 'microsoft azure'],
    'docker': ['docker', 'containerization'],
    'kubernetes': ['kubernetes', 'k8s'],
    # AI/ML tier — JDs often say "AI/ML" or "machine learning" for roles
    # that require LLM/RAG skills; group them so AI-engineering experience
    # surfaces against those postings during the deterministic prefilter.
    'ai_ml': [
        'ai', 'ml', 'machine learning', 'artificial intelligence', 'ai/ml',
        'llm', 'large language model', 'language model',
        'rag', 'retrieval augmented generation', 'retrieval-augmented generation',
        'nlp', 'natural language processing',
        'generative ai', 'gen ai', 'genai',
        'deep learning', 'neural network',
    ],
    'fastapi': ['fastapi', 'fast api'],
    'websockets': ['websockets', 'websocket', 'web socket', 'ws'],
    'next.js': ['next.js', 'nextjs', 'next js'],
    'mongodb': ['mongodb', 'mongo', 'nosql', 'document database'],
    'redis': ['redis', 'memcached', 'caching', 'in-memory database'],
    'graphql': ['graphql', 'graph ql'],
    'tailwindcss': ['tailwindcss', 'tailwind', 'tailwind css'],
    'agent_development': [
        'agent development', 'agentic', 'agentic systems', 'autonomous agent',
        'ai agent', 'agent framework', 'multi-agent', 'multi-agent systems',
        'mcp', 'model context protocol', 'langchain', 'langgraph',
        'crewai', 'autogen', 'swarm',
    ],
    'workflow_orchestration': [
        'workflow orchestration', 'workflow automation', 'pipeline orchestration',
        'langchain', 'langgraph', 'crewai', 'dspy', 'prefect', 'temporal',
    ],
    'api_development': [
        'api integration', 'api development', 'api design',
        'rest api', 'rest apis', 'restful', 'restful api', 'web services',
        'fastapi', 'flask', 'express',
    ],
    'llm_applications': [
        'llm applications', 'llm engineering', 'llm systems', 'llm development',
        'llm', 'large language model', 'language model',
        'prompt engineering', 'fine-tuning', 'rlhf',
    ],
    'evaluation_systems': [
        'evaluation systems', 'model evaluation', 'ai evaluation', 'llm evaluation',
        'benchmarking', 'evals', 'rag evaluation',
        'rag', 'ragas', 'trulens', 'langsmith',
    ],
}
# Inverted index: token → set of canonical groups. A token can belong to
# multiple groups (e.g. "llm" is in both ai_ml and llm_applications), so we
# store a set and check for non-empty intersection rather than equality.
_SKILL_VARIATION_INDEX: dict = {}
for _canonical, _variants in _SKILL_VARIATIONS.items():
    for _v in _variants:
        _SKILL_VARIATION_INDEX.setdefault(_v, set()).add(_canonical)


@lru_cache(maxsize=4096)
def fuzzy_skill_match(resume_skill, job_skill):
    """
    Intelligent fuzzy matching for skills to handle variations.

    Examples:
    - "React" matches "ReactJS", "React.js"
    - "Node.js" matches "Node", "NodeJS"
    - "JavaScript" matches "JS"
    - "Python" matches "Python3"

    Returns: True if skills match, False otherwise
    """
    resume_lower = resume_skill.lower().strip()
    job_lower = job_skill.lower().strip()

    # Exact match
    if resume_lower == job_lower:
        return True

    # Direct substring match (bidirectional)
    if resume_lower in job_lower or job_lower in resume_lower:
        return True

    # Check variation groups via inverted index (O(1) vs O(groups) scan).
    # A token can belong to multiple groups, so check for non-empty intersection.
    resume_groups = _SKILL_VARIATION_INDEX.get(resume_lower)
    if resume_groups and resume_groups & _SKILL_VARIATION_INDEX.get(job_lower, set()):
        return True

    return False


def simple_keyword_scoring(job, resume_skills, resume_text="", embedding_score=0.0):
    """
    Improved keyword-based scoring with fuzzy matching and stricter filtering.

    Scoring breakdown:
    - 85% from required_skills matches (primary signal)
    - 10% from bonus skills in title
    - 5% from role type alignment

    Key improvements:
    - Uses fuzzy matching for skill variations
    - Only scores based on required_skills (not random description mentions)
    - Returns (0, 0) if no required skills match
    - Better handles skill variations (React vs ReactJS)

    Returns: (score, matched_skill_count)
    """
    score = 0
    matched_skills = []
    skill_match_count = 0

    # Get job details
    job_skills = job.get('required_skills', [])
    job_title = job.get('title', '').lower()
    job_description = job.get('description', '').lower()

    # Pre-normalize resume skills once — avoids repeated .lower().strip() inside
    # the inner loop (called once here vs. once per job_skill × resume_skill pair).
    normalized_resume_skills = [s.lower().strip() for s in resume_skills] if resume_skills else []

    # 1. Required Skills Matching (60 points max) - PRIMARY SIGNAL
    # Reduced from 90 to 60 to make room for the embedding signal (35 pts).
    # Together they sum to 95 max before bonuses, preserving meaningful spread.
    if job_skills and normalized_resume_skills:
        for job_skill in job_skills:
            for resume_skill in normalized_resume_skills:
                if fuzzy_skill_match(resume_skill, job_skill):
                    skill_match_count += 1
                    matched_skills.append(job_skill)
                    break

        # Calculate percentage of required skills matched
        if len(job_skills) > 0:
            skill_coverage = skill_match_count / len(job_skills)
            score += int(skill_coverage * 60)

    # CRITICAL: If zero required skills matched, return (0, 0) immediately
    # This prevents irrelevant jobs from appearing (e.g., C++ jobs for JS developers).
    # Exception: if a semantic embedding signal is present, don't hard-zero — the
    # embedding can surface jobs whose vocabulary doesn't overlap the resume but are
    # genuinely relevant (e.g., "distributed systems" resume vs "C++/CUDA" job listing).
    if skill_match_count == 0 and job_skills:
        if embedding_score <= 0.0:
            return 0, 0

    # 1b. Description text scan — bonus for specialized user skills (RAG, Claude,
    # MCP, FastAPI, etc.) that rarely appear in structured required_skills but DO
    # appear in JD body text. Capped at 12 pts so it can't override the primary signal.
    if job_description and normalized_resume_skills:
        already_matched_lower = {s.lower() for s in matched_skills}
        desc_bonus = 0
        for s in normalized_resume_skills:
            if s in already_matched_lower:
                continue
            # word-boundary check to avoid "js" matching "adjustments", etc.
            if re.search(r'\b' + re.escape(s) + r'\b', job_description):
                desc_bonus += 4
        score += min(desc_bonus, 12)

    # 2. Title bonus (10 points max) - Only if we have skill matches
    # Rewards when matched skills appear prominently in the title
    title_bonus = 0
    for matched_skill in matched_skills:
        pattern = r'\b' + re.escape(matched_skill.lower()) + r'\b'
        if re.search(pattern, job_title):
            title_bonus += 3
    score += min(title_bonus, 10)

    # 3. Role type alignment (5 points) - Contextual bonus
    # Check if resume skills align with common role patterns
    role_patterns = {
        'frontend': ['react', 'vue', 'angular', 'javascript', 'typescript', 'html', 'css'],
        'backend': ['node.js', 'python', 'java', 'spring', 'django', 'flask', 'sql'],
        'fullstack': ['react', 'node.js', 'javascript', 'typescript', 'sql'],
        'data': ['python', 'pandas', 'numpy', 'tensorflow', 'pytorch', 'sql'],
        'mobile': ['react native', 'flutter', 'swift', 'kotlin', 'ios', 'android'],
        'devops': ['docker', 'kubernetes', 'aws', 'azure', 'gcp', 'ci/cd'],
    }

    for role_type, role_skills in role_patterns.items():
        if role_type in job_title:
            # Check if candidate has relevant skills for this role type
            role_skill_matches = sum(1 for rs in normalized_resume_skills if any(fuzzy_skill_match(rs, role_skill) for role_skill in role_skills))
            if role_skill_matches >= 2:
                score += 5
                break

    # Semantic similarity — applied throughout, not just as a rescue signal.
    # Up to 35 pts (rebalanced from 15) so embeddings carry real weight alongside
    # keyword matching rather than acting as a minor tiebreaker.
    if embedding_score > 0.0:
        score += min(int(embedding_score * 35), 35)

    # Deterministic ±5 jitter based on job_hash to visually spread scores
    # that land at the same integer. Same job always gets the same offset,
    # so cached results stay consistent across requests.
    job_hash = job.get('job_hash', '')
    if job_hash:
        offset = (int(job_hash[-2:], 16) % 11) - 5  # maps 0–10 → -5 to +5
        score = min(97, max(0, score + offset))

    # Quick Mode cap: 90s should be rare and reserved for near-perfect keyword
    # matches. LLM analysis (Think Deeper) is the path to confident 90+ scores.
    return min(int(score), 94), skill_match_count


def create_keyword_match_description(job, score, matched_skills_count, total_required_skills):
    """
    Generate helpful match descriptions for keyword-based matches.
    """
    company = job.get('company', 'Unknown Company')
    title = job.get('title', 'Unknown Position')
    location = job.get('location', 'Location not specified')

    # Create opening based on score
    if score >= 80:
        opening = f"🎯 **{company}** - Strong keyword match! This {title} position aligns well with your skills."
    elif score >= 60:
        opening = f"✅ **{company}** - Good match. This {title} role shows solid alignment."
    elif score >= 40:
        opening = f"⚠️ **{company}** - Moderate match. This {title} position has some alignment."
    else:
        opening = f"📊 **{company}** - Partial match. This {title} role has limited alignment."

    # Add skill coverage info
    if total_required_skills > 0:
        coverage_pct = int((matched_skills_count / total_required_skills) * 100)
        skill_info = f"\n\n**📋 Skill Coverage:** You match {matched_skills_count} of {total_required_skills} required skills ({coverage_pct}%)"
    else:
        skill_info = "\n\n**📋 Skill Coverage:** Job requirements not specified"

    # Add location
    location_section = f"\n\n**📍 Location:** {location}"

    # Add score with recommendation
    score_section = f"\n\n**🎯 Match Score: {score}/100**"
    if score >= 70:
        score_section += " - **Recommended**"
    elif score >= 40:
        score_section += " - **Consider Applying**"
    else:
        score_section += " - **May Be a Stretch**"

    # Add note about quick mode
    note = "\n\n*Quick Match Mode - For deeper analysis, enable 'Think Deeper'*"

    return opening + skill_info + location_section + score_section + note


def simple_keyword_match(resume_skills, jobs, resume_text="", progress_callback=None, categories=None):
    """
    Improved fast keyword-based matching with better descriptions.
    Used when LLM is disabled or unavailable.

    Key improvements:
    - Analyzes ALL jobs (no pre-filtering) since regex is fast
    - Uses fuzzy skill matching for accuracy
    - Blends sentence-embedding similarity when available
    - Generates helpful match descriptions
    - Returns top 100 results (increased from 50)

    Returns jobs with keyword match scores and descriptions.
    """
    matched_jobs = []

    # Department/category hard filter (no-op when categories is empty/None).
    jobs = _filter_by_categories(jobs, categories, progress_callback)

    # Send progress: Starting keyword matching
    if progress_callback:
        progress_callback("Matching jobs with keyword analysis...")

    logger.info(f"Quick Mode: Analyzing {len(jobs)} jobs with keyword matching...")

    # Load pre-computed job embeddings and embed the resume once.
    # Both are best-effort: missing embeddings fall back to keyword-only scoring.
    job_embeddings: dict = {}
    resume_embedding: list = []
    try:
        from matching.embedder import compute_resume_embedding, cosine_similarity
        from job_database import get_all_job_embeddings
        job_embeddings = get_all_job_embeddings()
        if resume_text:
            resume_embedding = compute_resume_embedding(resume_text)
    except Exception as _emb_err:
        logger.warning("Embedding lookup skipped: %s", _emb_err)

    for job in jobs:
        emb_score = 0.0
        if resume_embedding and job.get("job_hash") in job_embeddings:
            try:
                emb_score = cosine_similarity(resume_embedding, job_embeddings[job["job_hash"]])
            except Exception:
                pass

        score, matched_count = simple_keyword_scoring(job, resume_skills, resume_text, embedding_score=emb_score)

        # Only include jobs with some relevance (score > 0)
        if score > 0:
            job_copy = job.copy()
            job_copy['match_score'] = score

            # Generate rich description (matched_count comes from scoring, no second pass)
            job_skills = job.get('required_skills', [])
            job_copy['match_description'] = create_keyword_match_description(
                job, score, matched_count, len(job_skills)
            )

            job_copy['ai_reasoning'] = None  # No AI analysis in keyword mode
            matched_jobs.append(job_copy)

    # Sort by score descending
    matched_jobs.sort(key=lambda x: x['match_score'], reverse=True)

    logger.info(f"Quick Mode: Found {len(matched_jobs)} matching jobs")

    # Return top 100 results (analyze more jobs since it's fast)
    return matched_jobs[:100]


def _extract_resume_profile_haiku(resume_text: str, system_prompt=None, temperature=None) -> dict:
    """Uses Claude Haiku to quickly extract skills and experience level for accurate pre-filtering."""
    sys_p = system_prompt if system_prompt is not None else RESUME_PROFILE_SYSTEM_PROMPT
    user_prompt = f"RESUME:\n{resume_text[:6500]}"
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        create_kwargs = dict(
            model="claude-haiku-4-5",
            max_tokens=1000,
            system=sys_p,
            messages=[{"role": "user", "content": user_prompt}],
        )
        if temperature is not None:
            create_kwargs["temperature"] = temperature
        response = client.messages.create(**create_kwargs)
        raw = extract_json_from_response(response.content[0].text)
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Haiku extraction failed: {e}")
        return {"skills": [], "experience_level": "student", "years_of_experience": 0}


def _prefilter_jobs_with_profile(profile: dict, jobs: List[Dict], target_count: int = 30) -> List[Dict]:
    """Accurate pre-filtering using Haiku-extracted profile and skill overlap scoring."""
    is_student = profile.get('experience_level') == 'student'
    years_experience = profile.get('years_of_experience', 0)
    resume_skills = [str(s).lower() for s in profile.get('skills', [])]
    
    scored_jobs = []
    for job in jobs:
        title = job.get('title', '').lower()
        desc = job.get('description', '').lower()

        # Filter out senior roles for juniors
        if is_student or years_experience < 3:
            if any(kw in title for kw in ['senior', 'lead', 'principal', 'staff', 'architect', 'manager', 'director']):
                continue

        # Filter out high experience requirements
        skip = False
        for match in re.findall(r'(\d+)\+?\s*years?\s*(?:of\s+)?experience', desc):
            if int(match) >= 5 and years_experience < 3:
                skip = True
                break
        if skip:
            continue

        # Calculate simple skill overlap
        overlap = 0
        job_skills = job.get('required_skills', [])
        for js in job_skills:
            js_lower = str(js).lower()
            if any(fuzzy_skill_match(rs, js_lower) for rs in resume_skills):
                overlap += 1
                
        scored_jobs.append((overlap, job))
        
    # Sort by overlap descending
    scored_jobs.sort(key=lambda x: x[0], reverse=True)
    return [job for _, job in scored_jobs][:target_count]


def analyze_and_match_single_call(resume_text: str, jobs: List[Dict], progress_callback=None, system_prompt=None, temperature=None, categories=None):
    """
    Combined resume analysis + job matching in a SINGLE Claude Sonnet call.
    Uses Haiku for pre-filtering and XML prompting to prevent attention dilution.

    Returns: (skills, metadata, enhanced_jobs)
      - skills: list of skill strings
      - metadata: dict with experience_level, years_of_experience, is_student
      - enhanced_jobs: list of job dicts with match_score and ai_reasoning
    """
    if not resume_text.strip():
        return [], {}, []

    # Department/category hard filter BEFORE any LLM work so we never pay Haiku/
    # Sonnet cost on filtered-out jobs (no-op when categories is empty/None).
    jobs = _filter_by_categories(jobs, categories, progress_callback)
    if not jobs:
        return [], {}, []

    if progress_callback:
        progress_callback("Extracting profile with AI...")

    profile = _extract_resume_profile_haiku(resume_text)

    if progress_callback:
        progress_callback("Pre-filtering top candidates for you...")

    candidate_jobs = _prefilter_jobs_with_profile(profile, jobs, target_count=30)
    if not candidate_jobs:
        candidate_jobs = jobs[:15]  # Fallback: just take first 15

    if progress_callback:
        progress_callback("Analyzing resume with AI...")

    # Build XML compact job summaries to fix attention dilution
    jobs_xml = "<job_listings>\n"
    for i, job in enumerate(candidate_jobs):
        jobs_xml += f'  <job id="{i + 1}">\n'
        jobs_xml += f"    <company>{job.get('company', 'Unknown')}</company>\n"
        jobs_xml += f"    <title>{job.get('title', 'Unknown')}</title>\n"
        jobs_xml += f"    <location>{job.get('location', 'Unknown')}</location>\n"
        
        # [:400] is intentional — passing full JDs across 30 jobs would blow the
        # 4096 max_tokens budget. Full descriptions only flow into the single-job
        # tailor endpoint where only one job is scored at a time.
        desc = job.get('description', '')[:400]
        # Escape XML to prevent breaking parsing
        desc = desc.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
        jobs_xml += f"    <description>{desc}</description>\n"
        jobs_xml += "  </job>\n"
    jobs_xml += "</job_listings>"

    sys_p = system_prompt if system_prompt is not None else JOB_MATCH_SYSTEM_PROMPT

    user_prompt = (
        f"RESUME:\n{resume_text[:6500]}\n\n"
        f"JOBS TO ANALYZE ({len(candidate_jobs)} positions):\n"
        f"{jobs_xml}\n\n"
        f"Analyze the resume and score all {len(candidate_jobs)} jobs. Return JSON only."
    )

    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        create_kwargs = dict(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=[{"type": "text", "text": sys_p, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_prompt}],
        )
        if temperature is not None:
            create_kwargs["temperature"] = temperature
        response = client.messages.create(**create_kwargs)

        raw = extract_json_from_response(response.content[0].text)
        result = json.loads(raw)
    except Exception as e:
        logger.error(f"Combined LLM call failed: {e}")
        # Fallback: keyword match with extracted skills
        return profile.get('skills', []), profile, simple_keyword_match(profile.get('skills', []), jobs, resume_text, progress_callback=progress_callback)

    skills = profile.get("skills", [])
    metadata = {
        "experience_level": profile.get("experience_level", "student"),
        "years_of_experience": profile.get("years_of_experience", 0),
        "is_student": profile.get("is_student", profile.get("experience_level") == "student"),
        "projects": profile.get("projects", []),
        "impact_highlights": profile.get("impact_highlights", []),
        "confidence_metrics": profile.get("confidence_metrics", []),
    }

    if progress_callback:
        progress_callback("Enhancing results with career insights...")

    job_scores = result.get("job_scores", [])
    enhanced_jobs = enhance_batch_results(job_scores, candidate_jobs, skills)

    return skills, metadata, enhanced_jobs


def _score_jobs_with_prompt(resume_text: str, jobs_xml: str, system_prompt=None, temperature=None) -> dict:
    """
    Thin Sonnet-only scoring call for eval purposes.

    Skips the Haiku pre-filter step; accepts a pre-built jobs_xml string and
    an injectable system_prompt (defaults to JOB_MATCH_SYSTEM_PROMPT).
    Returns the raw parsed JSON dict from Claude.
    """
    sys_p = system_prompt if system_prompt is not None else JOB_MATCH_SYSTEM_PROMPT
    job_count = jobs_xml.count("<job ")
    user_prompt = (
        f"RESUME:\n{resume_text[:6500]}\n\n"
        f"JOBS TO ANALYZE ({job_count} positions):\n"
        f"{jobs_xml}\n\n"
        f"Analyze the resume and score all {job_count} jobs. Return JSON only."
    )
    client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    create_kwargs = dict(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=[{"type": "text", "text": sys_p, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_prompt}],
    )
    if temperature is not None:
        create_kwargs["temperature"] = temperature
    response = client.messages.create(**create_kwargs)
    raw = extract_json_from_response(response.content[0].text)
    return json.loads(raw)


def match_resume_to_jobs(resume_skills, jobs, resume_text="", use_llm=True, progress_callback=None, categories=None):
    """
    Intelligent job matching system with optional LLM analysis.

    Args:
        resume_skills: List of candidate skills
        jobs: List of job postings to match against
        resume_text: Full resume text for context
        use_llm: If True, uses AI analysis. If False, uses keyword matching.
        progress_callback: Optional callback function to report progress (takes message string)
        categories: Optional list of canonical department-category ids to filter to
                    (job_categories.CATEGORY_IDS); empty/None => no filtering.

    Returns:
        List of matched jobs with scores and descriptions

    Modes:
        - LLM Mode (use_llm=True): 3-stage intelligent matching with AI career analysis
        - Keyword Mode (use_llm=False): Fast keyword-based scoring
        - Fallback: Automatically falls back to keyword if LLM fails
    """
    if not jobs:
        return []

    # Department/category hard filter up front so every downstream stage (prefilter,
    # LLM, keyword fallback) operates on the already-narrowed set (no-op if empty).
    jobs = _filter_by_categories(jobs, categories, progress_callback)
    if not jobs:
        return []

    # If LLM disabled, use keyword matching directly
    if not use_llm:
        return simple_keyword_match(resume_skills, jobs, resume_text, progress_callback=progress_callback)

    # Extract resume metadata for filtering
    resume_metadata = {
        'experience_level': extract_user_experience_level(resume_skills, resume_text),
        'years_of_experience': 0,
        'is_student': True
    }

    # Try LLM matching with automatic fallback
    try:
        # STAGE 1: Intelligent Pre-filtering
        filtered_jobs = intelligent_prefilter_jobs(jobs, resume_skills, resume_metadata, target_count=30, progress_callback=progress_callback)

        if not filtered_jobs:
            # No jobs passed pre-filtering, fall back to keyword on all jobs
            return simple_keyword_match(resume_skills, jobs, resume_text, progress_callback=progress_callback)

        # STAGE 2: Batch LLM Analysis
        llm_scores = batch_analyze_jobs_with_llm(filtered_jobs, resume_skills, resume_text, resume_metadata, progress_callback=progress_callback)

        if not llm_scores:
            # LLM returned no scores, fall back to keyword
            return simple_keyword_match(resume_skills, jobs, resume_text, progress_callback=progress_callback)

        # STAGE 3: Enhanced Results Processing
        if progress_callback:
            progress_callback("Enhancing results with career insights...")

        enhanced_jobs = enhance_batch_results(llm_scores, filtered_jobs, resume_skills)

        return enhanced_jobs

    except Exception:
        # LLM matching failed, automatically fall back to keyword matching
        return simple_keyword_match(resume_skills, jobs, resume_text, progress_callback=progress_callback)


 

# ---------------------------------------------------------------------------
# Deterministic prefilter + scoring core for the MCP /api/v1 surface.
# NO LLM CALLS — the calling agent does all reasoning over these scores.
# ---------------------------------------------------------------------------

def prefilter_and_score(resume_profile: Dict, jobs: List[Dict]) -> List[Dict]:
    """LLM-free prefilter and scoring used by POST /api/v1/jobs/prefilter.

    Combines:
      - intelligent_prefilter_jobs hard rules (senior-role / years-required filters)
      - metadata_matcher.calculate_metadata_match_score (weighted metadata)
      - simple_keyword_scoring (fuzzy required-skills coverage)

    resume_profile is the small, PII-free object the MCP sends:
      {skills, experience_level, years_of_experience, location,
       willing_to_relocate, remote_ok}

    Returns one dict per job (hard-filtered jobs included with
    hard_filter_passed=False so the agent can see what was excluded), each with
    keyword_score / metadata_score / combined_score / skill_matches / skill_gaps.
    """
    from matching.metadata_matcher import (
        calculate_metadata_match_score,
        extract_job_metadata,
    )

    skills = resume_profile.get("skills", []) or []
    experience_level = resume_profile.get("experience_level", "student")
    years = resume_profile.get("years_of_experience", 0) or 0

    # Map the profile enum (student|entry_level|experienced) onto the levels
    # used by the metadata compatibility table and the hard-rule filter.
    _LEVEL_MAP = {"student": "student", "entry_level": "junior", "experienced": "mid"}
    resume_metadata = {
        "experience_level": _LEVEL_MAP.get(experience_level, "student"),
        "years_of_experience": years,
        "is_student": experience_level == "student",
        "location_preferences": (
            [resume_profile["location"]] if resume_profile.get("location") else []
        ),
        "industry_preferences": resume_profile.get("industry_preferences") or [],
        "remote_preference": bool(resume_profile.get("remote_ok", False)),
        "relocation_willingness": bool(resume_profile.get("willing_to_relocate", False)),
        "citizenship": resume_profile.get("citizenship") or "unknown",
    }

    # Load all job embeddings once and embed the resume profile text.
    # Best-effort: if unavailable, fall back to keyword+metadata weights.
    _job_embeddings: dict = {}
    _resume_embedding: list = []
    try:
        from matching.embedder import embed_text, cosine_similarity
        from job_database import get_all_job_embeddings
        _job_embeddings = get_all_job_embeddings()
        _resume_text = resume_profile.get("resume_text", "") or " ".join(resume_profile.get("skills", []))
        if _resume_text:
            _resume_embedding = embed_text(_resume_text[:8000])
    except Exception as _emb_err:
        logger.warning("prefilter_and_score: embedding skipped: %s", _emb_err)

    results = []
    for job in jobs:
        # Compute embedding similarity first so it can be passed into keyword scoring,
        # allowing the early-return guard to be bypassed for semantically relevant jobs.
        embedding_sim = 0.0
        if _resume_embedding and job.get("job_hash") in _job_embeddings:
            try:
                embedding_sim = cosine_similarity(_resume_embedding, _job_embeddings[job["job_hash"]])
            except Exception:
                pass

        keyword_score, _ = simple_keyword_scoring(job, skills, embedding_score=embedding_sim)
        job_metadata = extract_job_metadata(job)
        # extract_job_metadata parses location from description text via regex,
        # but scraped jobs store the authoritative location in the DB field.
        # Override so location scoring actually differentiates jobs.
        if job.get("location"):
            job_metadata["location"] = job["location"]
        metadata_score, _desc = calculate_metadata_match_score(resume_metadata, job_metadata)

        if embedding_sim > 0.0:
            # Three-signal blend: keyword 45%, metadata 25%, embedding 30%
            combined_score = round(keyword_score * 0.45 + metadata_score * 0.25 + embedding_sim * 100 * 0.30)
        else:
            # Fallback: original two-signal weights (no embedding available yet)
            combined_score = round(keyword_score * 0.7 + metadata_score * 0.3)

        # Supplement DB required_skills with a deterministic vocabulary scan
        # of stored text. Real JD text (after lazy job_get fetch) gives precise
        # results; synthetic descriptions still surface "Machine Learning" etc.
        db_skills = set(job.get("required_skills") or [])
        desc = job.get("description") or ""
        scan_text = (job.get("title") or "") + (" " + desc if desc else "")
        job_skills = list(db_skills | set(extract_skills_from_text(scan_text)))

        skill_matches = [
            js for js in job_skills
            if any(fuzzy_skill_match(rs, js) for rs in skills)
        ]
        skill_gaps = [js for js in job_skills if js not in skill_matches]

        # Surface user skills found in description text but not in required_skills.
        # Lets the agent see which differentiators (RAG, Claude, FastAPI, MCP) are
        # relevant to each JD even when not listed as structured requirements.
        import re as _re
        desc_lower = (job.get("description") or "").lower()
        matched_req_lower = {s.lower() for s in skill_matches}
        desc_skill_matches = [
            s for s in skills
            if s.lower() not in matched_req_lower
            and _re.search(r'\b' + _re.escape(s.lower()) + r'\b', desc_lower)
        ]

        results.append({
            "job_hash": job.get("job_hash"),
            "company": job.get("company"),
            "title": job.get("title"),
            "location": job.get("location"),
            "apply_link": job.get("apply_link"),
            "keyword_score": keyword_score,
            "metadata_score": metadata_score,
            "embedding_score": round(embedding_sim * 100) if embedding_sim > 0.0 else None,
            "combined_score": combined_score,
            "skill_matches": skill_matches,
            "skill_gaps": skill_gaps,
            "desc_skill_matches": desc_skill_matches,
            "hard_filter_passed": _passes_hard_filters(job, experience_level, years),
            "description_preview": (job.get("description") or "")[:500],
        })

    results.sort(key=lambda r: (r["hard_filter_passed"], r["combined_score"]), reverse=True)
    return results

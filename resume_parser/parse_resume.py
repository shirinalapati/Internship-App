import pdfplumber
import re
import os
import io
import json
from openai import OpenAI
from typing import List, Dict, Any

# Static system prompt for resume analysis (cached across calls)
RESUME_ANALYSIS_SYSTEM_PROMPT = """You are an expert resume analyzer. Your task is to extract ONLY the technical and professional skills that this person actually possesses based on their resume content.

CRITICAL INSTRUCTIONS:
1. ONLY extract skills the person actually has experience with or claims to know
2. DO NOT extract skills mentioned in negative contexts (e.g., "I have never used Python", "I want to learn React")
3. DO NOT extract skills from job descriptions they're applying to
4. DO NOT extract skills from courses they want to take in the future
5. Focus on concrete evidence: work experience, projects, education, certifications
6. USE STANDARD SKILL NAMES (e.g., "JavaScript" not "JS", "Python" not "Python3", "Machine Learning" not "ML")
7. PRIORITIZE skills with demonstrated project/work experience over just "familiar with"
8. BE CONSERVATIVE - it's better to extract 5-8 strong skills than 20 weak ones

SKILL CATEGORIES TO EXTRACT:
- Programming Languages: Python, Java, JavaScript, TypeScript, C++, C#, Go, Rust, PHP, Ruby, etc.
- Web Technologies: React, Angular, Vue, HTML, CSS, Node.js, Express, Django, Flask, etc.
- Databases: SQL, MySQL, PostgreSQL, MongoDB, Redis, etc.
- Cloud Platforms: AWS, Azure, GCP, Docker, Kubernetes, etc.
- Tools & Frameworks: Git, TensorFlow, PyTorch, Pandas, NumPy, etc.
- Soft Skills: Leadership, Communication, Project Management, Teamwork, etc.
- Domain Knowledge: Machine Learning, Data Analysis, Software Engineering, etc.

STANDARDIZATION RULES:
- Use "JavaScript" instead of "JS"
- Use "TypeScript" instead of "TS"
- Use "Python" instead of "Python3" or "Py"
- Use "Machine Learning" instead of "ML"
- Use "Artificial Intelligence" instead of "AI"
- Use "SQL" for general database skills
- Use specific database names when mentioned (MySQL, PostgreSQL, etc.)
- Use "Git" for version control
- Use full framework names (React, Angular, Vue, etc.)

Please analyze the user's resume text provided in the next message.
Return your response as a JSON object with this exact structure:
{
    "skills": [
        "skill1",
        "skill2",
        "skill3"
    ],
    "experience_level": "student/recent_graduate/entry_level/experienced",
    "years_of_experience": 0,
    "is_student": true/false,
    "confidence_notes": "Brief explanation of your extraction approach"
}
"""

def extract_skills_with_llm(resume_text: str) -> List[str]:
    """
    Use GPT-4o to extract skills from resume text with context awareness.
    Returns a list of skills that the person actually possesses.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            messages=[
                {"role": "system", "content": RESUME_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": resume_text}
            ]
        )
        
        # Parse the JSON response
        result = json.loads(response.choices[0].message.content)
        skills = result.get("skills", [])
        experience_level = result.get("experience_level", "student")
        years = result.get("years_of_experience", 0)
        is_student = result.get("is_student", True)
        
        print(f"🤖 LLM extracted {len(skills)} skills: {skills}")
        print(f"🤖 Experience level: {experience_level} ({years} years)")
        print(f"🤖 Is student: {is_student}")
        print(f"🤖 LLM confidence notes: {result.get('confidence_notes', 'None')}")
        
        return skills
        
    except Exception as e:
        print(f"❌ Error with LLM skill extraction: {e}")
        # Re-raise the exception to be handled by the calling function
        raise Exception(f"LLM skill extraction failed: {str(e)}")

def extract_basic_skills_from_text(resume_text: str) -> List[str]:
    """
    Extract basic skills from text using simple keyword matching.
    This is a fallback when LLM extraction fails or returns no results.
    """
    # Most common technical skills that are likely to match job requirements
    basic_skill_keywords = [
        "Python", "Java", "JavaScript", "TypeScript", "React", "Angular", "Vue",
        "HTML", "CSS", "SQL", "Git", "Node.js", "Express", "Django", "Flask",
        "Spring", "AWS", "Azure", "GCP", "Docker", "Kubernetes", "MongoDB",
        "PostgreSQL", "MySQL", "TensorFlow", "PyTorch", "Pandas", "NumPy",
        "Machine Learning", "Data Analysis", "Software Engineering", "Programming",
        "C++", "C#", "PHP", "Ruby", "Go", "Rust", "Bootstrap", "jQuery",
        "REST API", "GraphQL", "Linux", "Testing", "Agile", "Scrum"
    ]
    
    found_skills = []
    text_lower = resume_text.lower()
    
    for skill in basic_skill_keywords:
        skill_lower = skill.lower()
        # Simple word boundary check
        if re.search(r'\b' + re.escape(skill_lower) + r'\b', text_lower):
            found_skills.append(skill)
    
    return list(set(found_skills))

def extract_skills_with_regex(resume_text: str) -> List[str]:
    """
    Fallback regex-based skill extraction (original method).
    """
    skills = re.findall(r"\b(Python|Java|React|Data Analysis|SQL|TensorFlow|C\+\+|JavaScript|Computer Science|Technical|Programming|Software|Engineering|Data|Machine Learning|AI|Cloud|Leadership|Communication|Teamwork|Problem Solving|Git|Rust|Less|Go|R\b|C#|TypeScript|PHP|Ruby|Scala|Matlab|Perl|Bash|Shell|PowerShell|Angular|Vue|Node\.js|Express|Django|Flask|Spring|Laravel|HTML|CSS|Sass|Bootstrap|Tailwind|jQuery|Ajax|REST API|GraphQL|WebSocket|HTTP|HTTPS|JSON|XML|MySQL|PostgreSQL|MongoDB|Redis|Elasticsearch|Cassandra|Data Science|Data Engineering|ETL|Data Pipeline|Deep Learning|Artificial Intelligence|Neural Networks|PyTorch|Scikit-learn|Pandas|Numpy|Matplotlib|Seaborn|Computer Vision|NLP|Natural Language Processing|Recommendation Systems|AWS|Azure|GCP|Google Cloud|Docker|Kubernetes|Jenkins|GitLab|GitHub|CI/CD|Terraform|Ansible|Prometheus|Grafana|Software Development|Coding|Algorithm|Data Structures|Object-oriented|Functional Programming|Design Patterns|Microservices|API Development|Backend|Frontend|Full Stack|Fullstack|Mobile Development|iOS|Android|React Native|Flutter|Xamarin|Testing|Unit Testing|Integration Testing|QA|Quality Assurance|Test Automation|Selenium|JUnit|PyTest|Jest|Cypress|Maven|Gradle|NPM|Yarn|IntelliJ|VSCode|Eclipse|Vim|Emacs|Linux|Unix|macOS|E-commerce|Fintech|Healthcare|Cybersecurity|Blockchain|IoT|Embedded Systems|FPGA|Hardware|Robotics|Autonomous Vehicles|Agile|Scrum|Project Management|Mentoring|Collaboration|Presentation|Student|Intern|Internship|Co-op|Research|Thesis|Academic|University|College|Bachelor|Master|PhD|Graduate|Undergraduate|Mathematics|Statistics|Physics)\b", resume_text, re.IGNORECASE)
    return list(set([s.title() for s in skills]))

def parse_resume(file_content, filename, use_llm=True):
    """
    Parse resume from file content and extract skills using LLM or legacy methods.
    Args:
        file_content: The file content to parse
        filename: The filename for file type detection
        use_llm: If True, use LLM-based parsing; if False, use legacy text-based parsing
    Returns tuple: (skills_list, resume_text, metadata_dict)
    """
    ext = os.path.splitext(filename)[1].lower() if filename else ''
    text = ""
    
    if ext in [".png", ".jpg", ".jpeg"]:
        try:
            from PIL import Image
            import pytesseract
            image = Image.open(io.BytesIO(file_content))
            text = pytesseract.image_to_string(image)
        except Exception as e:
            print(f"Error processing image: {e}")
            text = ""
    else:
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
        except Exception as e:
            print(f"Error processing PDF: {e}")
            text = ""

    # Check if text was extracted successfully
    if not text.strip():
        print("⚠️ No text extracted from resume, cannot perform skill extraction")
        return [], "", {}
    
    # Choose parsing method based on use_llm parameter
    if use_llm:
        print("🤖 Starting LLM-based resume analysis with GPT-4o...")
        
        try:
            # Primary method: LLM extraction with full metadata
            result = extract_skills_with_llm_full(text)
            skills = result.get("skills", [])
            metadata = {
                "experience_level": result.get("experience_level", "student"),
                "years_of_experience": result.get("years_of_experience", 0),
                "is_student": result.get("is_student", True),
                "confidence_notes": result.get("confidence_notes", "")
            }
            
            if not skills:
                print("⚠️ LLM returned no skills, trying to extract basic skills from text...")
                # Fallback: extract some basic skills from the text if LLM returns nothing
                basic_skills = extract_basic_skills_from_text(text)
                if basic_skills:
                    print(f"🔄 Fallback extracted {len(basic_skills)} basic skills: {basic_skills}")
                    return basic_skills, text, {"experience_level": "student", "is_student": True}
                else:
                    print("❌ No skills could be extracted from resume")
                    return [], text, {}
                
            print(f"✅ Successfully extracted {len(skills)} skills using LLM")
            print(f"📊 Resume metadata: {metadata['experience_level']} ({metadata['years_of_experience']} years)")
            return skills, text, metadata
            
        except Exception as e:
            print(f"❌ LLM extraction failed: {e}")
            
            # Check if it's an API key issue
            if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                print("🔑 API key issue detected. Please check your OPENAI_API_KEY environment variable.")
                raise Exception("OpenAI API key not configured properly. Please set OPENAI_API_KEY in your environment variables.")
            
            # Check if it's a quota/billing issue
            if "quota" in str(e).lower() or "billing" in str(e).lower():
                print("💳 OpenAI quota/billing issue detected.")
                raise Exception("OpenAI API quota exceeded or billing issue. Please check your OpenAI account.")
            
            # For other errors, provide a clear message
            print("🚨 Critical error in LLM processing - cannot extract skills")
            raise Exception(f"Resume processing failed: {str(e)}. Please try again or contact support.")
    
    else:
        print("📄 Using legacy text-based resume analysis...")
        
        try:
            # Legacy method: text-based skill extraction
            skills = extract_basic_skills_from_text(text)
            
            if not skills:
                # Try regex fallback if basic extraction returns nothing
                print("🔄 Basic text extraction returned no skills, trying regex fallback...")
                skills = extract_skills_with_regex(text)
            
            if not skills:
                print("❌ No skills could be extracted using legacy methods")
                return [], text, {}
            
            # Create basic metadata for legacy parsing
            metadata = {
                "experience_level": "student",  # Default for legacy parsing
                "years_of_experience": 0,
                "is_student": True,
                "confidence_notes": "Extracted using legacy text-based parsing"
            }
            
            print(f"✅ Successfully extracted {len(skills)} skills using legacy methods")
            return skills, text, metadata
            
        except Exception as e:
            print(f"❌ Legacy extraction failed: {e}")
            return [], text, {}

def extract_skills_with_llm_full(resume_text: str) -> Dict[str, Any]:
    """
    Enhanced version that returns full metadata along with skills.
    This is used by parse_resume() to get complete resume analysis.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            messages=[
                {"role": "system", "content": RESUME_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": resume_text}
            ]
        )
        
        result = json.loads(response.choices[0].message.content)
        
        print(f"🤖 LLM extracted {len(result.get('skills', []))} skills: {result.get('skills', [])}")
        print(f"🤖 Experience level: {result.get('experience_level', 'unknown')} ({result.get('years_of_experience', 0)} years)")
        print(f"🤖 Is student: {result.get('is_student', True)}")
        print(f"🤖 Confidence: {result.get('confidence_notes', 'None')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error with LLM skill extraction: {e}")
        raise Exception(f"LLM skill extraction failed: {str(e)}")


def is_valid_resume(text):
    """Check if the text appears to be from a valid resume"""
    if not text or len(text.strip()) < 100:
        return False
    
    # Look for common resume indicators
    resume_indicators = [
        'experience', 'education', 'skills', 'work', 'employment', 
        'university', 'college', 'degree', 'bachelor', 'master', 
        'resume', 'cv', 'curriculum vitae', 'contact', 'email', 
        'phone', 'project', 'intern', 'job', 'position'
    ]
    
    text_lower = text.lower()
    found_indicators = sum(1 for indicator in resume_indicators if indicator in text_lower)
    
    # Require at least 3 resume indicators
    return found_indicators >= 3

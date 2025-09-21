import pdfplumber
import re
import os
import io
import json
from openai import OpenAI
from typing import List, Dict, Any

def extract_skills_with_llm(resume_text: str) -> List[str]:
    """
    Use GPT-4o to extract skills from resume text with context awareness.
    Returns a list of skills that the person actually possesses.
    """
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Craft a detailed prompt for skill extraction with standardized format
        prompt = f"""
You are an expert resume analyzer. Your task is to extract ONLY the technical and professional skills that this person actually possesses based on their resume content.

CRITICAL INSTRUCTIONS:
1. ONLY extract skills the person actually has experience with or claims to know
2. DO NOT extract skills mentioned in negative contexts (e.g., "I have never used Python", "I want to learn React")
3. DO NOT extract skills from job descriptions they're applying to
4. DO NOT extract skills from courses they want to take in the future
5. Focus on concrete evidence: work experience, projects, education, certifications
6. USE STANDARD SKILL NAMES (e.g., "JavaScript" not "JS", "Python" not "Python3", "Machine Learning" not "ML")

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

Return your response as a JSON object with this exact structure:
{{
    "skills": [
        "skill1",
        "skill2",
        "skill3"
    ],
    "confidence_notes": "Brief explanation of your extraction approach"
}}

Resume Text:
{resume_text}
"""

        # Make API call to GPT-4o
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a precise resume analyzer that extracts only verified skills from resumes. You never hallucinate or add skills that aren't clearly demonstrated."
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
        
        # Parse the JSON response
        result = json.loads(response.choices[0].message.content)
        skills = result.get("skills", [])
        
        print(f"🤖 LLM extracted {len(skills)} skills: {skills}")
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

def parse_resume(file_content, filename):
    """Parse resume from file content and extract skills"""
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

    # Use LLM-based skill extraction as primary method
    if not text.strip():
        print("⚠️ No text extracted from resume, cannot perform skill extraction")
        return []
    
    print("🤖 Starting LLM-based skill extraction...")
    
    try:
        # Primary method: LLM extraction
        skills = extract_skills_with_llm(text)
        
        if not skills:
            print("⚠️ LLM returned no skills, trying to extract basic skills from text...")
            # Fallback: extract some basic skills from the text if LLM returns nothing
            basic_skills = extract_basic_skills_from_text(text)
            if basic_skills:
                print(f"🔄 Fallback extracted {len(basic_skills)} basic skills: {basic_skills}")
                return basic_skills
            else:
                print("❌ No skills could be extracted from resume")
                return []
            
        print(f"✅ Successfully extracted {len(skills)} skills using LLM")
        return skills
        
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

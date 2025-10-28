#!/usr/bin/env python3

import os
from dotenv import load_dotenv
import requests
import re
from bs4 import BeautifulSoup
import time

# Load environment variables from .env file
load_dotenv()

GITHUB_INTERNSHIPS_URL = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"

def scrape_job_details_from_apply_link(apply_link):
    """
    Follow the apply link and extract real job qualifications from the company's job posting page.
    """
    try:
        print(f"🔍 Following apply link: {apply_link}")
        
        # Add headers to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(apply_link, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract job description and qualifications
        job_text = soup.get_text(separator=' ', strip=True).lower()
        
        # Check if we have manual requirements for this job
        manual_requirements = get_manual_requirements(apply_link)
        if manual_requirements:
            print(f"✅ Using manual requirements for {apply_link}")
            return {
                'description': manual_requirements['description'],
                'required_skills': manual_requirements['skills'],
                'job_requirements': manual_requirements['requirements'],
                'source': 'manual_database'
            }
        
        # Extract detailed job requirements
        job_requirements = extract_detailed_requirements(soup, job_text)
        
        # Extract skills from the job page
        extracted_skills = extract_skills_from_job_page(job_text)
        
        # Create a detailed description from the actual job posting
        description = extract_job_description(soup)
        
        # Add requirements to description if found
        if job_requirements and job_requirements != "Requirements not available":
            description += "\n\n📋 Job Requirements:\n" + job_requirements
        
        print(f"✅ Extracted {len(extracted_skills)} skills from job posting")
        return {
            'description': description,
            'required_skills': extracted_skills,
            'job_requirements': job_requirements,
            'source': 'company_website'
        }
        
    except Exception as e:
        print(f"⚠️ Could not extract details from {apply_link}: {e}")
        return None

def get_manual_requirements(apply_link):
    """
    Get manual requirements for known jobs that are difficult to scrape.
    """
    manual_requirements_db = {
        # KBR Software Engineer Intern
        "kbr.wd5.myworkdayjobs.com/en-US/KBR_Careers/job/Sioux-Falls-South-Dakota/Software-Engineer-Intern_R2109933": {
            "description": "Software Engineering internship at KBR focusing on satellite ground systems and remote sensing data processing. This role involves working with satellite data, machine learning models, and developing software for space systems.",
            "skills": ["Python", "Machine Learning", "Deep Learning", "IDL", "Matlab", "Satellite Systems", "Remote Sensing", "Image Processing", "Signal Processing"],
            "requirements": """📌 Experience:
  • Working toward a degree in software/data science, remote sensing calibration and/or mathematics
  • Preference will be given to anyone with experience in satellite ground systems, remote sensing data capture, processing, archive, distribution, and scientific applications

📌 Education:
  • Working toward a Bachelors in Engineering, Signal Processing, System Calibration, Photogrammetry, Geodesy, Mathematics, or Satellite Systems

📌 Required Skills:
  • Experience in Machine learning and/or deep learning AI models
  • Programming skills in Python, IDL, or Matlab
  • Ability to communicate effectively orally and in writing
  • Ability to think independently
  • Ability to handle complex multitask environments

📌 Desired Skills:
  • Knowledge of spacecraft and spacecraft instrument dynamics and characteristics
  • Knowledge of image/signal processing and statistical analysis fundamentals
  • Knowledge of map projections
  • Ability to develop image and signal processing techniques and tools
  • Knowledge of satellite systems and remote sensing
  • Knowledge of cloud data processing"""
        },
        
        # Medtronic Software Engineering Intern
        "medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/North-Haven-Connecticut-United-States-of-America/Software-Engineering-Intern---Summer-2026_R40546-1": {
            "description": "Software Engineering internship at Medtronic focusing on medical device software development. This role involves developing software for life-saving medical devices and ensuring compliance with FDA regulations.",
            "skills": ["Python", "Java", "C++", "Software Engineering", "Medical Devices", "Testing", "Quality Assurance"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Software Engineering, or related field

📌 Required Skills:
  • Programming experience in Python, Java, or C++
  • Understanding of software development lifecycle
  • Strong problem-solving and analytical skills
  • Excellent communication and teamwork abilities

📌 Desired Skills:
  • Experience with medical device software development
  • Knowledge of FDA regulations and quality systems
  • Experience with testing and validation processes
  • Understanding of embedded systems and real-time software"""
        },
        
        # ByteDance Software Development Engineer in Test Intern
        "jobs.bytedance.com/en/position/7533346574367377672/detail": {
            "description": "Software Development Engineer in Test (SDET) internship at ByteDance focusing on e-commerce platform testing and automation. This role involves developing automated testing frameworks and ensuring quality for global e-commerce applications.",
            "skills": ["Python", "Java", "JavaScript", "Selenium", "Testing", "Automation", "E-commerce", "API Testing"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Software Engineering, or related field

📌 Required Skills:
  • Programming experience in Python, Java, or JavaScript
  • Understanding of software testing methodologies
  • Experience with automated testing frameworks
  • Knowledge of web technologies and APIs

📌 Desired Skills:
  • Experience with Selenium or similar testing tools
  • Knowledge of e-commerce platforms
  • Understanding of CI/CD pipelines
  • Experience with performance testing"""
        },
        
        # ByteDance Frontend Software Engineer Intern
        "jobs.bytedance.com/en/position/7533346008655825159/detail": {
            "description": "Frontend Software Engineer internship at ByteDance focusing on e-commerce platform development. This role involves building user interfaces and frontend applications for global e-commerce platforms.",
            "skills": ["JavaScript", "React", "Vue", "HTML", "CSS", "Frontend", "E-commerce", "Web Development"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Software Engineering, or related field

📌 Required Skills:
  • Strong JavaScript programming skills
  • Experience with modern frontend frameworks (React, Vue, Angular)
  • Knowledge of HTML, CSS, and web technologies
  • Understanding of responsive design principles

📌 Desired Skills:
  • Experience with e-commerce platforms
  • Knowledge of state management (Redux, Vuex)
  • Understanding of web performance optimization
  • Experience with TypeScript"""
        },
        
        # ByteDance Backend Software Engineer Intern
        "jobs.bytedance.com/en/position/7532668388906256658/detail": {
            "description": "Backend Software Engineer internship at ByteDance focusing on e-commerce platform backend development. This role involves developing server-side applications, APIs, and database systems for global e-commerce platforms.",
            "skills": ["Python", "Java", "Go", "Backend", "API Development", "Database", "E-commerce", "Microservices"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Software Engineering, or related field

📌 Required Skills:
  • Strong programming skills in Python, Java, or Go
  • Understanding of backend development principles
  • Knowledge of API development and database design
  • Experience with server-side technologies

📌 Desired Skills:
  • Experience with microservices architecture
  • Knowledge of cloud platforms (AWS, GCP, Azure)
  • Understanding of distributed systems
  • Experience with e-commerce backend systems"""
        },
        
        # Chase Software Engineer Program
        "jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1002/jobs/job/210650080": {
            "description": "Software Engineer Program internship at JPMorgan Chase focusing on financial technology development. This role involves developing software solutions for banking and financial services.",
            "skills": ["Java", "Python", "SQL", "Financial Technology", "Banking", "Software Engineering"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Engineering, or related field

📌 Required Skills:
  • Programming experience in Java, Python, or similar languages
  • Understanding of software development principles
  • Strong analytical and problem-solving skills
  • Interest in financial technology

📌 Desired Skills:
  • Knowledge of financial systems and banking
  • Experience with databases and SQL
  • Understanding of security principles
  • Interest in fintech innovation"""
        },
        
        # GDIT Software Developer Associate
        "gdit.wd5.myworkdayjobs.com/en-US/gdit_earlytalent/job/USA-LA-Bossier-City/Software-Developer-Associate--Intern_": {
            "description": "Software Developer Associate internship at GDIT focusing on government and defense software development. This role involves developing software solutions for government agencies and defense contractors.",
            "skills": ["Java", "Python", "C++", "Government", "Defense", "Software Development"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Software Engineering, or related field

📌 Required Skills:
  • Programming experience in Java, Python, or C++
  • Understanding of software development lifecycle
  • Strong problem-solving abilities
  • US Citizenship required for some positions

📌 Desired Skills:
  • Knowledge of government software systems
  • Understanding of security clearances
  • Experience with defense industry software
  • Interest in public sector technology"""
        },
        
        # SEL Software Application Engineer Intern
        "selinc.wd1.myworkdayjobs.com/en-US/SEL/job/Washington---Pullman/Software-Application-Engineer-Intern_": {
            "description": "Software Application Engineer internship at SEL focusing on power systems and electrical engineering software. This role involves developing software for power grid management and electrical systems.",
            "skills": ["C++", "Python", "Electrical Engineering", "Power Systems", "Real-time Systems"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Electrical Engineering, or related field

📌 Required Skills:
  • Programming experience in C++ or Python
  • Understanding of software engineering principles
  • Interest in power systems and electrical engineering
  • Strong analytical skills

📌 Desired Skills:
  • Knowledge of power systems and electrical engineering
  • Experience with real-time systems
  • Understanding of industrial software development
  • Interest in grid technology"""
        },
        
        # Tencent Cloud Media Services Intern
        "tencent.wd1.myworkdayjobs.com/en-US/Tencent_Careers/job/US-California-Palo-Alto/Cloud-Media-Services-Intern_": {
            "description": "Cloud Media Services internship at Tencent focusing on cloud computing and media processing. This role involves developing cloud-based solutions for media streaming and processing.",
            "skills": ["Cloud Computing", "Media Processing", "Python", "Java", "AWS", "Azure"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Engineering, or related field

📌 Required Skills:
  • Programming experience in Python, Java, or similar languages
  • Understanding of cloud computing concepts
  • Interest in media processing and streaming
  • Strong technical skills

📌 Desired Skills:
  • Experience with cloud platforms (AWS, Azure, GCP)
  • Knowledge of media processing technologies
  • Understanding of streaming protocols
  • Interest in video and audio processing"""
        },
        
        # HPR Software Engineering Intern
        "job-boards.greenhouse.io/hyannisportresearch/jobs/6667961003": {
            "description": "Software Engineering internship at HPR (Hyannis Port Research) focusing on financial technology and quantitative research. This role involves developing software for high-frequency trading and financial analysis.",
            "skills": ["Python", "Java", "Go", "R", "Bash", "Shell", "Less", "Ai", "Aws", "Software Engineering", "Programming", "Coding", "Algorithm", "Data Structures", "Linux", "Fintech"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Engineering, Mathematics, or related field

📌 Required Skills:
  • Strong programming skills in Python, Java, or C++
  • Understanding of algorithms and data structures
  • Knowledge of Linux systems and shell scripting
  • Interest in financial technology and quantitative analysis

📌 Desired Skills:
  • Experience with cloud platforms (AWS, GCP)
  • Knowledge of financial markets and trading
  • Understanding of high-performance computing
  • Experience with quantitative analysis tools"""
        },
        
        # Allium Engineering Intern - AI
        "jobs.ashbyhq.com/allium/5d697ce5-b820-45c0-a101-86a05e1fb15e": {
            "description": "Engineering Intern - AI at Allium focusing on artificial intelligence and machine learning development. This role involves developing AI-powered software solutions and machine learning models.",
            "skills": ["Java", "Javascript", "R", "Ai", "Intern", "Engineering", "Machine Learning"],
            "requirements": """📌 Education:
  • Currently pursuing a Bachelor's or Master's degree in Computer Science, Engineering, or related field

📌 Required Skills:
  • Programming experience in Java, JavaScript, or Python
  • Understanding of machine learning and AI concepts
  • Strong mathematical and analytical skills
  • Interest in artificial intelligence

📌 Desired Skills:
  • Experience with machine learning frameworks
  • Knowledge of data science and statistics
  • Understanding of neural networks and deep learning
  • Experience with AI/ML projects"""
        }
    }
    
    # Check if we have manual requirements for this URL
    for url_pattern, requirements in manual_requirements_db.items():
        if url_pattern in apply_link:
            return requirements
    
    return None

def extract_detailed_requirements(soup, job_text):
    """
    Extract detailed job requirements including experience, education, required skills, and desired skills.
    """
    requirements = []
    
    # Look for common requirement sections
    requirement_sections = [
        "experience", "education", "required skills", "desired skills", "qualifications",
        "requirements", "minimum qualifications", "preferred qualifications", "what you need",
        "what you'll need", "technical skills", "competencies", "knowledge", "abilities",
        "essential functions", "job duties", "responsibilities", "background", "prerequisites"
    ]
    
    # Find requirement sections in the HTML
    for section in requirement_sections:
        # Look for headings containing these keywords
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b', 'span', 'div'])
        for heading in headings:
            heading_text = heading.get_text().lower()
            if section in heading_text:
                # Get the content following this heading
                content = []
                next_elem = heading.find_next_sibling()
                count = 0
                while next_elem and next_elem.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and count < 10:
                    if next_elem.name in ['p', 'li', 'div', 'span']:
                        text = next_elem.get_text(strip=True)
                        if text and len(text) > 10:  # Only include substantial content
                            content.append(text)
                    next_elem = next_elem.find_next_sibling()
                    count += 1
                
                if content:
                    section_title = heading.get_text().strip()
                    requirements.append(f"📌 {section_title}:")
                    # Limit to 3 items per section to avoid repetition
                    for item in content[:3]:
                        requirements.append(f"  • {item}")
                    requirements.append("")
    
    # If no structured requirements found, try specific job site patterns
    if not requirements:
        requirements = extract_from_specific_sites(soup, job_text)
    
    # If still no requirements, extract from general text
    if not requirements:
        # Look for bullet points or list items
        lists = soup.find_all(['ul', 'ol'])
        for lst in lists:
            items = lst.find_all('li')
            if items:
                for item in items[:5]:  # Limit to 5 items
                    text = item.get_text(strip=True)
                    if text and len(text) > 10:
                        requirements.append(f"  • {text}")
    
    # If still no requirements, extract sentences containing key words
    if not requirements:
        sentences = job_text.split('.')
        key_words = ['experience', 'education', 'required', 'desired', 'skills', 'knowledge', 'ability', 'degree', 'background', 'qualification']
        for sentence in sentences[:5]:  # Limit to 5 sentences
            if any(word in sentence for word in key_words) and len(sentence) > 20:
                requirements.append(f"  • {sentence.strip()}")
    
    # If still no requirements, look for any text that might be requirements
    if not requirements:
        # Look for any text that mentions requirements or qualifications
        paragraphs = soup.find_all('p')
        for p in paragraphs[:3]:  # Limit to 3 paragraphs
            text = p.get_text(strip=True)
            if text and len(text) > 30 and any(word in text.lower() for word in ['experience', 'education', 'required', 'skills', 'degree', 'background']):
                requirements.append(f"  • {text}")
    
    # Remove duplicates and limit length
    if requirements:
        # Remove duplicate lines
        unique_requirements = []
        seen = set()
        for req in requirements:
            if req not in seen:
                unique_requirements.append(req)
                seen.add(req)
        
        # Limit total length
        result = "\n".join(unique_requirements)
        if len(result) > 800:
            # Truncate but keep complete sections
            lines = result.split('\n')
            truncated = []
            total_length = 0
            for line in lines:
                if total_length + len(line) > 800:
                    break
                truncated.append(line)
                total_length += len(line)
            result = "\n".join(truncated) + "..."
        
        return result
    
    return "Requirements not available"

def extract_from_specific_sites(soup, job_text):
    """
    Extract requirements from specific job site platforms.
    """
    requirements = []
    
    # Workday job sites (like KBR, Medtronic, etc.)
    workday_selectors = [
        '[data-automation-id="jobDescriptionText"]',
        '[data-automation-id="jobDescription"]',
        '.job-description',
        '.job-description-text',
        '[data-testid="job-description"]',
        '.job-details',
        '.job-content'
    ]
    
    for selector in workday_selectors:
        elements = soup.select(selector)
        if elements:
            text = elements[0].get_text(separator=' ', strip=True)
            if len(text) > 100:
                # Extract requirements from the text
                req_sections = extract_requirements_from_text(text)
                if req_sections:
                    requirements.extend(req_sections)
                break
    
    # Greenhouse job sites (like HPR)
    greenhouse_selectors = [
        '.job-description',
        '.job-content',
        '#job-description',
        '.description'
    ]
    
    if not requirements:
        for selector in greenhouse_selectors:
            elements = soup.select(selector)
            if elements:
                text = elements[0].get_text(separator=' ', strip=True)
                if len(text) > 100:
                    req_sections = extract_requirements_from_text(text)
                    if req_sections:
                        requirements.extend(req_sections)
                    break
    
    # Oracle job sites (like Chase)
    oracle_selectors = [
        '.job-description',
        '.job-content',
        '.description',
        '[data-testid="job-description"]'
    ]
    
    if not requirements:
        for selector in oracle_selectors:
            elements = soup.select(selector)
            if elements:
                text = elements[0].get_text(separator=' ', strip=True)
                if len(text) > 100:
                    req_sections = extract_requirements_from_text(text)
                    if req_sections:
                        requirements.extend(req_sections)
                    break
    
    # Ashby job sites (like Allium)
    ashby_selectors = [
        '.job-description',
        '.job-content',
        '.description',
        '[data-testid="job-description"]'
    ]
    
    if not requirements:
        for selector in ashby_selectors:
            elements = soup.select(selector)
            if elements:
                text = elements[0].get_text(separator=' ', strip=True)
                if len(text) > 100:
                    req_sections = extract_requirements_from_text(text)
                    if req_sections:
                        requirements.extend(req_sections)
                    break
    
    return requirements

def extract_requirements_from_text(text):
    """
    Extract requirements from job description text.
    """
    requirements = []
    text_lower = text.lower()
    
    # Look for requirement sections
    sections = [
        ("experience", ["experience", "work experience", "professional experience"]),
        ("education", ["education", "degree", "bachelor", "master", "phd", "academic"]),
        ("required skills", ["required skills", "required qualifications", "minimum qualifications", "requirements"]),
        ("desired skills", ["desired skills", "preferred qualifications", "nice to have", "bonus"]),
        ("technical skills", ["technical skills", "programming", "software", "technology"]),
        ("responsibilities", ["responsibilities", "duties", "job duties", "role"])
    ]
    
    for section_name, keywords in sections:
        for keyword in keywords:
            if keyword in text_lower:
                # Find the section content
                start_idx = text_lower.find(keyword)
                if start_idx != -1:
                    # Get text after the keyword
                    section_text = text[start_idx:start_idx + 500]  # Get 500 chars after keyword
                    
                    # Split into sentences and find relevant ones
                    sentences = section_text.split('.')
                    relevant_sentences = []
                    
                    for sentence in sentences[:5]:  # Limit to 5 sentences
                        sentence = sentence.strip()
                        if len(sentence) > 20 and any(word in sentence.lower() for word in ['experience', 'education', 'required', 'skills', 'degree', 'background', 'knowledge', 'ability']):
                            relevant_sentences.append(sentence)
                    
                    if relevant_sentences:
                        requirements.append(f"📌 {section_name.title()}:")
                        for sentence in relevant_sentences:
                            requirements.append(f"  • {sentence}")
                        requirements.append("")
                        break
    
    return requirements

def extract_skills_from_job_page(job_text):
    """
    Extract technical skills from the actual job posting text.
    """
    # Enhanced skill keywords for job page extraction
    skill_keywords = [
        # Programming Languages
        "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "kotlin", "swift",
        "php", "ruby", "scala", "r", "matlab", "perl", "bash", "shell", "powershell",
        
        # Web Technologies
        "react", "angular", "vue", "node.js", "express", "django", "flask", "spring", "laravel",
        "html", "css", "sass", "less", "bootstrap", "tailwind", "jquery", "ajax", "rest api",
        "graphql", "websocket", "http", "https", "json", "xml",
        
        # Databases & Data
        "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch", "cassandra",
        "data analysis", "data science", "data engineering", "etl", "data pipeline",
        "machine learning", "deep learning", "ai", "artificial intelligence", "neural networks",
        "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn",
        "computer vision", "nlp", "natural language processing", "recommendation systems",
        
        # Cloud & DevOps
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "jenkins", "gitlab",
        "github", "git", "ci/cd", "terraform", "ansible", "prometheus", "grafana",
        
        # Software Engineering
        "software engineering", "software development", "programming", "coding", "algorithm",
        "data structures", "object-oriented", "functional programming", "design patterns",
        "microservices", "api development", "backend", "frontend", "full stack", "fullstack",
        "mobile development", "ios", "android", "react native", "flutter", "xamarin",
        
        # Testing & Quality
        "testing", "unit testing", "integration testing", "qa", "quality assurance",
        "test automation", "selenium", "junit", "pytest", "jest", "cypress",
        
        # Tools & Frameworks
        "maven", "gradle", "npm", "yarn", "webpack", "babel", "eslint", "prettier",
        "intellij", "vscode", "eclipse", "vim", "emacs", "linux", "unix", "macos",
        
        # Domain Knowledge
        "e-commerce", "fintech", "healthcare", "cybersecurity", "blockchain", "iot",
        "embedded systems", "fpga", "hardware", "robotics", "autonomous vehicles",
        
        # Soft Skills
        "leadership", "communication", "teamwork", "problem solving", "agile", "scrum",
        "project management", "mentoring", "collaboration", "presentation",
        
        # Academic/Student Terms
        "student", "intern", "internship", "co-op", "research", "thesis", "academic",
        "university", "college", "bachelor", "master", "phd", "graduate", "undergraduate",
        "computer science", "engineering", "mathematics", "statistics", "physics"
    ]
    
    # Use LLM to dynamically extract skills from job page text
    from matching.llm_skill_extractor import extract_job_skills_with_llm
    
    skills = extract_job_skills_with_llm("", job_text, "")
    
    return skills

def extract_job_description(soup):
    """
    Extract a clean, concise job description from the job posting page.
    """
    try:
        # Look for common job description containers
        description_selectors = [
            '[data-automation-id="jobDescriptionText"]',
            '[data-automation-id="jobDescription"]',
            '.job-description',
            '.job-description-text',
            '[data-testid="job-description"]',
            '.job-details',
            '.job-content',
            '.description',
            '#job-description',
            '.job-summary',
            '.role-description',
            '.job-info',
            '.position-description',
            '.job-overview'
        ]
        
        description_text = ""
        
        # Try to find description in specific containers
        for selector in description_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator=' ', strip=True)
                if len(text) > 50:  # Ensure we have meaningful content
                    description_text = text
                    break
        
        # If no specific container found, try to extract from body
        if not description_text:
            body = soup.find('body')
            if body:
                # Get all text and filter out navigation/UI elements
                all_text = body.get_text(separator=' ', strip=True)
                
                # Split into sentences and filter
                sentences = []
                for sentence in all_text.split('.'):
                    sentence = sentence.strip()
                    if len(sentence) > 20:  # Only meaningful sentences
                        # Filter out UI/navigation text
                        skip_words = [
                            'menu', 'dashboard', 'log in', 'sign up', 'share', 'apply', 
                            'job requirements', 'requirements:', 'qualifications:', 'skills:', 
                            'about this role', 'about this role:', '📋 job requirements:',
                            'job requirements:', 'get referrals', 'simplify\'s take', 'what believers are saying',
                            'what critics are saying', 'significant headcount growth', 'want to apply to',
                            'you have', 'ways to', 'get a', 'referral', 'from your', 'network',
                            'open menu', 'matches', 'jobs', 'job tracker', 'documents', 'profile',
                            'back', 'work here?', 'claim your company', 'website', 'open user menu',
                            'overview', 'reviews', 'interviews', 'about', 'simplify\'s rating',
                            'why', 'rated', 'competitive edge', 'growth potential', 'differentiation',
                            'industries', 'company stage', 'overview', 'get s', 'simplify\'s take',
                            'what believers are saying', 'what critics are saying', 'integration with',
                            'expansion of', 'digital fixed-income trading', 'meets growing advisor demand',
                            'for diverse products', 'data privacy concerns', 'sensitive client information'
                        ]
                        should_skip = any(word in sentence.lower() for word in skip_words)
                        
                        if not should_skip:
                            sentences.append(sentence)
                
                # Take first 8 sentences maximum
                if sentences:
                    description_text = '. '.join(sentences[:8])
        
        # If still no description, use the page title and any available text
        if not description_text:
            title = soup.find('title')
            if title:
                description_text = title.get_text(strip=True)
            
            # Add any available text from the page
            body_text = soup.find('body')
            if body_text:
                text = body_text.get_text(separator=' ', strip=True)
                if len(text) > 100:
                    # Take the first 800 characters as a fallback
                    description_text = text[:800]
        
        # Clean and limit the description
        if description_text:
            # Remove excessive whitespace
            description_text = ' '.join(description_text.split())
            
            # Remove unwanted phrases and text - comprehensive list
            phrases_to_remove = [
                'job requirements',
                'requirements:',
                'qualifications:',
                'skills:',
                'about this role',
                'about this role:',
                '📋 job requirements:',
                '📋 job requirements',
                'job requirements:',
                'headquarters',
                'founded',
                'company size',
                'total funding',
                'get referrals',
                'simplify\'s take',
                'what believers are saying',
                'what critics are saying',
                'significant headcount growth',
                'want to apply to',
                'you have',
                'ways to',
                'get a',
                'referral',
                'from your',
                'network',
                'open menu',
                'dashboard',
                'matches',
                'jobs',
                'job tracker',
                'documents',
                'profile',
                'log in',
                'back',
                'work here?',
                'claim your company',
                'website',
                'open user menu',
                'share',
                'overview',
                'reviews',
                'interviews',
                'about',
                'simplify\'s rating',
                'why',
                'rated',
                'competitive edge',
                'growth potential',
                'differentiation',
                'industries',
                'company stage',
                'overview',
                'get s',
                'simplify\'s take',
                'what believers are saying',
                'what critics are saying',
                'integration with',
                'expansion of',
                'digital fixed-income trading',
                'meets growing advisor demand',
                'for diverse products',
                'data privacy concerns',
                'sensitive client information',
                'altruist\'s $152m funding round',
                'indicates strong investor confidence',
                'and growth potential',
                'integration with thyme',
                'enhances ai capabilities',
                'improving client interactions',
                'for rias',
                'expansion of digital',
                'fixed-income trading',
                'meets growing advisor',
                'demand for diverse',
                'products',
                'what critics are saying',
                'integration of ai',
                'capabilities may raise',
                'data privacy concerns',
                'for sensitive client',
                'information'
            ]
            
            for phrase in phrases_to_remove:
                description_text = description_text.replace(phrase, '').replace(phrase.upper(), '')
            
            # Clean up any remaining artifacts
            description_text = description_text.replace('  ', ' ')
            description_text = description_text.strip()
            
            # Remove any remaining "About this role:" text - more aggressive filtering
            role_phrases = [
                'about this role:',
                'about this role',
                'about the role:',
                'about the role',
                'role description:',
                'role description',
                'position description:',
                'position description'
            ]
            
            # First, remove from the beginning
            for phrase in role_phrases:
                if description_text.lower().startswith(phrase):
                    description_text = description_text[len(phrase):].strip()
                    break
            
            # Then remove from anywhere in the text (case insensitive)
            for phrase in role_phrases:
                description_text = description_text.replace(phrase, '').replace(phrase.title(), '').replace(phrase.upper(), '')
            
            # Also remove any remaining "About this role:" that might have been missed
            if 'about this role:' in description_text.lower():
                description_text = description_text.lower().replace('about this role:', '').strip()
                # Capitalize first letter
                if description_text:
                    description_text = description_text[0].upper() + description_text[1:]
            
            # Remove "📋 Job Requirements:" and similar phrases from anywhere in the text
            requirements_phrases = [
                '📋 job requirements:',
                '📋 job requirements',
                'job requirements:',
                'job requirements',
                'requirements:',
                'requirements',
                'qualifications:',
                'qualifications',
                'skills:',
                'skills'
            ]
            
            for phrase in requirements_phrases:
                # Remove from anywhere in the text
                description_text = description_text.replace(phrase, '').replace(phrase.title(), '').replace(phrase.upper(), '')
                # Also remove with emoji variations
                description_text = description_text.replace('📋 ' + phrase, '').replace('📋 ' + phrase.title(), '').replace('📋 ' + phrase.upper(), '')
            
            # Remove any text that ends with "..." and replace with clean period
            if description_text.endswith('...'):
                description_text = description_text[:-3] + '.'
            elif not description_text.endswith('.'):
                description_text += '.'
            
            # Clean up any double periods or excessive whitespace
            description_text = description_text.replace('..', '.').replace('  ', ' ').strip()
            
            # Limit to reasonable length
            if len(description_text) > 800:
                # Find the last complete sentence within 800 characters
                truncated = description_text[:800]
                last_period = truncated.rfind('.')
                if last_period > 600:  # Only if we have a reasonable sentence
                    description_text = truncated[:last_period + 1]
                else:
                    description_text = truncated + '.'
            
            # Add "About this company:" prefix if not already present
            if not description_text.lower().startswith('about this company'):
                description_text = f"About this company: {description_text}"
            
            return description_text
        
        # Fallback description
        return "About this company: Software Engineering internship position. Please click 'Apply Here' for detailed information."
        
    except Exception as e:
        print(f"⚠️ Error extracting job description: {e}")
        return "About this company: Software Engineering internship position. Please click 'Apply Here' for detailed information."

def filter_jobs_by_date(jobs, max_days=None):
    """
    Filter jobs based on how recently they were posted.
    
    Args:
        jobs: List of job dictionaries
        max_days: Maximum number of days since posted (e.g., 30 for jobs posted in last 30 days)
                  If None, return all jobs
    
    Returns:
        Filtered list of jobs
    """
    if max_days is None:
        return jobs
    
    filtered = []
    skipped = 0
    
    for job in jobs:
        days_since = job.get('days_since_posted')
        
        if days_since is None:
            # If we can't determine the date, include it (benefit of doubt)
            filtered.append(job)
        elif days_since <= max_days:
            filtered.append(job)
        else:
            skipped += 1
    
    if skipped > 0:
        print(f"📅 [Date Filter] Filtered out {skipped} jobs older than {max_days} days")
    
    return filtered

def scrape_github_internships(keyword="intern", max_results=10000, incremental=False, max_days_old=None):
    """
    Scrape internship listings from the Summer 2026 Tech Internships GitHub repository.
    This is much more reliable than scraping individual company career sites.
    
    Args:
        keyword: Search keyword (not used for GitHub scraping)
        max_results: Maximum number of results to return
        incremental: If True, only return new jobs not in database
        max_days_old: If set, only return jobs posted within this many days (e.g., 30 for last 30 days)
    """
    scrape_type = "incremental" if incremental else "full"
    date_filter_msg = f" (last {max_days_old} days)" if max_days_old else ""
    print(f"🔍 [GitHub Internships] Starting {scrape_type} scrape{date_filter_msg} from Summer 2026 Tech Internships repository...")
    
    try:
        # Get the raw markdown content from GitHub
        response = requests.get(GITHUB_INTERNSHIPS_URL)
        response.raise_for_status()
        
        # Parse the markdown content directly
        markdown_content = response.text
        
        # Parse the markdown table structure
        all_jobs = parse_internship_table(markdown_content, max_results)
        
        # Apply date filter if specified
        if max_days_old is not None:
            all_jobs = filter_jobs_by_date(all_jobs, max_days_old)
        
        if incremental:
            # Filter to only new jobs using database comparison
            try:
                from job_cache import get_new_jobs_only
                filtered_jobs = get_new_jobs_only(all_jobs)
                print(f"✅ [GitHub Internships] {scrape_type} scrape: {len(filtered_jobs)} new jobs (from {len(all_jobs)} total)")
                return filtered_jobs
            except Exception as e:
                print(f"⚠️ [GitHub Internships] Incremental filtering failed: {e}")
                print(f"📝 [GitHub Internships] Falling back to full scrape")
                return all_jobs
        else:
            print(f"✅ [GitHub Internships] {scrape_type} scrape: {len(all_jobs)} total jobs")
            return all_jobs
        
    except Exception as e:
        print(f"❌ [GitHub Internships] Error during {scrape_type} scrape: {e}")
        return []

def extract_skills_from_job(job):
    """
    Extract skills from job title and description.
    Uses AGGRESSIVE role inference from job title combined with LLM extraction.
    """
    job_title = job.get('title', '')
    job_description = job.get('description', '')
    company = job.get('company', '')
    
    # STEP 1: Aggressively infer role-specific skills from title FIRST
    title_skills = infer_skills_from_title_aggressive(job_title)
    
    # STEP 2: Try LLM extraction to enhance/refine
    try:
        from matching.llm_skill_extractor import extract_job_skills_with_llm
        llm_skills = extract_job_skills_with_llm(job_title, job_description, company)
        
        if llm_skills and len(llm_skills) > 2:
            # Merge title skills with LLM skills, removing duplicates
            combined = title_skills.copy()
            for skill in llm_skills:
                if skill not in combined and skill.lower() not in [s.lower() for s in combined]:
                    combined.append(skill)
            return combined[:8]  # Limit to 8 skills
        else:
            # LLM didn't find much, use title-inferred skills
            return title_skills
            
    except Exception as e:
        print(f"⚠️ LLM extraction failed, using title-based inference: {e}")
        return title_skills

def infer_skills_from_title_aggressive(job_title):
    """
    AGGRESSIVELY infer role-specific skills from job title.
    Every job gets unique, relevant skills based on its title.
    """
    title_lower = job_title.lower()
    skills = []
    
    # Extract specific technologies mentioned in title
    tech_map = {
        'react': 'React', 'angular': 'Angular', 'vue': 'Vue',
        'python': 'Python', 'java': 'Java', 'javascript': 'JavaScript',
        'typescript': 'TypeScript', 'go': 'Go', 'rust': 'Rust',
        'c++': 'C++', 'c#': 'C#', 'swift': 'Swift', 'kotlin': 'Kotlin',
        'aws': 'AWS', 'azure': 'Azure', 'gcp': 'GCP',
        'docker': 'Docker', 'kubernetes': 'Kubernetes',
        'node': 'Node.js', 'sql': 'SQL', '.net': '.NET'
    }
    
    for keyword, tech in tech_map.items():
        if keyword in title_lower:
            skills.append(tech)
    
    # Role-based skill inference (order matters - check specific before generic)
    if "frontend" in title_lower or "front-end" in title_lower or "front end" in title_lower:
        skills.extend(['JavaScript', 'React', 'HTML', 'CSS', 'TypeScript', 'Frontend Development'])
    elif "backend" in title_lower or "back-end" in title_lower or "back end" in title_lower:
        skills.extend(['Python', 'Java', 'SQL', 'API Development', 'Backend Development', 'REST APIs'])
    elif "full stack" in title_lower or "fullstack" in title_lower or "full-stack" in title_lower:
        skills.extend(['JavaScript', 'Python', 'SQL', 'React', 'Node.js', 'Full Stack Development'])
    elif "mobile" in title_lower:
        skills.extend(['Mobile Development', 'Swift', 'Kotlin', 'Java', 'iOS', 'Android'])
    elif "data scien" in title_lower or "data analy" in title_lower:
        skills.extend(['Python', 'SQL', 'Data Analysis', 'Machine Learning', 'Statistics', 'Pandas'])
    elif "data engineer" in title_lower or ("data" in title_lower and "engineer" in title_lower):
        skills.extend(['Python', 'SQL', 'ETL', 'Data Pipelines', 'Spark', 'Data Engineering'])
    elif "machine learning" in title_lower or "ml engineer" in title_lower or " ai " in title_lower:
        skills.extend(['Python', 'Machine Learning', 'TensorFlow', 'PyTorch', 'Deep Learning'])
    elif "devops" in title_lower or "sre" in title_lower:
        skills.extend(['AWS', 'Docker', 'Kubernetes', 'CI/CD', 'Linux', 'DevOps'])
    elif "cloud" in title_lower:
        skills.extend(['AWS', 'Azure', 'Cloud Computing', 'Docker', 'Python'])
    elif "security" in title_lower or "cybersecurity" in title_lower or "cyber" in title_lower:
        skills.extend(['Cybersecurity', 'Network Security', 'Python', 'Security Analysis'])
    elif "qa" in title_lower or "test" in title_lower or "sdet" in title_lower or "quality" in title_lower:
        skills.extend(['Testing', 'Test Automation', 'Selenium', 'Python', 'Java', 'QA'])
    elif "embedded" in title_lower or "firmware" in title_lower:
        skills.extend(['C++', 'C', 'Embedded Systems', 'Firmware', 'Hardware'])
    elif "ios" in title_lower:
        skills.extend(['Swift', 'iOS', 'Xcode', 'Mobile Development'])
    elif "android" in title_lower:
        skills.extend(['Kotlin', 'Java', 'Android', 'Mobile Development'])
    elif "automation" in title_lower:
        skills.extend(['Python', 'Automation', 'Testing', 'Scripting'])
    elif "database" in title_lower or "dba" in title_lower:
        skills.extend(['SQL', 'Database Design', 'MySQL', 'PostgreSQL'])
    elif "salesforce" in title_lower or "crm" in title_lower:
        skills.extend(['Salesforce', 'CRM', 'Apex', 'Lightning'])
    elif "infrastructure" in title_lower:
        skills.extend(['Python', 'Infrastructure', 'Cloud Computing', 'DevOps'])
    else:
        # Generic software engineering - but still specific!
        skills.extend(['Python', 'Java', 'Software Development', 'Algorithms', 'Data Structures'])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_skills = []
    for skill in skills:
        if skill.lower() not in seen:
            seen.add(skill.lower())
            unique_skills.append(skill)
    
    return unique_skills[:8]  # Limit to 8 skills

def infer_skills_from_title(job_title):
    """
    Legacy function - redirects to aggressive version.
    """
    return infer_skills_from_title_aggressive(job_title)

def extract_job_metadata(job_title, location, age, apply_link):
    """
    Extract metadata from job information.
    """
    metadata = {
        "job_type": "Internship",
        "experience_level": "Entry-level",
        "location_type": "On-site",
        "deadline": None,
        "sponsorship": "Unknown",
        "salary_range": None,
        "application_age": age
    }
    
    # Determine job type
    title_lower = job_title.lower()
    if "co-op" in title_lower or "coop" in title_lower:
        metadata["job_type"] = "Co-op"
    elif "intern" in title_lower:
        metadata["job_type"] = "Internship"
    elif "program" in title_lower:
        metadata["job_type"] = "Program"
    elif "associate" in title_lower:
        metadata["job_type"] = "Associate"
    
    # Determine experience level
    if any(word in title_lower for word in ["senior", "lead", "principal", "staff"]):
        metadata["experience_level"] = "Senior"
    elif any(word in title_lower for word in ["junior", "entry", "associate"]):
        metadata["experience_level"] = "Entry-level"
    else:
        metadata["experience_level"] = "Entry-level"  # Default for internships
    
    # Determine location type
    location_lower = location.lower()
    if "remote" in location_lower:
        metadata["location_type"] = "Remote"
    elif "hybrid" in location_lower:
        metadata["location_type"] = "Hybrid"
    elif "on-site" in location_lower or "onsite" in location_lower:
        metadata["location_type"] = "On-site"
    else:
        metadata["location_type"] = "On-site"  # Default
    
    # Determine sponsorship status
    if "🛂" in job_title:
        metadata["sponsorship"] = "No Sponsorship"
    elif "🇺🇸" in job_title:
        metadata["sponsorship"] = "US Citizenship Required"
    else:
        metadata["sponsorship"] = "Unknown"
    
    # Parse age for deadline estimation
    if age and age != "Unknown":
        try:
            if "d" in age:
                days = int(age.replace("d", ""))
                metadata["deadline"] = f"Posted {days} days ago"
            elif "mo" in age:
                months = int(age.replace("mo", ""))
                metadata["deadline"] = f"Posted {months} months ago"
            elif "w" in age:
                weeks = int(age.replace("w", ""))
                metadata["deadline"] = f"Posted {weeks} weeks ago"
        except:
            metadata["deadline"] = age
    
    return metadata

def parse_date_to_days(date_string):
    """
    Parse various date formats and convert to days since posted.
    Handles formats like:
    - "Oct 21" (Month Day)
    - "2025-10-21" (ISO date)
    - "21 days ago"
    - "3 weeks ago"
    - "2 months ago"
    - "Yesterday"
    - "Today"
    
    Returns:
        int: Number of days since posted, or None if unable to parse
    """
    if not date_string or date_string == "Unknown":
        return None
    
    date_string = date_string.strip().lower()
    
    try:
        # Import datetime for date parsing
        from datetime import datetime, timedelta
        import re
        
        # Handle relative time formats
        if "today" in date_string or "just now" in date_string:
            return 0
        elif "yesterday" in date_string:
            return 1
        elif "day" in date_string or "d" == date_string[-1]:
            # Format: "X days ago" or "Xd"
            match = re.search(r'(\d+)\s*d', date_string)
            if match:
                return int(match.group(1))
        elif "week" in date_string or "w" == date_string[-1]:
            # Format: "X weeks ago" or "Xw"
            match = re.search(r'(\d+)\s*w', date_string)
            if match:
                return int(match.group(1)) * 7
        elif "month" in date_string or "mo" in date_string:
            # Format: "X months ago" or "Xmo"
            match = re.search(r'(\d+)\s*mo', date_string)
            if match:
                return int(match.group(1)) * 30
        elif "year" in date_string or "y" == date_string[-1]:
            # Format: "X years ago" or "Xy"
            match = re.search(r'(\d+)\s*y', date_string)
            if match:
                return int(match.group(1)) * 365
        
        # Handle date formats like "Oct 21", "Oct 21, 2025", "2025-10-21"
        current_year = datetime.now().year
        
        # Try ISO format first: YYYY-MM-DD
        try:
            posted_date = datetime.strptime(date_string, '%Y-%m-%d')
            days_diff = (datetime.now() - posted_date).days
            return max(0, days_diff)  # Don't return negative days
        except:
            pass
        
        # Try format: "Month Day" (e.g., "Oct 21")
        try:
            # Add current year
            posted_date = datetime.strptime(f"{date_string} {current_year}", '%b %d %Y')
            days_diff = (datetime.now() - posted_date).days
            
            # If the date is in the future, it was probably from last year
            if days_diff < 0:
                posted_date = datetime.strptime(f"{date_string} {current_year - 1}", '%b %d %Y')
                days_diff = (datetime.now() - posted_date).days
            
            return max(0, days_diff)
        except:
            pass
        
        # Try format: "Month Day, Year" (e.g., "Oct 21, 2025")
        try:
            posted_date = datetime.strptime(date_string, '%b %d, %Y')
            days_diff = (datetime.now() - posted_date).days
            return max(0, days_diff)
        except:
            pass
        
        # Try format: "MM/DD/YYYY" or "DD/MM/YYYY"
        try:
            posted_date = datetime.strptime(date_string, '%m/%d/%Y')
            days_diff = (datetime.now() - posted_date).days
            return max(0, days_diff)
        except:
            pass
        
        try:
            posted_date = datetime.strptime(date_string, '%d/%m/%Y')
            days_diff = (datetime.now() - posted_date).days
            return max(0, days_diff)
        except:
            pass
        
        print(f"⚠️ [Date Parser] Could not parse date format: '{date_string}'")
        return None
        
    except Exception as e:
        print(f"⚠️ [Date Parser] Error parsing date '{date_string}': {e}")
        return None

def parse_internship_table(content, max_results):
    jobs = []
    
    print(f"🔍 [GitHub] Parsing {len(content)} characters...")
    
    # Use BeautifulSoup to parse the HTML table
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, 'html.parser')
    
    # Find all tables
    tables = soup.find_all('table')
    
    if not tables:
        print("❌ [GitHub] No tables found in content")
        return jobs
    
    # Look for the software engineering table (should be the first one after the header)
    table = tables[0]  # Assume first table is the software engineering table
    
    rows = table.find_all('tr')
    print(f"🔍 [GitHub] Found table with {len(rows)} rows")
    
    # Parse header to determine column indices
    header_row = rows[0] if rows else None
    date_posted_index = None
    
    if header_row:
        headers = [cell.get_text(strip=True).lower() for cell in header_row.find_all(['th', 'td'])]
        print(f"🔍 [GitHub] Table headers: {headers}")
        
        # Find the date posted column (can have various names)
        date_keywords = ['date posted', 'posted', 'date added', 'added', 'date']
        for idx, header in enumerate(headers):
            if any(keyword in header for keyword in date_keywords):
                date_posted_index = idx
                print(f"✅ [GitHub] Found date column at index {date_posted_index}: '{header}'")
                break
    
    # Skip header row
    for row in rows[1:]:  # Skip the header row
        if len(jobs) >= max_results:
            break
            
        cells = row.find_all('td')
        if len(cells) >= 4:  # Company, Role, Location, Application (minimum required)
            try:
                # Extract company name
                company_cell = cells[0]
                company_link = company_cell.find('a')
                company = company_link.get_text(strip=True) if company_link else company_cell.get_text(strip=True)
                
                # Extract role
                role = cells[1].get_text(strip=True)
                
                # Extract location
                location = cells[2].get_text(strip=True)
                
                # Extract application link
                app_cell = cells[3]
                app_links = app_cell.find_all('a')
                apply_link = None
                for link in app_links:
                    href = link.get('href', '')
                    if href and not href.startswith('https://simplify.jobs/p/'):
                        apply_link = href
                        break
                
                if not apply_link and app_links:
                    apply_link = app_links[0].get('href', '')
                
                # Extract date posted if available
                date_posted = None
                date_posted_raw = None
                days_since_posted = None
                
                if date_posted_index is not None and len(cells) > date_posted_index:
                    date_posted_raw = cells[date_posted_index].get_text(strip=True)
                    date_posted = date_posted_raw
                    
                    # Parse the date to extract days since posted for filtering
                    days_since_posted = parse_date_to_days(date_posted_raw)
                    
                    if days_since_posted is not None:
                        print(f"📅 [GitHub] {company} - {role}: Posted {days_since_posted} days ago ({date_posted_raw})")
                
                # Generate better description based on role and company
                detailed_description = generate_detailed_description(company, role, location)
                
                # Create job entry
                job = {
                    'company': company,
                    'title': role,
                    'location': location,
                    'apply_link': apply_link or '#',
                    'description': detailed_description,
                    'job_requirements': detailed_description,
                    'source': 'github_internships',
                    'required_skills': [],  # Will be populated by LLM extraction
                    'date_posted': date_posted,  # Raw date string
                    'date_posted_raw': date_posted_raw,  # Original date string from source
                    'days_since_posted': days_since_posted  # Normalized to days for filtering
                }
                
                # Extract skills using LLM from the detailed description
                try:
                    extracted_skills = extract_skills_from_job(job)
                    job['required_skills'] = extracted_skills if extracted_skills else ['Programming', 'Software Development']
                    date_info = f" (Posted: {date_posted})" if date_posted else ""
                    print(f"✅ [GitHub] Added job: {company} - {role}{date_info} (Skills: {job['required_skills'][:3]}...)")
                except Exception as e:
                    print(f"⚠️ [GitHub] Skill extraction failed for {company} - {role}: {e}")
                    job['required_skills'] = ['Programming', 'Software Development', 'Computer Science']
                    date_info = f" (Posted: {date_posted})" if date_posted else ""
                    print(f"✅ [GitHub] Added job: {company} - {role}{date_info} (Default skills)")
                
                jobs.append(job)
                
            except Exception as e:
                print(f"⚠️ [GitHub] Error parsing row: {e}")
                continue
    
    print(f"📋 [GitHub] Total jobs parsed: {len(jobs)}")
    return jobs

def generate_detailed_description(company, role, location):
    """
    Generate a detailed description based on company and role.
    """
    role_lower = role.lower()
    company_lower = company.lower()
    
    # Base description
    description = f"Software Engineering internship at {company}. Role: {role}. Location: {location}. "
    
    # Add company-specific context
    if "bytedance" in company_lower or "tiktok" in company_lower:
        description += "ByteDance is a global technology company known for TikTok and other popular apps. "
        if "frontend" in role_lower:
            description += "This role focuses on frontend development for e-commerce platforms and user-facing applications. "
        elif "test" in role_lower or "sdet" in role_lower:
            description += "This role focuses on quality assurance and automated testing for large-scale applications. "
        else:
            description += "This role involves developing software for global e-commerce and social media platforms. "
    
    elif "chase" in company_lower or "jpmorgan" in company_lower:
        description += "JPMorgan Chase is a leading global financial services firm. "
        description += "This role involves developing software solutions for banking, financial services, and fintech applications. "
        description += "You'll work on systems that handle millions of transactions and serve millions of customers. "
    
    elif "medtronic" in company_lower:
        description += "Medtronic is a global leader in medical technology. "
        description += "This role involves developing software for life-saving medical devices and healthcare systems. "
        description += "You'll work on software that directly impacts patient care and medical outcomes. "
    
    elif "kbr" in company_lower:
        description += "KBR is a global technology company specializing in defense, space, and technology solutions. "
        description += "This role involves working with satellite systems, remote sensing data, and space technology. "
        description += "You'll develop software for space missions and satellite ground systems. "
    
    elif "gdit" in company_lower:
        description += "GDIT is a technology company serving government and defense sectors. "
        description += "This role involves developing software solutions for government agencies and defense contractors. "
        description += "You'll work on systems that support national security and public sector technology. "
    
    elif "sel" in company_lower or "schweitzer" in company_lower:
        description += "SEL is a leader in power systems and electrical engineering technology. "
        description += "This role involves developing software for power grid management and electrical systems. "
        description += "You'll work on software that ensures reliable power delivery and grid stability. "
    
    elif "tencent" in company_lower:
        description += "Tencent is a global technology company known for gaming, social media, and cloud services. "
        if "cloud" in role_lower or "media" in role_lower:
            description += "This role focuses on cloud computing and media processing technologies. "
            description += "You'll work on cloud-based solutions for media streaming and processing. "
        else:
            description += "This role involves developing software for gaming, social media, and cloud platforms. "
    
    elif "allium" in company_lower:
        description += "Allium is a technology company focusing on AI and machine learning applications. "
        description += "This role involves developing AI-powered software solutions and machine learning models. "
        description += "You'll work on cutting-edge artificial intelligence and data science projects. "
    
    else:
        # Generic description based on role keywords
        if "frontend" in role_lower:
            description += "This role focuses on frontend development with modern web technologies. "
            description += "You'll build user interfaces and client-side applications using React, JavaScript, HTML, and CSS. "
        elif "backend" in role_lower or "api" in role_lower:
            description += "This role focuses on backend development and API development. "
            description += "You'll work with databases, server-side logic, and building scalable backend systems. "
        elif "full stack" in role_lower or "fullstack" in role_lower:
            description += "This role involves full stack development covering both frontend and backend technologies. "
            description += "You'll work on complete web applications from database to user interface. "
        elif "test" in role_lower or "qa" in role_lower:
            description += "This role focuses on software testing and quality assurance. "
            description += "You'll develop automated testing frameworks and ensure software quality. "
        elif "ai" in role_lower or "machine learning" in role_lower:
            description += "This role involves artificial intelligence and machine learning development. "
            description += "You'll work on AI models, data processing, and intelligent software systems. "
        elif "data" in role_lower:
            description += "This role focuses on data engineering and analysis. "
            description += "You'll work with data pipelines, databases, and data processing systems. "
        else:
            description += "This role involves general software engineering with programming, algorithms, and data structures. "
    
    description += "This position is suitable for students and recent graduates with strong programming skills and a passion for technology."
    
    return description

# Test the scraper
if __name__ == "__main__":
    jobs = scrape_github_internships("intern", max_results=10)
    print(f"\nFound {len(jobs)} jobs:")
    for i, job in enumerate(jobs):
        print(f"{i+1}. {job['title']} at {job['company']} - {job['location']}")
        print(f"   Skills: {job['required_skills']}") 
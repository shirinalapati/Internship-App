import pdfplumber
import re
import os
import io

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

    skills = re.findall(r"\b(Python|Java|React|Data Analysis|SQL|TensorFlow|C\+\+|JavaScript|Computer Science|Technical|Programming|Software|Engineering|Data|Machine Learning|AI|Cloud|Leadership|Communication|Teamwork|Problem Solving|Git|Rust|Less|Go|R\b|C#|TypeScript|PHP|Ruby|Scala|Matlab|Perl|Bash|Shell|PowerShell|Angular|Vue|Node\.js|Express|Django|Flask|Spring|Laravel|HTML|CSS|Sass|Bootstrap|Tailwind|jQuery|Ajax|REST API|GraphQL|WebSocket|HTTP|HTTPS|JSON|XML|MySQL|PostgreSQL|MongoDB|Redis|Elasticsearch|Cassandra|Data Science|Data Engineering|ETL|Data Pipeline|Deep Learning|Artificial Intelligence|Neural Networks|PyTorch|Scikit-learn|Pandas|Numpy|Matplotlib|Seaborn|Computer Vision|NLP|Natural Language Processing|Recommendation Systems|AWS|Azure|GCP|Google Cloud|Docker|Kubernetes|Jenkins|GitLab|GitHub|CI/CD|Terraform|Ansible|Prometheus|Grafana|Software Development|Coding|Algorithm|Data Structures|Object-oriented|Functional Programming|Design Patterns|Microservices|API Development|Backend|Frontend|Full Stack|Fullstack|Mobile Development|iOS|Android|React Native|Flutter|Xamarin|Testing|Unit Testing|Integration Testing|QA|Quality Assurance|Test Automation|Selenium|JUnit|PyTest|Jest|Cypress|Maven|Gradle|NPM|Yarn|IntelliJ|VSCode|Eclipse|Vim|Emacs|Linux|Unix|macOS|E-commerce|Fintech|Healthcare|Cybersecurity|Blockchain|IoT|Embedded Systems|FPGA|Hardware|Robotics|Autonomous Vehicles|Agile|Scrum|Project Management|Mentoring|Collaboration|Presentation|Student|Intern|Internship|Co-op|Research|Thesis|Academic|University|College|Bachelor|Master|PhD|Graduate|Undergraduate|Mathematics|Statistics|Physics)\b", text, re.IGNORECASE)
    return list(set([s.title() for s in skills]))


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

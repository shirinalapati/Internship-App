import pdfplumber
import re
import os

def parse_resume(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    if ext in [".png", ".jpg", ".jpeg"]:
        from PIL import Image
        import pytesseract
        image = Image.open(filepath)
        text = pytesseract.image_to_string(image)
    else:
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
        except Exception:
            text = ""
        # If no text was extracted, try OCR on PDF
        if not text.strip():
            from pdf2image import convert_from_path
            import pytesseract
            images = convert_from_path(filepath)
            for image in images:
                text += pytesseract.image_to_string(image)

    skills = re.findall(r"\b(Python|Java|React|Data Analysis|SQL|TensorFlow|C\+\+|JavaScript|Computer Science|Technical|Programming|Software|Engineering|Data|Machine Learning|AI|Cloud|Leadership|Communication|Teamwork|Problem Solving|Git|Rust|Less|Go|R\b|C#|TypeScript|PHP|Ruby|Scala|Matlab|Perl|Bash|Shell|PowerShell|Angular|Vue|Node\.js|Express|Django|Flask|Spring|Laravel|HTML|CSS|Sass|Bootstrap|Tailwind|jQuery|Ajax|REST API|GraphQL|WebSocket|HTTP|HTTPS|JSON|XML|MySQL|PostgreSQL|MongoDB|Redis|Elasticsearch|Cassandra|Data Science|Data Engineering|ETL|Data Pipeline|Deep Learning|Artificial Intelligence|Neural Networks|PyTorch|Scikit-learn|Pandas|Numpy|Matplotlib|Seaborn|Computer Vision|NLP|Natural Language Processing|Recommendation Systems|AWS|Azure|GCP|Google Cloud|Docker|Kubernetes|Jenkins|GitLab|GitHub|CI/CD|Terraform|Ansible|Prometheus|Grafana|Software Development|Coding|Algorithm|Data Structures|Object-oriented|Functional Programming|Design Patterns|Microservices|API Development|Backend|Frontend|Full Stack|Fullstack|Mobile Development|iOS|Android|React Native|Flutter|Xamarin|Testing|Unit Testing|Integration Testing|QA|Quality Assurance|Test Automation|Selenium|JUnit|PyTest|Jest|Cypress|Maven|Gradle|NPM|Yarn|IntelliJ|VSCode|Eclipse|Vim|Emacs|Linux|Unix|macOS|E-commerce|Fintech|Healthcare|Cybersecurity|Blockchain|IoT|Embedded Systems|FPGA|Hardware|Robotics|Autonomous Vehicles|Agile|Scrum|Project Management|Mentoring|Collaboration|Presentation|Student|Intern|Internship|Co-op|Research|Thesis|Academic|University|College|Bachelor|Master|PhD|Graduate|Undergraduate|Mathematics|Statistics|Physics)\b", text, re.IGNORECASE)
    return {
        "skills": list(set([s.title() for s in skills])),
        "raw_text": text
    }

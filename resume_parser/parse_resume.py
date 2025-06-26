import PyPDF2
import re

def parse_resume(filepath):
    text = ""
    with open(filepath, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()

    skills = re.findall(r"(Python|Java|React|Data Analysis|SQL|TensorFlow)", text, re.IGNORECASE)
    return {
        "skills": list(set([s.title() for s in skills])),
        "raw_text": text
    }

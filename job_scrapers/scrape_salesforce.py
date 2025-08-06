from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import re

def get_short_description(text, max_sentences=3, max_chars=300):
    sentences = re.split(r'(?<=[.!?]) +', text)
    short_desc = ''
    count = 0
    for s in sentences:
        if not s.strip():
            continue
        if len(short_desc) + len(s) > max_chars or count >= max_sentences:
            break
        short_desc += s + ' '
        count += 1
    return short_desc.strip()

def scrape_salesforce_jobs(keyword="intern", max_results=10):
    opts = Options()
    opts.headless = True
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1400, 1000)
    # Always use the US internships URL
    driver.get("https://careers.salesforce.com/en/jobs/?search=&country=United+States+of+America&jobtype=Intern&pagesize=20#results")

    wait = WebDriverWait(driver, 20)

    # Wait for initial job listings to appear
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.card.card-job")))
    except:
        print("❌ No job listings found.")
        driver.quit()
        return []

    # Scroll to load more jobs
    for _ in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    job_cards = soup.select("div.card.card-job")

    filtered_interns = 0
    filtered_us = 0
    jobs = []
    
    def extract_skills_from_text(text):
        # Expanded list of skills to look for
        skill_keywords = [
            "Python", "Java", "SQL", "React", "TensorFlow", "Data Analysis", "C++", "JavaScript",
            "Computer Science", "Technical", "Programming", "Software", "Engineering", "Data", "Machine Learning", "AI", "Cloud", "Leadership", "Communication", "Teamwork", "Problem Solving"
        ]
        found_skills = []
        for skill in skill_keywords:
            if skill.lower() in text.lower():
                found_skills.append(skill)
        return found_skills

    us_terms = [
        "united states", "usa", "u.s.", "us", "california", "new york", "texas", "washington", "illinois", "florida", "georgia", "virginia", "pennsylvania", "ohio", "michigan", "arizona", "massachusetts", "north carolina", "new jersey", "colorado", "tennessee", "indiana", "missouri", "maryland", "wisconsin", "minnesota", "south carolina", "alabama", "louisiana", "kentucky", "oregon", "oklahoma", "connecticut", "iowa", "mississippi", "arkansas", "utah", "nevada", "kansas", "new mexico", "nebraska", "west virginia", "idaho", "hawaii", "maine", "new hampshire", "montana", "rhode island", "delaware", "south dakota", "north dakota", "alaska", "vermont", "wyoming", "district of columbia", "dc"
    ]
    for card in job_cards:
        title_elem = card.select_one("h3.card-title")
        link_elem = card.select_one("a.stretched-link")
        location_elem = card.select_one("ul.list-inline.job-meta li")

        if title_elem and link_elem:
            title_text = title_elem.text.strip()
            job_link = link_elem["href"]
            if not job_link.startswith("http"):
                job_link = "https://careers.salesforce.com" + job_link
            location_text = location_elem.text.strip() if location_elem else "N/A"

            # Skip if no title found
            if not title_text or title_text.lower() == "internship":
                continue
            
            # Filter for US locations only
            if not any(us_term in location_text.lower() for us_term in us_terms):
                filtered_us += 1
                continue
            
            # Get description from the card text
            description = card.get_text(separator=" ", strip=True)
            description = get_short_description(description)
            
            jobs.append({
                "title": title_text,
                "company": "Salesforce",
                "location": location_text,
                "description": description,
                "required_skills": [],
                "apply_link": job_link,
                "deadline": None
            })
            
            if len(jobs) >= max_results:
                break
    
    return jobs

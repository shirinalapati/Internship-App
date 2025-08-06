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

GOOGLE_INTERNSHIPS_URL = "https://www.google.com/about/careers/applications/jobs/results/?distance=50&employment_type=INTERN&degree=BACHELORS&location=United%20States&company=YouTube&company=Fitbit&company=Google"

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

def get_detailed_job_description(driver, job_url):
    """Get detailed job description by visiting the job page."""
    try:
        driver.get(job_url)
        time.sleep(2)
        
        # Wait for job details to load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='job-description']")))
        
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for job description content
        description_elem = soup.select_one("div[data-testid='job-description']")
        if description_elem:
            return description_elem.get_text(separator=" ", strip=True)
        
        # Fallback: look for any content with job details
        content_elems = soup.select("div[class*='description'], div[class*='content'], div[class*='details']")
        if content_elems:
            return content_elems[0].get_text(separator=" ", strip=True)
            
    except Exception as e:
        print(f"⚠️ Could not get detailed description for {job_url}: {e}")
    
    return ""

def scrape_google_jobs(keyword="intern", max_results=10):
    opts = Options()
    opts.headless = True
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1400, 1000)
    driver.get(GOOGLE_INTERNSHIPS_URL)

    wait = WebDriverWait(driver, 20)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.ObfsIf-oKdM2c")))
    except:
        print("❌ No Google job listings found.")
        driver.quit()
        return []

    time.sleep(3)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")
    job_cards = soup.select("div.ObfsIf-oKdM2c")
    jobs = []
    us_terms = [
        "united states", "usa", "u.s.", "us", "california", "new york", "texas", "washington", "illinois", "florida", "georgia", "virginia", "pennsylvania", "ohio", "michigan", "arizona", "massachusetts", "north carolina", "new jersey", "colorado", "tennessee", "indiana", "missouri", "maryland", "wisconsin", "minnesota", "south carolina", "alabama", "louisiana", "kentucky", "oregon", "oklahoma", "connecticut", "iowa", "mississippi", "arkansas", "utah", "nevada", "kansas", "new mexico", "nebraska", "west virginia", "idaho", "hawaii", "maine", "new hampshire", "montana", "rhode island", "delaware", "south dakota", "north dakota", "alaska", "vermont", "wyoming", "district of columbia", "dc"
    ]
    filtered_interns = 0
    filtered_us = 0
    for card in job_cards:
        title_elem = card.select_one("h3.QJPWVe")
        company = "Google"
        # Extract company and location
        company_loc_elem = card.find_next_sibling("div", class_="EAcu5e Gx4ovb")
        location = "N/A"
        if company_loc_elem:
            loc_p = company_loc_elem.select_one("p.l103df")
            if loc_p:
                location = loc_p.get_text(strip=True)
        # Find the 'Learn more' link (a.WpHeLc)
        learn_more_a = card.find_next("a", class_="WpHeLc")
        learn_more_link = None
        if learn_more_a and learn_more_a.get("href"):
            learn_more_link = learn_more_a["href"]
            if not learn_more_link.startswith("http"):
                learn_more_link = "https://www.google.com/about/careers/applications/" + learn_more_link.lstrip("/")
        # Only add jobs with a real title (not empty or 'Internship')
        title = title_elem.text.strip() if title_elem else ""
        # Skip if no title found
        if not title or title.lower() == "internship":
            continue
            
        # Filter for US locations only
        if not any(us_term in location.lower() for us_term in us_terms):
            filtered_us += 1
            continue
        
        # Get detailed description by visiting the job page
        detailed_description = ""
        if learn_more_link:
            detailed_description = get_detailed_job_description(driver, learn_more_link)
        
        # Fallback to card description if detailed description is empty
        if not detailed_description:
            description = card.get_text(separator=" ", strip=True)
            description = get_short_description(description)
        else:
            description = get_short_description(detailed_description)
        
        jobs.append({
            "title": title,
            "company": "Google",
            "location": location,
            "description": description,
            "required_skills": [],
            "apply_link": learn_more_link if learn_more_link else GOOGLE_INTERNSHIPS_URL,
            "deadline": None
        })
        
        if len(jobs) >= max_results:
            break
    
    driver.quit()
    print(f"✅ [Google] Found {len(jobs)} internship opportunities")
    return jobs 
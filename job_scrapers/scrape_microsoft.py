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

MICROSOFT_INTERNSHIPS_URL = "https://jobs.careers.microsoft.com/global/en/search?lc=United%20States&et=Internship&l=en_us&pg=1&pgSz=20&o=Relevance&flt=true"

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

def scrape_microsoft_jobs(keyword="intern", max_results=10):
    opts = Options()
    opts.headless = True
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1400, 1000)
    driver.get(MICROSOFT_INTERNSHIPS_URL)

    wait = WebDriverWait(driver, 20)
    
    # Wait for page to load and scroll to load more content
    time.sleep(5)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    
    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    
    # Try multiple approaches to find job listings
    job_cards = []
    
    # Approach 1: Look for job cards with role="button" and tabindex="0"
    possible_selectors = [
        'div[role="button"][tabindex="0"]',  # Microsoft job card selector
        "section.jobs-list-item",
        "div[class*='job']",
        "div[class*='card']",
        "div[class*='listing']",
        "div[class*='result']",
        "article",
        "section",
        "div[data-testid*='job']",
        "div[data-testid*='card']"
    ]
    
    for selector in possible_selectors:
        elements = soup.select(selector)
        if elements:
            job_cards = elements
            break
    
    if not job_cards:
        return []

    filtered_us = 0
    jobs = []
    
    us_terms = ["united states", "usa", "us", "united states of america", "california", "new york", "texas", "washington", "illinois", "florida", "georgia", "virginia", "pennsylvania", "ohio", "michigan", "arizona", "massachusetts", "north carolina", "new jersey", "colorado", "tennessee", "indiana", "missouri", "maryland", "wisconsin", "minnesota", "south carolina", "alabama", "louisiana", "kentucky", "oregon", "oklahoma", "connecticut", "iowa", "mississippi", "arkansas", "utah", "nevada", "kansas", "new mexico", "nebraska", "west virginia", "idaho", "hawaii", "maine", "new hampshire", "montana", "rhode island", "delaware", "south dakota", "north dakota", "alaska", "vermont", "wyoming", "district of columbia", "dc"]
    
    for card in job_cards:
        # Try to extract job information from the card
        title = ""
        location = "N/A"
        description = ""
        apply_link = MICROSOFT_INTERNSHIPS_URL
        
        # Look for title in h2 elements (Microsoft job titles are in h2)
        title_elem = card.select_one("h2")
        if title_elem:
            title = title_elem.get_text(strip=True)
        
        # Look for location in the card text
        card_text = card.get_text(strip=True)
        
        # Microsoft locations are often mentioned in the job title or description
        # Look for common US location patterns
        location_patterns = [
            "Redmond", "Seattle", "Bellevue", "Washington", "WA",
            "Mountain View", "Sunnyvale", "California", "CA",
            "New York", "NY", "Texas", "TX", "Florida", "FL"
        ]
        
        for pattern in location_patterns:
            if pattern.lower() in card_text.lower():
                location = pattern
                break
        
        # Look for links - Microsoft job cards might have "See details" buttons
        link_elem = card.select_one("button")
        if link_elem and "see details" in link_elem.get_text(strip=True).lower():
            # The job card itself might be clickable
            apply_link = MICROSOFT_INTERNSHIPS_URL
        
        # Skip if no title found
        if not title or title.lower() == "internship":
            continue
            
        # Filter for US locations only
        if not any(us_term in location.lower() for us_term in us_terms):
            filtered_us += 1
            continue
        
        # Get description from the card text
        description = card.get_text(separator=" ", strip=True)
        description = get_short_description(description)
        
        jobs.append({
            "title": title,
            "company": "Microsoft",
            "location": location,
            "description": description,
            "required_skills": [],
            "apply_link": apply_link,
            "deadline": None
        })
        
        if len(jobs) >= max_results:
            break
    
    return jobs 
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

META_INTERNSHIPS_URL = "https://www.metacareers.com/jobs?teams[0]=University%20Grad%20-%20Business&teams[1]=University%20Grad%20-%20Engineering%2C%20Tech%20%26%20Design&teams[2]=University%20Grad%20-%20PhD%20%26%20Postdoc&roles[0]=Internship"

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

def scrape_meta_jobs(keyword="intern", max_results=10):
    opts = Options()
    opts.headless = True
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1400, 1000)
    driver.get(META_INTERNSHIPS_URL)

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
    
    # Approach 1: Look for any elements that might contain job information
    possible_selectors = [
        "div.x9f619.x1p5oq8j.xyri2b.xwxc41k.xf7qf19.xt7dq6l.x7a106z.x78zum5.xdt5ytf.x1ilxx4r.x1gpa8tf.xfuitmc.x18ekk8g",  # Working selector from HTML analysis
        "div[data-testid*='card']",
        "div[data-testid*='job']",
        "div[data-testid*='result']",
        "div[class*='job']",
        "div[class*='card']",
        "div[class*='listing']",
        "div[class*='result']",
        "article",
        "section"
    ]
    
    for selector in possible_selectors:
        elements = soup.select(selector)
        if elements:
            job_cards = elements
            break
    
    if not job_cards:
        # Let's see what elements exist
        all_divs = soup.find_all('div', class_=True)
        return []

    filtered_us = 0
    jobs = []
    
    us_terms = [
        "united states", "usa", "u.s.", "us", "california", "new york", "texas", "washington", "illinois", "florida", "georgia", "virginia", "pennsylvania", "ohio", "michigan", "arizona", "massachusetts", "north carolina", "new jersey", "colorado", "tennessee", "indiana", "missouri", "maryland", "wisconsin", "minnesota", "south carolina", "alabama", "louisiana", "kentucky", "oregon", "oklahoma", "connecticut", "iowa", "mississippi", "arkansas", "utah", "nevada", "kansas", "new mexico", "nebraska", "west virginia", "idaho", "hawaii", "maine", "new hampshire", "montana", "rhode island", "delaware", "south dakota", "north dakota", "alaska", "vermont", "wyoming", "district of columbia", "dc", "wa", "ca", "ny", "tx", "fl", "ga", "va", "pa", "oh", "mi", "az", "ma", "nc", "nj", "co", "tn", "in", "mo", "md", "wi", "mn", "sc", "al", "la", "ky", "or", "ok", "ct", "ia", "ms", "ar", "ut", "nv", "ks", "nm", "ne", "wv", "id", "hi", "me", "nh", "mt", "ri", "de", "sd", "nd", "ak", "vt", "wy"
    ]
    
    for card in job_cards:
        # Try to extract job information from the card
        title = ""
        location = "N/A"
        description = ""
        apply_link = META_INTERNSHIPS_URL
        
        # Look for title in various possible elements
        title_selectors = [
            "div.x10lme4x.x26uert.xngnso2.x117nqv4.x1mnlqng.x1e096f4",  # Meta job title selector
            "h1", "h2", "h3", "h4", "a", "span", "div"
        ]
        for selector in title_selectors:
            title_elem = card.select_one(selector)
            if title_elem and title_elem.get_text(strip=True):
                potential_title = title_elem.get_text(strip=True)
                if len(potential_title) > 5 and len(potential_title) < 100:  # Reasonable title length
                    title = potential_title
                    break
        
        # Look for location
        location_selectors = [
            "span.x26uert.x8xxdc5.x1jchvi3",  # Meta location selector
            "span", "div", "p"
        ]
        for selector in location_selectors:
            loc_elem = card.select_one(selector)
            if loc_elem:
                loc_text = loc_elem.get_text(strip=True)
                if any(us_term in loc_text.lower() for us_term in us_terms):
                    location = loc_text
                    break
        
        # Look for links - Meta job cards are wrapped in anchor tags
        link_elem = card.find_parent("a")
        if link_elem and link_elem.get("href"):
            apply_link = link_elem["href"]
            if not apply_link.startswith("http"):
                apply_link = "https://www.metacareers.com" + apply_link
        
        # Skip if no title found
        if not title or title.lower() == "internship":
            continue
            
        # Filter for US locations only
        if not any(us_term in location.lower() for us_term in us_terms):
            filtered_us += 1
            continue
        else:
            matching_term = next(us_term for us_term in us_terms if us_term in location.lower())
        
        # Get description from the card text
        description = card.get_text(separator=" ", strip=True)
        description = get_short_description(description)
        
        jobs.append({
            "title": title,
            "company": "Meta",
            "location": location,
            "description": description,
            "required_skills": [],
            "apply_link": apply_link,
            "deadline": None
        })
        
        if len(jobs) >= max_results:
            break
    
    return jobs 
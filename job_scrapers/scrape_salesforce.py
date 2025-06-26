from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

def scrape_salesforce_jobs(keyword="intern", location=None, max_results=10):
    opts = Options()
    opts.headless = False
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1400, 1000)
    driver.get("https://careers.salesforce.com/en/jobs/")

    wait = WebDriverWait(driver, 20)

    # Wait for initial job listings to appear
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.jobs-list-item")))
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
    job_cards = soup.select("li.jobs-list-item")

    jobs = []
    for card in job_cards:
        title = card.select_one("span.title")
        location = card.select_one("span.location")
        link = card.find("a", href=True)

        if title and location and link:
            title_text = title.text.strip()
            if "intern" not in title_text.lower():
                continue  # only collect internships

            jobs.append({
                "title": title_text,
                "company": "Salesforce",
                "location": location.text.strip(),
                "description": "N/A",
                "required_skills": [],
                "apply_link": "https://careers.salesforce.com" + link["href"],
                "deadline": None
            })

        if len(jobs) >= max_results:
            break

    return jobs

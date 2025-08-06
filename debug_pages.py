#!/usr/bin/env python3

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def save_page_html(url, filename):
    opts = Options()
    opts.headless = True
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1400, 1000)
    
    print(f"Loading {url}...")
    driver.get(url)
    
    # Wait for page to load
    time.sleep(5)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    
    html = driver.page_source
    driver.quit()
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Saved HTML to {filename}")
    print(f"Page title: {driver.title if driver.title else 'No title'}")

if __name__ == "__main__":
    # Meta internships URL
    meta_url = "https://www.metacareers.com/jobs?teams[0]=University%20Grad%20-%20Business&teams[1]=University%20Grad%20-%20Engineering%2C%20Tech%20%26%20Design&teams[2]=University%20Grad%20-%20PhD%20%26%20Postdoc&roles[0]=Internship"
    save_page_html(meta_url, "meta_page.html")
    
    # Microsoft internships URL
    microsoft_url = "https://jobs.careers.microsoft.com/global/en/search?lc=United%20States&et=Internship&l=en_us&pg=1&pgSz=20&o=Relevance&flt=true"
    save_page_html(microsoft_url, "microsoft_page.html") 
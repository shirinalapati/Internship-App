#!/usr/bin/env python3

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def save_microsoft_html():
    opts = Options()
    opts.headless = True
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1400, 1000)
    
    url = "https://jobs.careers.microsoft.com/global/en/search?lc=United%20States&et=Internship&l=en_us&pg=1&pgSz=20&o=Relevance&flt=true"
    print(f"Loading {url}...")
    driver.get(url)
    
    # Wait for page to load
    time.sleep(5)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    
    html = driver.page_source
    title = driver.title
    driver.quit()
    
    with open("microsoft_page.html", 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Saved HTML to microsoft_page.html")
    print(f"Page title: {title}")

if __name__ == "__main__":
    save_microsoft_html() 
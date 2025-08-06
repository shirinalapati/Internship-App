from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

url = "https://www.google.com/about/careers/applications/jobs/results/?distance=50&employment_type=INTERN&degree=BACHELORS&location=United%20States&company=YouTube&company=Fitbit&company=Google"

opts = Options()
opts.headless = False
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=opts)
driver.set_window_size(1400, 1000)
driver.get(url)

print("🔍 Loading Google jobs page...")
time.sleep(8)  # Wait for page to load

# Scroll to load more content
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(3)

# Get page source
html = driver.page_source

# Save HTML to file for inspection
with open("google_page.html", "w", encoding="utf-8") as f:
    f.write(html)

print("✅ Saved page HTML to google_page.html")
driver.quit() 
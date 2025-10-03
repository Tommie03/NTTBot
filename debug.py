from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=chrome_options)

try:
    driver.get("https://nttb.toernooi.nl")
    time.sleep(3)
    
    # Accept cookies
    try:
        accept = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'accept')]"))
        )
        accept.click()
        time.sleep(2)
    except:
        pass
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # Find tournaments
    tournaments = [elem for elem in soup.find_all('li', class_='list__item') 
                   if elem.find('h4', class_='media__title') 
                   and not elem.find('input', type='checkbox')]
    
    if tournaments:
        print("="*80)
        print("FIRST TOURNAMENT HTML:")
        print("="*80)
        print(tournaments[0].prettify())
        
        print("\n" + "="*80)
        print("ALL CLASSES USED:")
        print("="*80)
        for tag in tournaments[0].find_all(True):
            if tag.get('class'):
                print(f"{tag.name}: {', '.join(tag.get('class'))}")
    else:
        print("No tournaments found")
        
finally:
    driver.quit()
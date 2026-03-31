import time as t
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pandas as pd
import requests
import os
import json
import hashlib
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

TALENT_URL_BASE = os.getenv('TALENT_BASE_URL')

def setup_driver_options():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.92 Safari/537.36")
    return options

def get_element_text(element, selector):
    try:
        return element.find_element(By.CSS_SELECTOR, selector).text or '-'
    except:
        return '-'

def get_element_attribute(element, selector, attribute):
    try:
        return element.find_element(By.CSS_SELECTOR, selector).get_attribute(attribute) or '-'
    except:
        return '-'

def get_ticket_info(talent_id, talent_name):
    url = f"{TALENT_URL_BASE}{talent_id}"
    print(f"アクセス先URL: {url}")  # 追加
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=setup_driver_options())
    driver.get(url)

    # 非表示要素の全表示
    driver.execute_script("""
        document.querySelectorAll('[id^="feedItem2-"]').forEach(el => {
            el.style.display = 'grid';
        });
    """)

    events = []
    for event in driver.find_elements(By.CSS_SELECTOR, '#feed_ticket_info2 .feed-item-container'):
        title = get_element_text(event, '.feed-ticket-title')
        date = get_element_text(event, '.opt-feed-ft-dateside p:first-child')
        time_ = get_element_text(event, '.opt-feed-ft-dateside p:last-child')
        members = get_element_text(event, '.opt-feed-ft-element-member').replace('\n', '|')
        venue = get_element_text(event, '.opt-feed-ft-element-venue')
        origin_image = get_element_attribute(event, '.feed-item-img', 'src')
        link = get_element_attribute(event, '.feed-item-link', 'href')

        # 画像のローカル保存等はここでは行わず、「元画像URL」をOriginImageで記録
        events.append({
            'TalentName': talent_name,
            'TalentID': str(talent_id),
            'EventTitle': title,
            'EventDate': date,
            'EventStartTime': time_,
            'EventMembers': members,
            'TheaterVenue': venue,
            'OriginImage': origin_image,
            'AppImage': "",      # 画像保存は次工程に委譲する前提
            'TicketLink': link
        })

    driver.quit()
    return events

def main():
    # talents.jsonの読み込み
    with open('docs/talents.json', encoding='utf-8') as f:
        talents = json.load(f)

    all_events = []
    for talent in talents:
        print(f"Scraping {talent['name']} (ID: {talent['id']}) ...")
        all_events.extend(get_ticket_info(talent['id'], talent['name']))
    df = pd.DataFrame(all_events)

    # CSVに一時保存
    df.to_csv('temp_talent_events.csv', index=False, encoding='utf-8-sig')
    print("Scraping & Export完了: temp_talent_events.csv")

if __name__ == "__main__":
    main()

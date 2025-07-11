import time as t
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pandas as pd
import os
import json
from webdriver_manager.chrome import ChromeDriverManager

# 環境変数で設定
talent_url = os.getenv('TALENT_BASE_URL')

# 名前取得
talents = []
with open('talents.json', encoding='utf-8') as f:
    talents = json.load(f)

def get_ticket_info(talent_id, talent_name):
    url = f"{talent_url}{talent_id}"
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
        image = get_element_attribute(event, '.feed-item-img', 'src')
        link = get_element_attribute(event, '.feed-item-link', 'href')

        events.append({
            'TalentName': talent_name,
            'TalentID': talent_id,
            'EventTitle': title,
            'EventDate': date,
            'EventStartTime': time_,
            'EventMembers': members,
            'TheaterVenue': venue,
            'Image': image,
            'TicketLink': link
        })

    driver.quit()
    return events

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

if __name__ == "__main__":
    all_events = []
    for talent in talents:
        all_events.extend(get_ticket_info(talent['id'], talent['name']))

    df = pd.DataFrame(all_events)
    df.to_csv('talent_tickets.csv', index=False, encoding='utf-8-sig')
    print("done.")

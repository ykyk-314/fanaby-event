import time as t
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

# 環境変数で設定
talent_url = os.getenv('TALENT_BASE_URL')

# 名前取得
with open('docs/talents.json', encoding='utf-8') as f:
    talents = json.load(f)

def download_event_image(origin_url, img_dir, file_name):
    """
    origin_url: オリジナル画像URL
    img_dir:    保存先ディレクトリ（例: docs/img/flier/7295）
    file_name:  ファイル名のみ（例: 2024-07-21_MyEvent_abcdef12.jpg）
    """
    if not origin_url or origin_url == '-':
        return False
    os.makedirs(img_dir, exist_ok=True)
    save_path = os.path.join(img_dir, file_name)
    # 既に画像ファイルが存在すればスキップ
    if os.path.exists(save_path):
        return True
    try:
        r = requests.get(origin_url, timeout=10)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
                print(f"Image save_path: {origin_url}: {save_path}")
            return True
        else:
            print(f"Image download failed: {origin_url}")
            return False
    except Exception as e:
        print(f"Image download error: {e}")
        return False

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
        origin_image = get_element_attribute(event, '.feed-item-img', 'src')
        link = get_element_attribute(event, '.feed-item-link', 'href')

        # ファイル名生成（画像URLのハッシュ＋タイトル＋日付などで一意性を担保）
        safe_title = "".join([c for c in title if c.isalnum() or c in " _-"]).rstrip()
        safe_date = date.replace('/', '-').replace(' ', '').replace(':','')
        file_hash = hashlib.md5(origin_image.encode()).hexdigest()[:8] if origin_image else "noimg"
        file_name = f"{safe_date}_{safe_title}_{file_hash}.jpg"
        img_dir = f"docs/img/flier/{talent_id}"
        app_image = f"/img/flier/{talent_id}/{file_name}"

        # 画像ダウンロード（存在しなければダウンロード、すでにあればスキップ）
        download_event_image(origin_image, img_dir, file_name)

        events.append({
            'TalentName': talent_name,
            'TalentID': str(talent_id),
            'EventTitle': title,
            'EventDate': date,
            'EventStartTime': time_,
            'EventMembers': members,
            'TheaterVenue': venue,
            'OriginImage': origin_image,
            'AppImage': app_image,
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

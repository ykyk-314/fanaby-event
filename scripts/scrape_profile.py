"""
芸人プロフィールページから公演情報を取得するスクリプト。
取得結果は profile_events.json として一時保存する。
"""

import json
import os
import random
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
OUTPUT_PATH = BASE_DIR / "data" / "profile_events.json"
PROFILE_BASE_URL = "https://profile.yoshimoto.co.jp/talent/detail?id="


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
    # Selenium 4.6+ の selenium-manager が ChromeDriver を自動管理する
    return webdriver.Chrome(options=options)


def resolve_year(month: int, day: int, today: date) -> int:
    """
    月日から年を推定する。
    プロフィールページには未来のチケット情報のみ掲載されるため、
    今日以降の最近の日付として年を確定する。
    """
    year = today.year
    candidate = date(year, month, day)
    if candidate < today:
        candidate = date(year + 1, month, day)
    return candidate.year


def parse_date(raw: str, today: date) -> str | None:
    """
    "4/19" → "2026-04-19" 形式に変換する。
    """
    m = re.match(r"(\d{1,2})/(\d{1,2})", raw.strip())
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        year = resolve_year(month, day, today)
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_time(raw: str) -> str | None:
    """
    "20:30" 形式の時刻文字列を正規化して返す。
    """
    m = re.search(r"(\d{1,2}:\d{2})", raw.strip())
    return m.group(1) if m else None


def scrape_talent(driver: webdriver.Chrome, talent: dict, today: date) -> list[dict]:
    url = PROFILE_BASE_URL + talent["id"]
    print(f"  取得中: {talent['name']} ({url})")
    driver.get(url)

    # JS描画待機：feed_ticket_info2 が現れるまで最大15秒
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#feed_ticket_info2"))
        )
    except Exception:
        print(f"  警告: #feed_ticket_info2 が見つかりませんでした ({talent['name']})")
        return []

    # 非表示になっているfeedItemを強制表示
    driver.execute_script(
        "document.querySelectorAll('[id^=\"feedItem2-\"]').forEach(el => {"
        "  el.style.display = 'grid';"
        "});"
    )
    time.sleep(1)

    items = driver.find_elements(By.CSS_SELECTOR, "#feed_ticket_info2 .feed-item-container")
    print(f"  {len(items)} 件取得")

    events = []
    for item in items:
        try:
            event = _parse_item(item, talent, today)
            if event:
                events.append(event)
        except Exception as e:
            print(f"  警告: アイテムのパース失敗: {e}")
    return events


def _parse_item(item, talent: dict, today: date) -> dict | None:
    # 日付・時刻
    dateside = item.find_elements(By.CSS_SELECTOR, ".opt-feed-ft-dateside p")
    if len(dateside) < 2:
        return None
    raw_date = dateside[0].text.strip()
    raw_time = dateside[1].text.strip()

    event_date = parse_date(raw_date, today)
    if not event_date:
        return None
    start_time = parse_time(raw_time)

    # タイトル
    title_el = item.find_elements(By.CSS_SELECTOR, ".feed-ticket-title")
    title = title_el[0].text.strip() if title_el else ""
    if not title:
        return None

    # 出演者
    member_el = item.find_elements(By.CSS_SELECTOR, ".opt-feed-ft-element-member")
    members_raw = member_el[0].get_attribute("innerHTML").strip() if member_el else ""
    members = _parse_members(members_raw)

    # 所在地（吉本所有劇場のみ）
    place_el = item.find_elements(By.CSS_SELECTOR, ".opt-feed-ft-element-place")
    place = place_el[0].text.strip() if place_el else None

    # 会場名
    venue_el = item.find_elements(By.CSS_SELECTOR, ".opt-feed-ft-element-venue")
    venue = venue_el[0].text.strip() if venue_el else None

    # フライヤー画像
    img_el = item.find_elements(By.CSS_SELECTOR, ".feed-item-img")
    image_url = img_el[0].get_attribute("src") if img_el else None
    if image_url and image_url.startswith("data:"):
        image_url = None

    # チケットURL
    link_el = item.find_elements(By.CSS_SELECTOR, "a.feed-item-link")
    ticket_url = link_el[0].get_attribute("href") if link_el else None

    return {
        "talent_id": talent["id"],
        "talent_name": talent["name"],
        "title": title,
        "date": event_date,
        "start_time": start_time,
        "members": members,
        "place": place,
        "venue": venue,
        "image_url": image_url,
        "ticket_url": ticket_url,
        "source": "profile",
    }


def _parse_members(html: str) -> list[str]:
    """
    出演者HTMLから名前リストを抽出する。
    <br> / 「、」/ 「／」/ 「・」で分割し、ゲスト等のプレフィックスも除去する。
    """
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"ゲスト[:：]", "", text)
    parts = re.split(r"[、／\n・,，]", text)
    return [p.strip() for p in parts if p.strip()]


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    talents = config["talents"]
    today = date.today()

    driver = build_driver()
    all_events: list[dict] = []

    try:
        for i, talent in enumerate(talents):
            events = scrape_talent(driver, talent, today)
            all_events.extend(events)
            if i < len(talents) - 1:
                wait = random.uniform(5, 10)
                print(f"  待機 {wait:.1f}秒...")
                time.sleep(wait)
    finally:
        driver.quit()

    OUTPUT_PATH.write_text(
        json.dumps(all_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nプロフィール取得完了: {len(all_events)} 件 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

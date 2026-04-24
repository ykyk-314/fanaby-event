"""
劇場スケジュールページから公演情報を取得するスクリプト。
登録芸人が出演する公演のみ抽出し、theater_events.json として一時保存する。
"""

import json
import random
import re
import time
from datetime import date
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
OUTPUT_PATH = BASE_DIR / "data" / "theater_events.json"

PROFILE_BASE_URL = "https://profile.yoshimoto.co.jp/talent/detail?id="
# 何ヶ月先まで取得するか（今月 + FETCH_MONTHS 先まで）
FETCH_MONTHS = 2


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-cache")
    options.add_argument("--disk-cache-size=0")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
    # Selenium 4.6+ の selenium-manager が ChromeDriver を自動管理する
    return webdriver.Chrome(options=options)


def get_target_months(today: date) -> list[tuple[int, int]]:
    """今月〜FETCH_MONTHS先までの (year, month) リストを返す。"""
    months = []
    y, m = today.year, today.month
    for _ in range(FETCH_MONTHS + 1):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def click_month_tab(driver: webdriver.Chrome, year: int, month: int) -> bool:
    """指定年月のタブをクリックする。存在しない場合はFalseを返す。"""
    tab_id = f"month{year}-{month:02d}"
    tabs = driver.find_elements(By.ID, tab_id)
    if not tabs:
        return False
    driver.execute_script("arguments[0].click();", tabs[0])
    # アクティブクラスが切り替わるまで待機
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, f"#{tab_id}.active"))
        )
    except Exception:
        time.sleep(random.uniform(3, 5))
    return True


def scrape_theater(
    driver: webdriver.Chrome,
    theater: dict,
    talent_ids: set[str],
    today: date,
) -> list[dict]:
    url = theater["url"]
    print(f"  劇場取得中: {theater['name']} ({url})")
    driver.get(url)

    # ページ初期ロード待機（タブリンク自体の出現まで確認）
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "ul.calendar-month li a[id^='month']")
            )
        )
    except Exception:
        print(f"  警告: calendar-month が見つかりません ({theater['name']})")
        return []

    target_months = get_target_months(today)
    events: list[dict] = []

    for year, month in target_months:
        print(f"    {year}年{month}月 取得中...")
        if not click_month_tab(driver, year, month):
            print(f"    タブなし（{year}/{month}）、スキップ")
            continue

        month_events = _parse_schedule(driver, theater, talent_ids, year, month)
        print(f"    {len(month_events)} 件ヒット")
        events.extend(month_events)

    return events


def _parse_schedule(
    driver: webdriver.Chrome,
    theater: dict,
    talent_ids: set[str],
    year: int,
    month: int,
) -> list[dict]:
    blocks = driver.find_elements(By.CSS_SELECTOR, "div.schedule-block")
    events = []

    for block in blocks:
        # ブロックIDから日付を取得: schedule2026-03-31
        block_id = block.get_attribute("id") or ""
        date_match = re.search(r"schedule(\d{4}-\d{2}-\d{2})", block_id)
        if not date_match:
            continue
        event_date = date_match.group(1)

        # 同じブロック内に複数公演がある場合、schedule-time と schedule-detail がペア
        time_divs = block.find_elements(By.CSS_SELECTOR, "div.schedule-time")
        detail_divs = block.find_elements(By.CSS_SELECTOR, "div.schedule-detail")

        for idx, time_div in enumerate(time_divs):
            detail_div = detail_divs[idx] if idx < len(detail_divs) else None
            event = _parse_event(
                time_div, detail_div, event_date, theater, talent_ids
            )
            if event:
                events.append(event)

    return events


def _parse_event(
    time_div,
    detail_div,
    event_date: str,
    theater: dict,
    talent_ids: set[str],
) -> dict | None:
    # タイトル（strong タグ）
    title_el = time_div.find_elements(By.CSS_SELECTOR, "strong")
    title = title_el[0].text.strip() if title_el else ""
    if not title:
        return None

    # 時刻: "開場17:00｜開演17:15｜終演18:25" 形式の span
    time_span = time_div.find_elements(By.CSS_SELECTOR, "span.bold.em")
    open_time = start_time = end_time = None
    if time_span:
        time_text = time_span[0].text
        open_m = re.search(r"開場(\d{1,2}:\d{2})", time_text)
        start_m = re.search(r"開演(\d{1,2}:\d{2})", time_text)
        end_m = re.search(r"終演(\d{1,2}:\d{2})", time_text)
        open_time = open_m.group(1) if open_m else None
        start_time = start_m.group(1) if start_m else None
        end_time = end_m.group(1) if end_m else None

    if not detail_div:
        return None

    # 出演者詳細（schedule-detail-member）
    # 芸人IDはリンクから取得（登録芸人の絞り込みに使用）
    # members は <a> タグを除去したテキストをそのまま使用
    member_el = detail_div.find_elements(By.CSS_SELECTOR, "dd.schedule-detail-member")
    member_talent_ids: set[str] = set()
    members: str = ""
    if member_el:
        links = member_el[0].find_elements(By.CSS_SELECTOR, "a[href*='/talent/detail']")
        for link in links:
            href = link.get_attribute("href") or ""
            id_m = re.search(r"id=(\d+)", href)
            if id_m:
                member_talent_ids.add(id_m.group(1))
        # innerHTML から <a> タグのみ除去（テキストは保持）してテキスト化
        html = member_el[0].get_attribute("innerHTML") or ""
        text = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", html, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", "", text)
        lines = [line.strip() for line in text.splitlines()]
        members = "\n".join(line for line in lines if line)

    # 登録芸人が含まれているか確認
    matched_talents = talent_ids & member_talent_ids
    if not matched_talents:
        return None

    # 料金
    price = _parse_price(detail_div)

    # チケットURL・配信URL
    ticket_url = online_url = None
    btn_links = detail_div.find_elements(By.CSS_SELECTOR, "div.btns a")
    for link in btn_links:
        href = link.get_attribute("href") or ""
        text = link.text.strip()
        if "online" in href.lower() or "ONLINE" in text or "配信" in text:
            online_url = href
        elif href:
            ticket_url = href

    return {
        "talent_id": None,
        "talent_name": None,
        "matched_talent_ids": sorted(matched_talents),
        "title": title,
        "date": event_date,
        "open_time": open_time,
        "start_time": start_time,
        "end_time": end_time,
        "members": members,
        "venue": theater["name"],
        "place": None,
        "image_url": None,
        "ticket_urls": [ticket_url] if ticket_url else [],
        "online_url": online_url,
        "price": price,
        "source": f"theater:{theater['id']}",
    }


def _parse_price(detail_div) -> dict | None:
    price = {}
    dls = detail_div.find_elements(By.CSS_SELECTOR, "dl")
    for dl in dls:
        dt = dl.find_elements(By.CSS_SELECTOR, "dt label")
        dd = dl.find_elements(By.CSS_SELECTOR, "dd")
        if not dt or not dd:
            continue
        label = dt[0].text.strip()
        value = dd[0].text.strip()
        if label == "料金":
            adv = re.search(r"前売[：:]?.*?¥([\d,]+)", value)
            door = re.search(r"当日[：:]?.*?¥([\d,]+)", value)
            if adv:
                price["advance"] = int(adv.group(1).replace(",", ""))
            if door:
                price["door"] = int(door.group(1).replace(",", ""))
        elif label == "オンライン":
            onl = re.search(r"¥([\d,]+)", value)
            if onl:
                price["online"] = int(onl.group(1).replace(",", ""))
    return price if price else None


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    talent_ids = {t["id"] for t in config["talents"]}
    theaters = config["theaters"]
    today = date.today()

    driver = build_driver()
    all_events: list[dict] = []

    try:
        for i, theater in enumerate(theaters):
            events = scrape_theater(driver, theater, talent_ids, today)
            all_events.extend(events)
            if i < len(theaters) - 1:
                wait = random.uniform(5, 10)
                print(f"  待機 {wait:.1f}秒...")
                time.sleep(wait)
    finally:
        driver.quit()

    OUTPUT_PATH.write_text(
        json.dumps(all_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n劇場取得完了: {len(all_events)} 件 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

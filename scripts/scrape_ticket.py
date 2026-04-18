"""
リマインド対象公演のチケット受付期間を fany.lol から取得する。

実行条件（スクレイプするかどうかの判断）:
  - remind:true の公演のみ対象
  - ticket_deadlines.json に未記録 → 即スクレイプ（新規ON後、次の30分チェックで反映）
  - 記録済みで最終更新から24時間未満 → スキップ
  - 公演日が今日以前 → スキップ（エントリがあれば削除）
  - remind が OFF になった公演 → エントリを削除
"""

import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from urllib.parse import quote

BASE_DIR      = Path(__file__).parent.parent
EVENTS_PATH   = BASE_DIR / "data" / "events.json"
DEADLINES_PATH = BASE_DIR / "data" / "ticket_deadlines.json"

JST = timezone(timedelta(hours=9))
FANY_SEARCH_URL = "https://ticket.fany.lol/search/event"
WEEKDAYS = "月火水木金土日"

REMIND_API_URL    = os.environ.get("REMIND_API_URL", "")
REMIND_API_SECRET = os.environ.get("REMIND_API_SECRET", "")

SCRAPE_INTERVAL_HOURS = 24


def now_jst() -> datetime:
    return datetime.now(JST)


def format_date_for_search(iso_date: str) -> str:
    """2026-05-01 → 2026/05/01(金)"""
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    wd = WEEKDAYS[dt.weekday()]
    return f"{dt.year}/{dt.month:02d}/{dt.day:02d}({wd})"


def get_remind_event_ids() -> list[str]:
    """Workers /api/remind-list から remind:true の eventId リストを取得"""
    if not REMIND_API_URL or not REMIND_API_SECRET:
        print("REMIND_API_URL / REMIND_API_SECRET が未設定")
        return []
    try:
        res = requests.get(
            REMIND_API_URL,
            headers={"Authorization": f"Bearer {REMIND_API_SECRET}"},
            timeout=10,
        )
        print(f"remind-list HTTP {res.status_code} (body={len(res.content)}bytes)")
        if res.status_code != 200:
            print(f"  レスポンス先頭: {res.text[:200]}")
            res.raise_for_status()
        return [item["eventId"] for item in res.json()]
    except Exception as e:
        print(f"remind-list 取得エラー: {e}")
        return []


def scrape_tickets(title: str, date_str: str) -> list[dict]:
    """fany.lol の検索ページからチケット受付情報を取得"""
    date_fmt = format_date_for_search(date_str)
    url = (
        f"{FANY_SEARCH_URL}"
        f"?keywords={quote(title)}&from={quote(date_fmt)}&search_type=form"
    )
    headers = {"User-Agent": "Mozilla/5.0 (compatible; fanaby-event-bot/1.0)"}
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    tickets = []

    for info in soup.select(".fany_g-ticketInfo"):
        # ステータステキスト（ul[class*="fany_icon__"] の最初の li）
        status_ul = info.select_one("ul[class*='fany_icon__']")
        status_text = ""
        if status_ul:
            li = status_ul.find("li")
            status_text = li.get_text(strip=True) if li else ""

        text_div = info.select_one(".fany_g-ticketInfo__text")
        if not text_div:
            continue

        # 直接の子 span を2つ取る（販売種別名・受付期間）
        spans = text_div.find_all("span", recursive=False)
        if len(spans) < 2:
            continue

        name = spans[0].get_text(strip=True)

        # 受付期間テキスト: span 内の <span class="g-dayofweek*"> を除いてパース
        period_text = spans[1].get_text(" ", strip=True)
        m = re.search(
            r"受付期間[：:]\s*(\d{4}/\d{2}/\d{2}).*?(\d{2}:\d{2})\s*〜\s*(\d{4}/\d{2}/\d{2}).*?(\d{2}:\d{2})",
            period_text,
        )
        if not m:
            continue

        start = f"{m.group(1)} {m.group(2)}"
        end   = f"{m.group(3)} {m.group(4)}"

        link = info.select_one("a[href]")
        ticket_url = link["href"] if link else ""

        ticket_type = "general" if name == "一般発売" else "lottery"

        tickets.append({
            "name":        name,
            "type":        ticket_type,
            "status_text": status_text,
            "start":       start,
            "end":         end,
            "url":         ticket_url,
        })

    return tickets


def main():
    today = date.today()
    now   = now_jst()

    # events.json から id → イベント情報のマッピングを作成
    events_data = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    events_map  = {e["id"]: e for e in events_data.get("events", [])}

    # ticket_deadlines.json を読み込み（なければ空で初期化）
    if DEADLINES_PATH.exists():
        deadlines = json.loads(DEADLINES_PATH.read_text(encoding="utf-8"))
    else:
        deadlines = {"updated_at": "", "events": {}}

    # リマインド対象 eventId を取得
    remind_ids = set(get_remind_event_ids())
    if not remind_ids:
        print("リマインド対象なし")
        return

    updated = False

    # リマインドON の公演をスクレイプ
    for event_id in remind_ids:
        ev = events_map.get(event_id)
        if not ev:
            print(f"スキップ（events.json に未登録）: {event_id}")
            continue

        # 過去公演はスキップ
        try:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if ev_date < today:
            print(f"スキップ（過去公演）: {event_id} {ev['date']}")
            continue

        # 24時間以内に更新済みならスキップ
        existing = deadlines["events"].get(event_id)
        if existing:
            try:
                scraped_at = datetime.fromisoformat(existing["scraped_at"])
                if (now - scraped_at).total_seconds() < SCRAPE_INTERVAL_HOURS * 3600:
                    print(f"スキップ（{SCRAPE_INTERVAL_HOURS}h以内に更新済み）: {event_id}")
                    continue
            except (KeyError, ValueError):
                pass  # scraped_at が不正な場合はスクレイプし直す

        # スクレイプ実行
        print(f"スクレイプ: {event_id} {ev['title'][:40]}")
        try:
            tickets = scrape_tickets(ev["title"], ev["date"])
        except Exception as e:
            print(f"  エラー: {e}")
            continue

        deadlines["events"][event_id] = {
            "title":      ev["title"],
            "date":       ev["date"],
            "scraped_at": now.isoformat(),
            "tickets":    tickets,
        }
        updated = True
        print(f"  取得完了: {len(tickets)} 件")

    if updated:
        deadlines["updated_at"] = now.isoformat()
        DEADLINES_PATH.write_text(
            json.dumps(deadlines, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("ticket_deadlines.json を更新しました")
    else:
        print("変更なし（ticket_deadlines.json は更新しません）")


if __name__ == "__main__":
    main()

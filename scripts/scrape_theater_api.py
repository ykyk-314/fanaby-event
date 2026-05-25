"""
劇場スケジュールを feed-api から取得するスクリプト。
Selenium を使わず requests で JSON を直接取得し、theater_events.json として保存する。
"""

import json
import re
import sys
import requests
from calendar import monthrange
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
OUTPUT_PATH = BASE_DIR / "data" / "theater_events.json"

API_BASE = "https://feed-api.yoshimoto.co.jp/fany/theater/v1"
API_VENUE = "01"
FETCH_MONTHS = 2

sys.path.insert(0, str(Path(__file__).parent))
from _talents_kv import fetch_talents_master


def get_date_range(today: date) -> tuple[str, str]:
    """今日〜FETCH_MONTHS ヶ月後の末日を YYYYMMDD 形式で返す。"""
    date_from = today.strftime("%Y%m%d")
    y, m = today.year, today.month
    for _ in range(FETCH_MONTHS):
        m += 1
        if m > 12:
            m = 1
            y += 1
    last_day = monthrange(y, m)[1]
    date_to = f"{y}{m:02d}{last_day:02d}"
    return date_from, date_to


def fetch_theater(api_id: str, date_from: str, date_to: str) -> list[dict]:
    url = (
        f"{API_BASE}"
        f"?theater={api_id}&venue={API_VENUE}"
        f"&date_from={date_from}&date_to={date_to}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_talent_ids(member_html: str) -> set[str]:
    """memberHtml のリンクから talent ID を抽出する。"""
    return set(re.findall(r"id=(\d+)", member_html))


def match_by_name(member_text: str, talent_name_to_id: dict[str, str]) -> set[str]:
    """member テキストに芸人名が含まれる場合、対応するIDを返す。
    HTMLリンクなしのプレーンテキスト形式にフォールバックするために使用。
    """
    return {tid for name, tid in talent_name_to_id.items() if name and name in member_text}


def extract_members(member_html: str) -> str:
    """memberHtml から <a> タグのみ除去したプレーンテキストを返す。"""
    text = re.sub(r"<br\s*/?>", "\n", member_html, flags=re.IGNORECASE)
    text = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_price(price_str: str | None) -> int | None:
    """'¥1,300' 形式を整数に変換する。"""
    if not price_str:
        return None
    digits = re.sub(r"[^\d]", "", price_str)
    return int(digits) if digits else None


def parse_event(
    item: dict, theater: dict, talent_ids: set[str],
    talent_name_to_id: dict[str, str] | None = None,
) -> dict | None:
    member_html = item.get("memberHtml") or ""
    member_talent_ids = extract_talent_ids(member_html)
    # memberHtml に <a href="...?id=XXXXXX"> 形式のリンクがない場合、芸人名で照合
    if not member_talent_ids and talent_name_to_id:
        member_text = item.get("member") or member_html
        member_talent_ids = match_by_name(member_text, talent_name_to_id)
    matched = talent_ids & member_talent_ids
    if not matched:
        return None

    # 日付: YYYY/MM/DD → YYYY-MM-DD
    event_date = item["date"].replace("/", "-")

    members = extract_members(member_html)

    price: dict = {}
    if p := parse_price(item.get("price1")):
        price["advance"] = p
    if p := parse_price(item.get("price2")):
        price["door"] = p
    if p := parse_price(item.get("price3")):
        price["online"] = p

    # ticket_url は fany.lol 形式のみ採用
    raw_url1 = item.get("url1") or ""
    ticket_url = raw_url1 if "ticket.fany.lol" in raw_url1 else None

    return {
        "matched_talent_ids": sorted(matched),
        "title": item["name"],
        "date": event_date,
        "open_time": item.get("dateTime1"),
        "start_time": item.get("dateTime2"),
        "end_time": item.get("dateTime3"),
        "members": members,
        "venue": theater["name"],
        "prefecture": theater.get("prefecture"),
        "image_url": item.get("url3"),
        "ticket_url": ticket_url,
        "online_url": item.get("url2"),
        "notice": item.get("notice") or None,
        "price": price or None,
        "source": f"theater:{theater['id']}",
    }


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    kv_talents = fetch_talents_master(config.get("talents", []))
    talent_ids = {t["id"] for t in kv_talents}
    talent_name_to_id = {t["name"]: t["id"] for t in kv_talents if t.get("name")}
    today = date.today()
    date_from, date_to = get_date_range(today)
    print(f"取得期間: {date_from} 〜 {date_to}")

    all_events: list[dict] = []

    for theater in config["theaters"]:
        api_id = theater.get("api_id")
        if not api_id:
            print(f"  スキップ（api_id未設定）: {theater['name']}")
            continue
        print(f"  劇場取得中: {theater['name']}")
        try:
            items = fetch_theater(api_id, date_from, date_to)
        except Exception as e:
            print(f"  警告: 取得失敗 ({theater['name']}): {e}")
            continue
        events = [e for item in items if (e := parse_event(item, theater, talent_ids, talent_name_to_id))]
        print(f"    {len(events)} 件ヒット（全 {len(items)} 件中）")
        all_events.extend(events)

    OUTPUT_PATH.write_text(
        json.dumps(all_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n劇場取得完了: {len(all_events)} 件 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

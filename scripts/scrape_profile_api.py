"""
芸人プロフィールの公演情報を feed-api から取得するスクリプト。
Selenium を使わず requests で JSON を直接取得し、profile_events.json として保存する。
"""

import json
import re
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
OUTPUT_PATH = BASE_DIR / "data" / "profile_events.json"

API_BASE = "https://feed-api.yoshimoto.co.jp/fany/tickets/v2"


def fetch_talent(talent_id: str) -> list[dict]:
    resp = requests.get(API_BASE, params={"id": talent_id}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_venue_prefecture(item: dict) -> tuple[str | None, str | None]:
    """place フィールド「劇場名（都道府県）」を分割して (venue, prefecture) を返す。
    isPermanentPlace に関わらず一律で place フィールドから取得する。
    """
    place = item.get("place") or ""
    m = re.match(r"^(.+?)（(.+?)）$", place.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return place.strip() or None, None


def parse_event(item: dict, talent: dict) -> dict | None:
    date2 = item.get("date2")
    if not date2:
        return None

    try:
        dt2 = datetime.fromisoformat(date2)
    except ValueError:
        return None

    event_date = dt2.date().isoformat()
    start_time = dt2.strftime("%H:%M")

    open_time = None
    date1 = item.get("date1")
    if date1:
        try:
            open_time = datetime.fromisoformat(date1).strftime("%H:%M")
        except ValueError:
            pass

    title = (item.get("name") or "").strip()
    if not title:
        return None

    venue, prefecture = parse_venue_prefecture(item)
    members = (item.get("member") or "").replace("\r\n", "\n").strip()
    image_url = item.get("url1") or None

    return {
        "talents": {talent["id"]: talent["name"]},
        "title": title,
        "date": event_date,
        "open_time": open_time,
        "start_time": start_time,
        "members": members,
        "venue": venue,
        "prefecture": prefecture,
        "image_url": image_url,
        "source": "profile",
    }


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    talents = config["talents"]
    all_events: list[dict] = []

    for talent in talents:
        print(f"  取得中: {talent['name']}")
        try:
            items = fetch_talent(talent["id"])
        except Exception as e:
            print(f"  警告: 取得失敗 ({talent['name']}): {e}")
            continue

        merged: dict[tuple, dict] = {}
        for item in items:
            event = parse_event(item, talent)
            if not event:
                continue
            key = (event["date"], event["title"], event["start_time"])
            if key not in merged:
                merged[key] = event

        events = list(merged.values())
        print(f"    {len(events)} 件取得（全 {len(items)} 件中）")
        all_events.extend(events)

    OUTPUT_PATH.write_text(
        json.dumps(all_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nプロフィール取得完了: {len(all_events)} 件 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

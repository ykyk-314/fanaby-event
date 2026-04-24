"""
芸人プロフィールの公演情報を feed-api から取得するスクリプト。
Selenium を使わず requests で JSON を直接取得し、profile_events.json として保存する。
"""

import json
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


def parse_venue_place(item: dict) -> tuple[str | None, str | None]:
    """venue と place を返す。既存スクリプトの出力形式に合わせる。"""
    if item.get("isPermanentPlace"):
        # 吉本管轄劇場: placeType が劇場名、city が所在地
        venue = item.get("placeType") or None
        place = item.get("city") or None
    else:
        # その他劇場: place をそのまま venue に（"会場名（都道府県）" 形式で保持）
        venue = item.get("place") or None
        place = None
    return venue, place


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

    venue, place = parse_venue_place(item)
    members = (item.get("member") or "").replace("\r\n", "\n").strip()
    image_url = item.get("url1") or None

    return {
        "talent_id": talent["id"],
        "talent_name": talent["name"],
        "title": title,
        "date": event_date,
        "open_time": open_time,
        "start_time": start_time,
        "members": members,
        "place": place,
        "venue": venue,
        "image_url": image_url,
        "ticket_urls": [],
        "source": "profile",
    }


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    talents = config["talents"]
    all_events: list[dict] = []

    # 同一公演が複数エントリになる場合（ticket_urlのみ異なる）を統合する
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
            else:
                for url in event["ticket_urls"]:
                    if url not in merged[key]["ticket_urls"]:
                        merged[key]["ticket_urls"].append(url)

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

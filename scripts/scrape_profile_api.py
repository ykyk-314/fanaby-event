"""
芸人プロフィールの公演情報を feed-api から取得するスクリプト。
Selenium を使わず requests で JSON を直接取得し、profile_events.json として保存する。
"""

import json
import re
import sys
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
OUTPUT_PATH = BASE_DIR / "data" / "profile_events.json"

API_BASE = "https://feed-api.yoshimoto.co.jp/fany/tickets/v2"
PROFILE_BASE = "https://profile.yoshimoto.co.jp/talent/detail"

sys.path.insert(0, str(Path(__file__).parent))
from _talents_kv import fetch_talents_master, patch_talent


def fetch_talent(talent_id: str) -> list[dict]:
    resp = requests.get(API_BASE, params={"id": talent_id}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_venue_prefecture(item: dict) -> tuple[str | None, str | None]:
    """place フィールド「劇場名（都道府県）」を分割して (venue, prefecture) を返す。
    末尾の（都道府県）を greedy で探すため、"銀座ブロッサム（中央会館）ホール（東京都）"
    のように会場名に括弧を含む場合も正しく分割できる。
    """
    place = item.get("place") or ""
    # 末尾の（...都/道/府/県）を都道府県として切り出す
    m = re.match(r"^(.+)（(.+?[都道府県])）$", place.strip())
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


def scrape_profile_info(talent: dict) -> dict:
    """プロフィールページから name と image_url を取得する。失敗時は空 dict。"""
    url = talent.get("profile_url") or f"{PROFILE_BASE}?id={talent['id']}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"    警告: プロフィールページ取得失敗 ({talent['id']}): {e}")
        return {}

    result: dict = {}
    # <p class="prof_name">シンクロニシティ</p>
    m = re.search(r'<p\b[^>]*class=["\'][^"\']*\bprof_name\b[^"\']*["\'][^>]*>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
    if m:
        name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if name:
            result["name"] = name
    # <div id="js-profSlide">...<img src="...">...
    m = re.search(r'id=["\']js-profSlide["\'][^>]*>.*?<img\s+src=["\']([^"\']+)["\']', html, re.DOTALL)
    if m:
        img_url = m.group(1).strip()
        if img_url.startswith("http"):
            result["image_url"] = img_url
    return result


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    talents = fetch_talents_master(config.get("talents", []))
    all_events: list[dict] = []

    for talent in talents:
        display_name = talent.get("name") or f"ID:{talent['id']}"
        print(f"  取得中: {display_name}")
        try:
            items = fetch_talent(talent["id"])
        except Exception as e:
            print(f"  警告: 取得失敗 ({display_name}): {e}")
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

    # name / image_url が未設定の芸人をプロフィールページから補完
    needs_patch = [t for t in talents if not t.get("name") or not t.get("image_url")]
    if needs_patch:
        print(f"\nプロフィール情報補完: {len(needs_patch)} 件")
        for talent in needs_patch:
            info = scrape_profile_info(talent)
            if not info:
                continue
            kw: dict = {}
            if not talent.get("name") and info.get("name"):
                kw["name"] = info["name"]
                print(f"    名前補完: {talent['id']} → {info['name']}")
            if not talent.get("image_url") and info.get("image_url"):
                kw["image_url"] = info["image_url"]
                print(f"    画像補完: {talent['id']} → (取得)")
            if kw:
                patch_talent(talent["id"], **kw)

    OUTPUT_PATH.write_text(
        json.dumps(all_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nプロフィール取得完了: {len(all_events)} 件 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

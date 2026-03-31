"""
プロフィール取得分と劇場取得分をマージし、events.json を更新するスクリプト。

処理フロー:
1. profile_events.json と theater_events.json を読み込む
2. 劇場取得分を同一公演に統合（照合キー: date + 正規化タイトル）
3. 既存 events.json と比較して差分を検出（new / updated）
4. events.json を上書き保存
"""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
EVENTS_PATH = BASE_DIR / "data" / "events.json"
PROFILE_PATH = BASE_DIR / "data" / "profile_events.json"
THEATER_PATH = BASE_DIR / "data" / "theater_events.json"

JST = timezone(timedelta(hours=9))

# 変更を検知するフィールド（これらが変わったら updated とみなす）
WATCH_FIELDS = ["members", "image_url", "ticket_url", "online_url", "price",
                "open_time", "start_time", "end_time", "venue"]


def now_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def normalize_title(title: str) -> str:
    """タイトルを正規化して照合しやすくする（全角→半角、空白・記号除去）。"""
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r"[\s\u3000\-－―「」『』【】（）()「」\[\]【】〜〜~・]", "", title)
    return title.lower()


def make_event_id(talent_id: str, event_date: str, title: str) -> str:
    """イベントID: SHA1(talent_id + date + normalized_title) の先頭8文字。"""
    key = f"{talent_id}:{event_date}:{normalize_title(title)}"
    return hashlib.sha1(key.encode()).hexdigest()[:8]


def load_profile_events() -> list[dict]:
    if not PROFILE_PATH.exists():
        return []
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_theater_events() -> list[dict]:
    if not THEATER_PATH.exists():
        return []
    return json.loads(THEATER_PATH.read_text(encoding="utf-8"))


def load_existing_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    data = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    return data.get("events", [])


def build_event_from_profile(p: dict) -> dict:
    """プロフィール取得データをイベントレコードに変換する。"""
    return {
        "id": make_event_id(p["talent_id"], p["date"], p["title"]),
        "talent_id": p["talent_id"],
        "talent_name": p["talent_name"],
        "title": p["title"],
        "date": p["date"],
        "open_time": None,
        "start_time": p.get("start_time"),
        "end_time": None,
        "members": p.get("members", []),
        "venue": p.get("venue"),
        "place": p.get("place"),
        "image_url": p.get("image_url"),
        "ticket_url": p.get("ticket_url"),
        "online_url": None,
        "price": None,
        "sources": [p["source"]],
    }


def merge_theater_into_events(
    events: list[dict],
    theater_events: list[dict],
    config: dict,
) -> None:
    """
    劇場イベントをプロフィールイベントリストに統合する。
    同一公演は照合キー（talent_id + date + 正規化タイトル）で突き合わせ、
    プロフィール側の不足情報を補完する。
    劇場のみにある公演は新規エントリとして追加する。
    """
    talent_map = {t["id"]: t["name"] for t in config["talents"]}

    # events を (talent_id, date, norm_title) → index のインデックスに
    event_index: dict[str, int] = {}
    for i, ev in enumerate(events):
        key = _theater_key(ev["talent_id"], ev["date"], ev["title"])
        event_index[key] = i

    for te in theater_events:
        for tid in te["matched_talent_ids"]:
            key = _theater_key(tid, te["date"], te["title"])
            if key in event_index:
                # 既存イベントに劇場情報を補完
                ev = events[event_index[key]]
                _patch_from_theater(ev, te)
            else:
                # 劇場にしか存在しないイベントを新規追加
                new_ev = _build_event_from_theater(te, tid, talent_map)
                if new_ev:
                    events.append(new_ev)
                    event_index[key] = len(events) - 1


def _theater_key(talent_id: str, event_date: str, title: str) -> str:
    return f"{talent_id}:{event_date}:{normalize_title(title)}"


def _patch_from_theater(ev: dict, te: dict) -> None:
    """劇場データでイベントの不足フィールドを補完する。"""
    if not ev.get("open_time") and te.get("open_time"):
        ev["open_time"] = te["open_time"]
    if not ev.get("start_time") and te.get("start_time"):
        ev["start_time"] = te["start_time"]
    if not ev.get("end_time") and te.get("end_time"):
        ev["end_time"] = te["end_time"]
    if not ev.get("online_url") and te.get("online_url"):
        ev["online_url"] = te["online_url"]
    if not ev.get("price") and te.get("price"):
        ev["price"] = te["price"]
    if te.get("members") and len(te["members"]) > len(ev.get("members", [])):
        ev["members"] = te["members"]
    src = te.get("source")
    if src and src not in ev.get("sources", []):
        ev.setdefault("sources", []).append(src)


def _build_event_from_theater(te: dict, talent_id: str, talent_map: dict) -> dict | None:
    talent_name = talent_map.get(talent_id)
    if not talent_name:
        return None
    return {
        "id": make_event_id(talent_id, te["date"], te["title"]),
        "talent_id": talent_id,
        "talent_name": talent_name,
        "title": te["title"],
        "date": te["date"],
        "open_time": te.get("open_time"),
        "start_time": te.get("start_time"),
        "end_time": te.get("end_time"),
        "members": te.get("members", []),
        "venue": te.get("venue"),
        "place": te.get("place"),
        "image_url": None,
        "ticket_url": te.get("ticket_url"),
        "online_url": te.get("online_url"),
        "price": te.get("price"),
        "sources": [te["source"]],
    }


def diff_and_update(
    scraped: list[dict],
    existing: list[dict],
) -> list[dict]:
    """
    スクレイプ結果と既存データを比較し、差分を検出してステータスを付与する。
    返り値: 更新済みの全イベントリスト
    """
    ts = now_jst()

    # 既存データを id → record のマップに
    existing_map: dict[str, dict] = {ev["id"]: ev for ev in existing}

    result: list[dict] = []
    for ev in scraped:
        eid = ev["id"]
        if eid not in existing_map:
            # 新規
            ev["status"] = "new"
            ev["first_seen"] = ts
            ev["last_updated"] = ts
            ev["notified_at"] = None
        else:
            old = existing_map[eid]
            changed_fields = [
                f for f in WATCH_FIELDS
                if ev.get(f) != old.get(f)
            ]
            if changed_fields:
                # 変更あり
                ev["status"] = "updated"
                ev["last_updated"] = ts
                ev["diff"] = {f: {"before": old.get(f), "after": ev.get(f)} for f in changed_fields}
                # notified 済みのものが再更新された場合は上書き
                ev["first_seen"] = old.get("first_seen", ts)
                ev["notified_at"] = old.get("notified_at")
            else:
                # 変更なし: 既存のステータスをそのまま維持
                ev["status"] = old.get("status", "notified")
                ev["first_seen"] = old.get("first_seen", ts)
                ev["last_updated"] = old.get("last_updated", ts)
                ev["notified_at"] = old.get("notified_at")
                ev["diff"] = old.get("diff")
        result.append(ev)

    new_count = sum(1 for e in result if e["status"] == "new")
    updated_count = sum(1 for e in result if e["status"] == "updated")
    print(f"差分検出: 新規 {new_count} 件、更新 {updated_count} 件")
    return result


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    print("プロフィールイベント読み込み中...")
    profile_events = load_profile_events()
    print(f"  {len(profile_events)} 件")

    print("劇場イベント読み込み中...")
    theater_events = load_theater_events()
    print(f"  {len(theater_events)} 件")

    print("既存 events.json 読み込み中...")
    existing_events = load_existing_events()
    print(f"  {len(existing_events)} 件")

    # プロフィール取得分をベースにイベントリストを構築
    scraped: list[dict] = [build_event_from_profile(p) for p in profile_events]

    # 劇場取得分をマージ
    print("劇場データをマージ中...")
    merge_theater_into_events(scraped, theater_events, config)
    print(f"  マージ後: {len(scraped)} 件")

    # 差分検出
    print("差分を検出中...")
    final_events = diff_and_update(scraped, existing_events)

    # 日付順にソート
    final_events.sort(key=lambda e: (e["date"], e.get("start_time") or ""))

    output = {
        "updated_at": now_jst(),
        "events": final_events,
    }
    EVENTS_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nmerge 完了: {len(final_events)} 件 → {EVENTS_PATH}")


if __name__ == "__main__":
    main()

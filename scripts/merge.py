"""
劇場取得分と芸人プロフィール取得分をマージし、events.json を更新するスクリプト。

処理フロー:
1. theater_events.json をベースにイベントリストを構築（1公演 = 1レコード）
2. profile_events.json でギャップ補完（劇場にない公演を追加、talents に芸人を追加）
3. 既存 events.json と比較して差分を検出（new / updated）
4. events.json を上書き保存
"""

import hashlib
import json
import os
import re
import unicodedata
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"
EVENTS_PATH = BASE_DIR / "data" / "events.json"
FLIERS_DIR = BASE_DIR / "docs" / "fliers"
PROFILE_PATH = BASE_DIR / "data" / "profile_events.json"
THEATER_PATH = BASE_DIR / "data" / "theater_events.json"

JST = timezone(timedelta(hours=9))

# 変更を検知するフィールド（これらが変わったら updated とみなす）
# online_url は一度取得したら更新しない仕様のため除外
WATCH_FIELDS = ["members", "image_url", "ticket_url", "price",
                "open_time", "start_time", "end_time", "venue", "notice"]

# 公演日当日のみチェックするフィールド
# 当日券はサイトから購入不可になるため ticket_url 等が変動するが通知対象外とする
WATCH_FIELDS_TODAY = ["members"]


def now_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def fetch_excluded_events() -> set[str] | None:
    """Cloudflare Pages API から除外イベントIDリストを取得する。
    取得失敗時は None を返し、呼び出し元が既存フラグを維持する。
    """
    api_url = os.environ.get("REMIND_API_URL", "").rstrip("/")
    api_secret = os.environ.get("REMIND_API_SECRET", "")
    if not api_url or not api_secret:
        print("REMIND_API_URL / REMIND_API_SECRET 未設定 — 除外リスト取得をスキップ")
        return None
    try:
        req = urllib.request.Request(
            f"{api_url}/api/excluded-events",
            headers={"Authorization": f"Bearer {api_secret}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ids = set(data.get("ids", []))
            print(f"除外リスト取得: {len(ids)} 件")
            return ids
    except Exception as e:
        print(f"警告: 除外リスト取得失敗: {e}")
        return None


def _normalize_ticket_url(url: str | None) -> str | None:
    """/event/detail/ パスのチケットURLのみ採用し、クエリパラメータを除去する。"""
    if not url:
        return None
    parsed = urlparse(url)
    if "/event/detail/" not in parsed.path:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def normalize_title(title: str) -> str:
    """タイトルを正規化して照合しやすくする（全角→半角、空白・記号除去）。"""
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r"[\s\u3000\-－―「」『』【】（）()「」\[\]【】〜〜~・]", "", title)
    return title.lower()


def make_event_id(event_date: str, title: str,
                  venue: str | None = None, start_time: str | None = None) -> str:
    """イベントID: SHA1(date + venue + start_time) の先頭8文字。
    venue/start_time が不明な場合は normalized_title にフォールバック。
    talent_id はハッシュから除外（同一公演に複数芸人が出演するケースで1レコードに統合するため）。
    """
    if venue and start_time:
        key = f"{event_date}:{venue}:{start_time}"
    else:
        key = f"{event_date}:{normalize_title(title)}"
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
    events = data.get("events", [])
    # ticket_urls（旧スキーマ）→ ticket_url（新スキーマ）へのマイグレーション
    for ev in events:
        if "ticket_urls" in ev and "ticket_url" not in ev:
            urls = ev.pop("ticket_urls")
            ev["ticket_url"] = urls[0] if urls else None
    return events


def build_events_from_theater(theater_events: list[dict], config: dict) -> list[dict]:
    """劇場取得データからイベントリストを構築する。1公演 = 1レコード。"""
    talent_map = {t["id"]: t["name"] for t in config["talents"]}
    events: list[dict] = []
    id_index: dict[str, int] = {}

    for te in theater_events:
        eid = make_event_id(te["date"], te["title"],
                            venue=te.get("venue"), start_time=te.get("start_time"))
        talents = {tid: talent_map[tid]
                   for tid in te["matched_talent_ids"] if tid in talent_map}

        if eid in id_index:
            # 同IDが重複した場合（日時・会場・開演が同一の別エントリ）は talents をマージ
            events[id_index[eid]]["talents"].update(talents)
            events[id_index[eid]]["talents"] = dict(sorted(events[id_index[eid]]["talents"].items()))
            continue

        ev = {
            "id": eid,
            "talents": dict(sorted(talents.items())),
            "title": te["title"],
            "date": te["date"],
            "open_time": te.get("open_time"),
            "start_time": te.get("start_time"),
            "end_time": te.get("end_time"),
            "members": te.get("members", ""),
            "venue": te.get("venue"),
            "prefecture": te.get("prefecture"),
            "image_url": te.get("image_url"),
            "ticket_url": te.get("ticket_url"),
            "online_url": te.get("online_url"),
            "notice": te.get("notice"),
            "price": te.get("price"),
            "sources": [te["source"]],
        }
        id_index[eid] = len(events)
        events.append(ev)

    return events


def merge_profile_into_events(events: list[dict], profile_events: list[dict]) -> None:
    """プロフィール取得データを劇場ベースのイベントリストに補完マージする。
    - 同一公演（IDで照合）: talents に芸人を追加、theater が null のフィールドのみ補完
    - 劇場にない公演: プロフィールのみの新規エントリとして追加
    """
    id_index: dict[str, int] = {ev["id"]: i for i, ev in enumerate(events)}

    for pe in profile_events:
        eid = make_event_id(pe["date"], pe["title"],
                            venue=pe.get("venue"), start_time=pe.get("start_time"))

        if eid in id_index:
            ev = events[id_index[eid]]
            # talents: theater 側にいない芸人のみ追加
            for tid, tname in (pe.get("talents") or {}).items():
                ev["talents"].setdefault(tid, tname)
            ev["talents"] = dict(sorted(ev["talents"].items()))
            # theater 側が null の場合のみセット（theater 優先厳守）
            if ev.get("image_url") is None and pe.get("image_url"):
                ev["image_url"] = pe["image_url"]
            if ev.get("open_time") is None and pe.get("open_time"):
                ev["open_time"] = pe["open_time"]
            if ev.get("start_time") is None and pe.get("start_time"):
                ev["start_time"] = pe["start_time"]
            src = pe.get("source")
            if src and src not in ev.get("sources", []):
                ev.setdefault("sources", []).append(src)
        else:
            # プロフィールにしかない公演を新規追加
            talents = pe.get("talents") or {}
            new_ev = {
                "id": eid,
                "talents": dict(sorted(talents.items())),
                "title": pe["title"],
                "date": pe["date"],
                "open_time": pe.get("open_time"),
                "start_time": pe.get("start_time"),
                "end_time": None,
                "members": pe.get("members", ""),
                "venue": pe.get("venue"),
                "prefecture": pe.get("prefecture"),
                "image_url": pe.get("image_url"),
                "ticket_url": None,
                "online_url": None,
                "notice": None,
                "price": None,
                "sources": [pe.get("source", "profile")],
            }
            id_index[eid] = len(events)
            events.append(new_ev)


def download_flyers(
    events: list[dict],
    existing_map: dict[str, dict],
    url_to_local: dict[str, str],
) -> None:
    """
    フライヤー画像をローカルに保存する。
    - ① 新IDのファイルが既に存在: スキップ（冪等性）
    - ② 同じ image_url の旧ファイルが存在: リネーム（IDリセット移行対応）
    - ③ 上記いずれでもなければダウンロード
    """
    FLIERS_DIR.mkdir(parents=True, exist_ok=True)
    _ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    downloaded = renamed = skipped = 0

    for ev in events:
        url = ev.get("image_url")
        if not url:
            ev["local_image"] = existing_map.get(ev["id"], {}).get("local_image")
            continue

        _raw_suffix = Path(url.split("?")[0]).suffix.lower()
        suffix = _raw_suffix if _raw_suffix in _ALLOWED_SUFFIXES else ".jpg"
        new_filename = f"{ev['id']}{suffix}"
        new_path = FLIERS_DIR / new_filename

        # ① 新IDのファイルが既に存在するならスキップ
        if new_path.exists():
            ev["local_image"] = f"fliers/{new_filename}"
            skipped += 1
            continue

        # ② 同じ image_url の旧ファイルが存在するならリネーム
        old_local = url_to_local.get(url)
        if old_local:
            old_path = BASE_DIR / "docs" / old_local
            if old_path.exists():
                old_path.rename(new_path)
                ev["local_image"] = f"fliers/{new_filename}"
                renamed += 1
                continue

        # ③ ダウンロード
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                new_path.write_bytes(resp.read())
            ev["local_image"] = f"fliers/{new_filename}"
            downloaded += 1
        except Exception as e:
            print(f"  警告: フライヤー取得失敗 ({ev['title'][:20]}): {e}")
            ev["local_image"] = existing_map.get(ev["id"], {}).get("local_image")

    print(f"フライヤー: 新規 {downloaded} 件、リネーム {renamed} 件、スキップ {skipped} 件")


def diff_and_update(
    scraped: list[dict],
    existing: list[dict],
) -> list[dict]:
    """
    スクレイプ結果と既存データを比較し、差分を検出してステータスを付与する。
    返り値: 更新済みの全イベントリスト
    """
    ts = now_jst()
    today = datetime.now(JST).date().isoformat()

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
            # 既存の excluded フラグを引き継ぎ（API取得失敗時のフォールバック）
            if old.get("excluded"):
                ev["excluded"] = True
            # 公演日当日は ticket_url 等が販売終了で変動するため members のみチェック
            watch = WATCH_FIELDS_TODAY if ev.get("date") == today else WATCH_FIELDS
            changed_fields = [
                f for f in watch
                if ev.get(f) != old.get(f)
            ]
            if changed_fields:
                # 変更あり — DEBUG: 何が変わったかコンソールに出力
                print(f"  [UPDATED] {ev['title']} ({ev['date']})")
                for f in changed_fields:
                    print(f"    {f}: {old.get(f)!r} → {ev.get(f)!r}")
                ev["status"] = "updated"
                ev["last_updated"] = ts
                ev["diff"] = {f: {"before": old.get(f), "after": ev.get(f)} for f in changed_fields}
                # notified 済みのものが再更新された場合は上書き
                ev["first_seen"] = old.get("first_seen", ts)
                ev["notified_at"] = old.get("notified_at")
            else:
                # 変更なし
                # - new: まだ通知されていない新規公演なので維持
                # - updated: 今回変更なし = 変更は解消済みなので notified にリセット
                # - notified: そのまま維持
                old_status = old.get("status", "notified")
                ev["status"] = old_status if old_status == "new" else "notified"
                ev["first_seen"] = old.get("first_seen", ts)
                ev["last_updated"] = old.get("last_updated", ts)
                ev["notified_at"] = old.get("notified_at")
                ev["diff"] = None  # 変更なしなので diff もクリア
        result.append(ev)

    # スクレイプに現れなかった既存イベント（サイトから消えた過去公演等）を保持する
    scraped_ids = {ev["id"] for ev in result}
    carried_over = [ev for ev in existing if ev["id"] not in scraped_ids]
    if carried_over:
        print(f"既存イベント引き継ぎ: {len(carried_over)} 件（サイトから消えたが保持）")
    result.extend(carried_over)

    new_count = sum(1 for e in result if e["status"] == "new")
    updated_count = sum(1 for e in result if e["status"] == "updated")
    print(f"差分検出: 新規 {new_count} 件、更新 {updated_count} 件")
    return result


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    print("劇場イベント読み込み中...")
    theater_events = load_theater_events()
    print(f"  {len(theater_events)} 件")

    print("プロフィールイベント読み込み中...")
    profile_events = load_profile_events()
    print(f"  {len(profile_events)} 件")

    print("既存 events.json 読み込み中...")
    existing_events = load_existing_events()
    print(f"  {len(existing_events)} 件")

    # 劇場取得分をベースにイベントリストを構築（1公演 = 1レコード）
    print("劇場データからイベントリストを構築中...")
    scraped: list[dict] = build_events_from_theater(theater_events, config)
    print(f"  {len(scraped)} 件")

    # プロフィール取得分でギャップ補完
    print("プロフィールデータをマージ中...")
    merge_profile_into_events(scraped, profile_events)
    print(f"  マージ後: {len(scraped)} 件")

    # 除外タイトルフィルタ（部分一致）
    exclude_titles: list[str] = config.get("exclude_titles", [])
    if exclude_titles:
        before = len(scraped)
        scraped = [
            ev for ev in scraped
            if not any(kw in ev["title"] for kw in exclude_titles)
        ]
        print(f"除外フィルタ適用: {before - len(scraped)} 件除外 → {len(scraped)} 件")

    # チケットURL: 劇場データのスカラー値を /event/detail/ 形式チェック + クエリパラメータ除去
    for ev in scraped:
        ev["ticket_url"] = _normalize_ticket_url(ev.get("ticket_url"))

    # フライヤー画像ダウンロード（image_url キーで旧ファイルをリネーム対応）
    print("フライヤー画像を処理中...")
    existing_map = {ev["id"]: ev for ev in existing_events}
    url_to_local = {
        ev["image_url"]: ev["local_image"]
        for ev in existing_events
        if ev.get("image_url") and ev.get("local_image")
    }
    download_flyers(scraped, existing_map, url_to_local)

    # フィールド保護: 既存値への後退を防ぐ
    # - open_time / start_time / end_time: None への後退はスクレイピング欠落によるバグ
    # - online_url: 一度取得したら更新しない（後から付与されるケースに対応）
    for ev in scraped:
        old = existing_map.get(ev["id"])
        if not old:
            continue
        for f in ("open_time", "start_time", "end_time"):
            if ev.get(f) is None and old.get(f) is not None:
                ev[f] = old[f]
        if old.get("online_url") is not None:
            ev["online_url"] = old["online_url"]

    # 差分検出
    print("差分を検出中...")
    final_events = diff_and_update(scraped, existing_events)

    # 除外フラグの適用（KV APIから最新の除外リストを取得して反映）
    excluded_ids = fetch_excluded_events()
    if excluded_ids is not None:
        for ev in final_events:
            if ev["id"] in excluded_ids:
                ev["excluded"] = True
            elif ev.get("excluded"):
                ev.pop("excluded", None)  # 除外解除された場合はフラグを削除
        excl_count = sum(1 for e in final_events if e.get("excluded"))
        if excl_count:
            print(f"除外フラグ適用: {excl_count} 件")
    else:
        excl_count = sum(1 for e in final_events if e.get("excluded"))
        if excl_count:
            print(f"除外フラグ維持: {excl_count} 件（API取得失敗のため既存値を保持）")

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

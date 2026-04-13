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
import urllib.request
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
                "open_time", "start_time", "end_time", "venue"]

# 公演日当日のみチェックするフィールド
# 当日券はサイトから購入不可になるため ticket_url 等が変動するが通知対象外とする
WATCH_FIELDS_TODAY = ["members"]


def now_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


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
    events = data.get("events", [])
    # ticket_urls（旧スキーマ）→ ticket_url（新スキーマ）へのマイグレーション
    for ev in events:
        if "ticket_urls" in ev and "ticket_url" not in ev:
            urls = ev.pop("ticket_urls")
            ev["ticket_url"] = urls[0] if urls else None
    return events


def build_event_from_profile(p: dict) -> dict:
    """プロフィール取得データをイベントレコードに変換する。
    劇場スケジュールが取得できない会場の公演に備え、プロフィールから取れる値はここで設定する。
    劇場スケジュールが取得できた場合は _patch_from_theater で上書きされる。
    image_url はプロフィールページからのみ取得する。
    """
    return {
        "id": make_event_id(p["talent_id"], p["date"], p["title"]),
        "talent_id": p["talent_id"],
        "talent_name": p["talent_name"],
        "title": p["title"],
        "date": p["date"],
        "open_time": None,
        "start_time": p.get("start_time"),   # 劇場スケジュール取得時は上書きされる
        "end_time": None,
        "members": p.get("members", ""),     # 劇場スケジュール取得時は上書きされる
        "venue": p.get("venue"),
        "place": p.get("place"),
        "image_url": p.get("image_url"),     # プロフィールページからのみ取得
        "ticket_urls": p.get("ticket_urls", []),  # 優先ルール解決まで保持
        "ticket_url": None,                        # 解決後に設定される
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
    """劇場データでイベントフィールドを上書きする。
    時刻・出演者・料金・チケットURLは劇場スケジュールが正とするため、
    劇場データが存在する場合は既存値に関わらず上書きする。
    """
    if te.get("open_time") is not None:
        ev["open_time"] = te["open_time"]
    if te.get("start_time") is not None:
        ev["start_time"] = te["start_time"]
    if te.get("end_time") is not None:
        ev["end_time"] = te["end_time"]
    if te.get("members"):
        ev["members"] = te["members"]
    # 劇場チケットURLを記録（優先ルール解決時に使用）
    theater_urls = te.get("ticket_urls", [])
    if theater_urls:
        ev["theater_ticket_url"] = theater_urls[0]
    if te.get("online_url") is not None:
        ev["online_url"] = te["online_url"]
    if te.get("price") is not None:
        ev["price"] = te["price"]
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
        "members": te.get("members", ""),
        "venue": te.get("venue"),
        "place": te.get("place"),
        "image_url": None,
        "ticket_url": te.get("ticket_urls", [None])[0],  # 劇場のみの公演は即解決
        "online_url": te.get("online_url"),
        "price": te.get("price"),
        "sources": [te["source"]],
    }


def download_flyers(events: list[dict], existing_map: dict[str, dict]) -> None:
    """
    フライヤー画像をローカルに保存する。
    - 新規イベント: image_url があればダウンロード
    - 既存イベント: image_url が変わっていたら再ダウンロードして上書き
    - local_image フィールドに docs/ からの相対パスを設定する
    """
    FLIERS_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = updated = skipped = 0

    for ev in events:
        url = ev.get("image_url")
        if not url:
            ev["local_image"] = existing_map.get(ev["id"], {}).get("local_image")
            continue

        old = existing_map.get(ev["id"], {})
        old_url = old.get("image_url")
        old_local = old.get("local_image")

        # URL が変わっていなくてローカルファイルが存在するならスキップ
        if url == old_url and old_local:
            local_path = BASE_DIR / "docs" / old_local
            if local_path.exists():
                ev["local_image"] = old_local
                skipped += 1
                continue

        # 拡張子を URL から推定（なければ .jpg）
        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        filename = f"{ev['id']}{suffix}"
        save_path = FLIERS_DIR / filename

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                save_path.write_bytes(resp.read())
            rel = f"fliers/{filename}"
            ev["local_image"] = rel
            if url == old_url:
                skipped += 1  # ファイルが消えていたので再取得
            else:
                updated += 1 if old_url else 0
                downloaded += 1 if not old_url else 0
        except Exception as e:
            print(f"  警告: フライヤー取得失敗 ({ev['title'][:20]}): {e}")
            ev["local_image"] = old_local  # 失敗時は旧パスを維持

    print(f"フライヤー: 新規 {downloaded} 件、更新 {updated} 件、スキップ {skipped} 件")


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

    # 除外タイトルフィルタ（部分一致）
    exclude_titles: list[str] = config.get("exclude_titles", [])
    if exclude_titles:
        before = len(scraped)
        scraped = [
            ev for ev in scraped
            if not any(kw in ev["title"] for kw in exclude_titles)
        ]
        print(f"除外フィルタ適用: {before - len(scraped)} 件除外 → {len(scraped)} 件")

    # チケットURL優先ルール解決
    # 1. 劇場スケジュールのURL（/event/detail/ パスのみ）があればそれを使用
    # 2. プロフィールのURLのうち /event/detail/ パスのものを先頭から採用
    # 3. いずれもなければ None
    # クエリパラメータはすべて除去する
    for ev in scraped:
        theater_url = _normalize_ticket_url(ev.pop("theater_ticket_url", None))
        if theater_url:
            ev["ticket_url"] = theater_url
        else:
            profile_urls = ev.pop("ticket_urls", None) or []
            ev["ticket_url"] = next(
                (u for u in (_normalize_ticket_url(u) for u in profile_urls) if u),
                None,
            )
        ev.pop("ticket_urls", None)

    # フライヤー画像ダウンロード（URL変更時は再取得）
    print("フライヤー画像を処理中...")
    existing_map = {ev["id"]: ev for ev in existing_events}
    download_flyers(scraped, existing_map)

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

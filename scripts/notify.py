"""
新規・更新イベントをGmailで通知するスクリプト。
送信後、対象イベントの status を "notified" にリセットし events.json を更新する。
"""

import json
import os
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
EVENTS_PATH = BASE_DIR / "data" / "events.json"
CONFIG_PATH = BASE_DIR / "data" / "config.json"

JST = timezone(timedelta(hours=9))

load_dotenv(BASE_DIR / ".env")

MAIL_USER = os.environ["MAIL_USER"]
MAIL_PASS = os.environ["MAIL_PASS"]
MAIL_TO = os.environ["MAIL_TO"]


def now_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def format_date(iso_date: str) -> str:
    """2026-04-19 → 2026年4月19日(土)"""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        weekdays = "月火水木金土日"
        return f"{dt.year}年{dt.month}月{dt.day}日({weekdays[dt.weekday()]})"
    except Exception:
        return iso_date


def format_price(price: dict | None) -> str:
    if not price:
        return "—"
    parts = []
    if "advance" in price:
        parts.append(f"前売 ¥{price['advance']:,}")
    if "door" in price:
        parts.append(f"当日 ¥{price['door']:,}")
    if "online" in price:
        parts.append(f"配信 ¥{price['online']:,}")
    return " / ".join(parts) if parts else "—"


def render_diff_rows(diff: dict | None) -> str:
    if not diff:
        return ""
    label_map = {
        "members": "出演者",
        "image_url": "フライヤー",
        "ticket_url": "チケットURL",
        "online_url": "配信URL",
        "price": "料金",
        "open_time": "開場時刻",
        "start_time": "開演時刻",
        "end_time": "終演時刻",
        "venue": "会場",
        "notice": "お知らせ",
    }
    labels = [label_map.get(f, f) for f in diff if f in label_map]
    if not labels:
        return ""
    items = "".join(
        f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;'
        f'background:#eaf3fb;border-radius:3px;font-size:12px;color:#2980b9">{label}</span>'
        for label in labels
    )
    return (
        f'<div style="margin-top:8px;font-size:12px;color:#666">変更項目: {items}</div>'
    )



def build_event_card(ev: dict) -> str:
    status = ev.get("status", "")
    if status == "new":
        badge = '<span style="background:#27ae60;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:bold;margin-right:8px">NEW</span>'
    else:
        badge = '<span style="background:#2980b9;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:bold;margin-right:8px">UPDATED</span>'

    date_str = format_date(ev.get("date", ""))
    times = []
    if ev.get("open_time"):
        times.append(f"開場 {ev['open_time']}")
    if ev.get("start_time"):
        times.append(f"開演 {ev['start_time']}")
    if ev.get("end_time"):
        times.append(f"終演 {ev['end_time']}")
    time_str = " | ".join(times) if times else "—"

    members_str = ev.get("members") or "—"
    venue_str = ev.get("venue") or "—"
    price_str = format_price(ev.get("price"))

    ticket_btn = ""
    if ev.get("ticket_url"):
        ticket_btn += (
            f'<a href="{ev["ticket_url"]}" style="display:inline-block;margin-top:8px;'
            f'margin-right:8px;padding:6px 14px;background:#e74c3c;color:#fff;'
            f'text-decoration:none;border-radius:4px;font-size:13px">チケット購入</a>'
        )
    if ev.get("online_url"):
        ticket_btn += (
            f'<a href="{ev["online_url"]}" style="display:inline-block;margin-top:8px;'
            f'padding:6px 14px;background:#8e44ad;color:#fff;'
            f'text-decoration:none;border-radius:4px;font-size:13px">配信チケット</a>'
        )

    flyer_img = ""
    if ev.get("image_url"):
        flyer_img = (
            f'<div style="margin-top:8px">'
            f'<img src="{ev["image_url"]}" alt="フライヤー" style="max-width:200px;border-radius:4px">'
            f'</div>'
        )

    diff_html = render_diff_rows(ev.get("diff"))

    return f"""
<div style="border:1px solid #ddd;border-radius:6px;padding:16px;margin-bottom:16px;background:#fafafa">
  <div style="margin-bottom:8px">{badge}<strong style="font-size:15px">{ev.get("title","")}</strong></div>
  <table style="border-collapse:collapse;font-size:14px">
    <tr><td style="padding:2px 8px;color:#666;white-space:nowrap">日時</td><td style="padding:2px 8px">{date_str} {time_str}</td></tr>
    <tr><td style="padding:2px 8px;color:#666;white-space:nowrap">会場</td><td style="padding:2px 8px">{venue_str}</td></tr>
    <tr><td style="padding:2px 8px;color:#666;white-space:nowrap">出演者</td><td style="padding:2px 8px">{members_str}</td></tr>
    <tr><td style="padding:2px 8px;color:#666;white-space:nowrap">料金</td><td style="padding:2px 8px">{price_str}</td></tr>
  </table>
  {diff_html}
  {ticket_btn}
  {flyer_img}
</div>"""


def build_html(talent_name: str, events: list[dict]) -> str:
    cards = "".join(build_event_card(ev) for ev in events)
    new_count = sum(1 for e in events if e.get("status") == "new")
    upd_count = sum(1 for e in events if e.get("status") == "updated")
    summary = f"新規 {new_count} 件 / 更新 {upd_count} 件"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Hiragino Sans',sans-serif;color:#333;max-width:600px;margin:0 auto;padding:16px">
  <h2 style="border-bottom:2px solid #e74c3c;padding-bottom:8px">{talent_name} の公演情報</h2>
  <p style="margin-top:4px;margin-bottom:12px;font-size:13px">
    <a href="https://fanaby-event.pages.dev/" style="color:#e74c3c;text-decoration:none">▶ fanaby-event を開く</a>
  </p>
  <p style="color:#666;font-size:13px">{summary}</p>
  {cards}
  <p style="color:#aaa;font-size:11px;margin-top:32px">fanaby-event 自動通知</p>
</body>
</html>"""


def send_mail(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = MAIL_USER
    msg["To"] = MAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(MAIL_USER, MAIL_PASS)
        smtp.sendmail(MAIL_USER, MAIL_TO, msg.as_string())


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    events = data.get("events", [])
    ts = now_jst()

    # 通知対象: new または updated（除外済みイベントは除く）
    notify_targets = [
        e for e in events
        if e.get("status") in ("new", "updated") and not e.get("excluded")
    ]
    if not notify_targets:
        print("通知対象なし")
        return

    # 芸人別にグルーピング（複数芸人が出演する公演は各芸人の通知に含める）
    talent_map: dict[str, list[dict]] = {}
    for ev in notify_targets:
        for tid in ev.get("talents", {}).keys():
            talent_map.setdefault(tid, []).append(ev)

    sent_ids: set[str] = set()
    for talent in config["talents"]:
        tid = talent["id"]
        if tid not in talent_map:
            continue
        talent_events = sorted(talent_map[tid], key=lambda e: e.get("date", ""))
        subject = f"【公演情報】{talent['name']} — 新規/更新 {len(talent_events)} 件"
        html = build_html(talent["name"], talent_events)
        try:
            send_mail(subject, html)
            print(f"送信完了: {talent['name']} ({len(talent_events)} 件)")
            for ev in talent_events:
                sent_ids.add(ev["id"])
        except Exception as e:
            print(f"送信失敗: {talent['name']}: {e}")

    # 送信済みのステータスをリセット
    for ev in events:
        if ev["id"] in sent_ids:
            ev["status"] = "notified"
            ev["notified_at"] = ts
            ev.pop("diff", None)

    data["updated_at"] = ts
    EVENTS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"notify 完了: {len(sent_ids)} 件のステータスをリセット")


if __name__ == "__main__":
    main()

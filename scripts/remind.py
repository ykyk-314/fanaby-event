"""
ticket_deadlines.json を参照してリマインドメールをユーザー別に送信する。

通知条件（JST 9:03 実行を想定）:
  1. 先行受付開始翌日朝: type=lottery かつ start が昨日
  2. 受付終了1〜2時間前: end まで 7200 秒以内（先行・一般共通）
  3. 一般販売開始1時間前: type=general かつ start まで 3600 秒以内

通知先: /api/remind-list から取得したユーザー別メールアドレス（MAIL_TO 廃止）
"""

import json
import os
import smtplib
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR       = Path(__file__).parent.parent
DEADLINES_PATH = BASE_DIR / "data" / "ticket_deadlines.json"

JST = timezone(timedelta(hours=9))

load_dotenv(BASE_DIR / ".env")

MAIL_USER         = os.environ["MAIL_USER"]
MAIL_PASS         = os.environ["MAIL_PASS"]
REMIND_API_URL    = os.environ.get("REMIND_API_URL", "").rstrip("/")
REMIND_API_SECRET = os.environ.get("REMIND_API_SECRET", "")


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y/%m/%d %H:%M").replace(tzinfo=JST)


def send_mail(subject: str, html: str, to_addr: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = MAIL_USER
    msg["To"]      = to_addr
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(MAIL_USER, MAIL_PASS)
        smtp.sendmail(MAIL_USER, to_addr, msg.as_string())


def build_html(items: list[dict]) -> str:
    cards = ""
    for item in items:
        cards += f"""
<div style="border:1px solid #ddd;border-radius:6px;padding:14px;margin-bottom:12px;background:#fafafa">
  <div style="font-size:12px;font-weight:bold;color:#e67e22;margin-bottom:6px">{item['trigger']}</div>
  <div style="font-size:15px;font-weight:bold">{item['event_title']}</div>
  <div style="font-size:13px;color:#555;margin-top:4px">{item['ticket_name']}</div>
  <div style="font-size:12px;color:#888;margin-top:4px">
    受付期間: {item['start']} 〜 {item['end']}
  </div>
  <a href="{item['url']}"
     style="display:inline-block;margin-top:8px;padding:6px 14px;background:#e74c3c;
            color:#fff;text-decoration:none;border-radius:4px;font-size:13px">
    チケットページ
  </a>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Hiragino Sans',sans-serif;color:#333;max-width:600px;margin:0 auto;padding:16px">
  <h2 style="border-bottom:2px solid #e67e22;padding-bottom:8px">チケットリマインド</h2>
  <p style="margin-bottom:12px;font-size:13px">
    <a href="https://fanaby-event.pages.dev/" style="color:#e74c3c;text-decoration:none">
      ▶ fanaby-event を開く
    </a>
  </p>
  {cards}
  <p style="color:#aaa;font-size:11px;margin-top:32px">fanaby-event 自動通知</p>
</body>
</html>"""


def get_remind_recipients() -> dict[str, set[str]]:
    """
    /api/remind-list から remind:true のイベントとユーザーメールの対応を取得する。
    戻り値: { eventId: {email1, email2, ...} }
    email が解決できないエントリ（email: null）はスキップする。
    """
    if not REMIND_API_URL or not REMIND_API_SECRET:
        print("REMIND_API_URL / REMIND_API_SECRET 未設定 — 通知先取得をスキップ")
        return {}
    try:
        req = urllib.request.Request(
            f"{REMIND_API_URL}/api/remind-list",
            headers={"Authorization": f"Bearer {REMIND_API_SECRET}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            remind_list = json.loads(resp.read().decode("utf-8"))
        recipients: dict[str, set[str]] = {}
        for item in remind_list:
            event_id = item.get("eventId")
            email    = item.get("email")
            if event_id and email:
                recipients.setdefault(event_id, set()).add(email)
        print(f"通知先取得: {len(remind_list)} エントリ / {len(recipients)} 公演")
        return recipients
    except Exception as e:
        print(f"通知先取得エラー: {e}")
        return {}


def main():
    if not DEADLINES_PATH.exists():
        print("ticket_deadlines.json が存在しません")
        return

    _dl_content = DEADLINES_PATH.read_text(encoding="utf-8").strip()
    if not _dl_content:
        print("ticket_deadlines.json が空です")
        return
    deadlines = json.loads(_dl_content)
    now       = datetime.now(JST)
    yesterday = (now - timedelta(days=1)).date()

    # ユーザー別リマインド対象: { email: [remind_item, ...] }
    recipients  = get_remind_recipients()
    per_user: dict[str, list[dict]] = {}

    for event_id, ev in deadlines.get("events", {}).items():
        emails = recipients.get(event_id, set())
        if not emails:
            continue

        for ticket in ev.get("tickets", []):
            try:
                start_dt = parse_dt(ticket["start"])
                end_dt   = parse_dt(ticket["end"])
            except (KeyError, ValueError):
                continue

            delta_start = (start_dt - now).total_seconds()
            delta_end   = (end_dt   - now).total_seconds()

            if delta_end <= 0:
                continue

            item = None

            # 1. 先行受付開始翌日朝通知（start が昨日）
            if ticket["type"] == "lottery" and start_dt.date() == yesterday:
                item = {
                    "trigger":     "先行受付が開始しました（昨日開始）",
                    "event_title": ev["title"],
                    "ticket_name": ticket["name"],
                    "start":       ticket["start"],
                    "end":         ticket["end"],
                    "url":         ticket["url"],
                }

            # 2. 受付終了 1〜2時間前（先行・一般共通）
            elif 0 < delta_end <= 7200:
                remain_min = int(delta_end // 60)
                item = {
                    "trigger":     f"受付終了まで約 {remain_min} 分",
                    "event_title": ev["title"],
                    "ticket_name": ticket["name"],
                    "start":       ticket["start"],
                    "end":         ticket["end"],
                    "url":         ticket["url"],
                }

            # 3. 一般販売開始 1時間前
            elif ticket["type"] == "general" and 0 < delta_start <= 3600:
                remain_min = int(delta_start // 60)
                item = {
                    "trigger":     f"一般販売開始まで約 {remain_min} 分",
                    "event_title": ev["title"],
                    "ticket_name": ticket["name"],
                    "start":       ticket["start"],
                    "end":         ticket["end"],
                    "url":         ticket["url"],
                }

            if item:
                for email in emails:
                    per_user.setdefault(email, []).append(item)

    if not per_user:
        print("通知対象なし")
        return

    for email, items in per_user.items():
        html    = build_html(items)
        subject = f"【チケットリマインド】{len(items)} 件"
        try:
            send_mail(subject, html, email)
            print(f"送信完了: {email} ({len(items)} 件)")
        except Exception as e:
            print(f"送信失敗: {email}: {e}")


if __name__ == "__main__":
    main()

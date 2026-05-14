"""
新規登録申請を管理者にメールで通知するスクリプト。
GitHub Actions の notify-register.yml から repository_dispatch 経由で起動される。
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

MAIL_USER = os.environ["MAIL_USER"]
MAIL_PASS = os.environ["MAIL_PASS"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "").rstrip("/")
REQ_TOKEN = os.environ["REQ_TOKEN"]
REQ_EMAIL = os.environ["REQ_EMAIL"]


def build_html() -> str:
    approve_url = f"{SITE_ORIGIN}/api/register-approve?token={REQ_TOKEN}"
    reject_url = f"{SITE_ORIGIN}/api/register-reject?token={REQ_TOKEN}"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Hiragino Sans',sans-serif;color:#333;max-width:600px;margin:0 auto;padding:16px">
  <h2 style="border-bottom:2px solid #1a1a2e;padding-bottom:8px">新規登録申請が届きました</h2>
  <p style="font-size:14px">以下のメールアドレスから登録申請が届いています。</p>
  <table style="border-collapse:collapse;font-size:14px;margin-bottom:24px">
    <tr>
      <td style="padding:6px 12px;color:#666;white-space:nowrap">申請メール</td>
      <td style="padding:6px 12px"><strong>{REQ_EMAIL}</strong></td>
    </tr>
  </table>
  <p style="font-size:14px">承認するとこのメールアドレスが Cloudflare Access に追加され、サービスにログインできるようになります。</p>
  <div style="margin-top:24px">
    <a href="{approve_url}"
       style="display:inline-block;padding:10px 24px;background:#27ae60;color:#fff;text-decoration:none;border-radius:4px;font-size:14px;margin-right:12px">
      ✓ 承認する
    </a>
    <a href="{reject_url}"
       style="display:inline-block;padding:10px 24px;background:#e74c3c;color:#fff;text-decoration:none;border-radius:4px;font-size:14px">
      ✗ 拒否する
    </a>
  </div>
  <p style="color:#aaa;font-size:11px;margin-top:32px">
    このリンクの有効期限は 24 時間です。<br>
    fanaby-event 自動通知
  </p>
</body>
</html>"""


def send_mail() -> None:
    subject = f"【fanaby-event 登録申請】{REQ_EMAIL}"
    html = build_html()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = MAIL_USER
    msg["To"] = ADMIN_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(MAIL_USER, MAIL_PASS)
        smtp.sendmail(MAIL_USER, ADMIN_EMAIL, msg.as_string())


if __name__ == "__main__":
    print(f"申請通知メール送信: {REQ_EMAIL} → {ADMIN_EMAIL}")
    send_mail()
    print("送信完了")

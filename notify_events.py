import os
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

SHEET_URL = os.getenv('GSHEET_URL')
CREDS_PATH = 'credentials.json'
MAIL_USER = os.getenv('MAIL_USER')
MAIL_PASS = os.getenv('MAIL_PASS')
MAIL_TO = os.getenv('MAIL_TO')

PAGES_BASE_URL = "https://ykyk-314.github.io/fanaby-event"

# スプレッドシートから全記録データを取得
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
gc = gspread.authorize(creds)
sh = gc.open_by_url(SHEET_URL)

new_records = []

# 各タレントごとシートからIsUpdateだけ抽出
for worksheet in sh.worksheets():
    sheet_name = worksheet.title
    records = worksheet.get_all_records()
    if not records:
        continue
    df = pd.DataFrame(records)
    print(f"### Processing sheet: {sheet_name} with {len(df)} records")
    if "IsUpdate" not in df.columns or df["IsUpdate"].isnull().all():
        continue

    df_notify = df[df["IsUpdate"].astype(str).isin(["1", "2"])].copy()
    print(f"### Found {len(df_notify)} records to notify in {sheet_name}")
    if not df_notify.empty:
        # タレント名取得
        talent_name = df_notify["TalentName"].iloc[0] if "TalentName" in df_notify.columns else sheet_name
        new_records.append((talent_name, df_notify))

# 通知メールHTMLの生成
def build_event_html(row, base_url):
    if str(row["IsUpdate"]) == "1":
        tag = "追加"
        tag_color = "#fa8800"
        tag_bg = "#fff5e6"
    else:
        tag = "更新"
        tag_color = "#0a72b6"
        tag_bg = "#eaf5fa"
    html = (
        f"<div style='border:1px solid #e0e0e0; border-radius:8px; padding:16px; margin:18px 0; background:#fafbfc;'>"
        f"<span style='display:inline-block; font-weight:bold; color:{tag_color}; background:{tag_bg}; border-radius:4px; padding:2px 10px; margin-bottom:6px;'>{tag}</span><br>"
        f"<span style='font-size:120%;font-weight:bold;color:#222;'>{row['EventTitle']}</span><br>"
        f"<span style='color:#222;'><b>日付：</b>{row['EventDate']} {row['EventStartTime']}</span><br>"
        f"<span style='color:#222;'><b>会場：</b>{row['TheaterVenue']}</span><br>"
        f"<span style='color:#222;'><b>出演者：</b>{row['EventMembers']}</span><br>"
    )
    # ボタン
    if row.get("TicketLink"):
        html += (
            f"<a href='{row['TicketLink']}' target='_blank' "
            "style='display:inline-block;margin:10px 0 6px 0;padding:7px 20px;font-weight:bold;"
            "border-radius:6px; color:#fff;background:#0a72b6;text-decoration:none;"
            "border:1px solid #0a72b6;box-shadow:0 1px 2px #ddd;'>"
            "チケット詳細</a><br>"
        )
    # 画像
    if row.get("AppImage") and row["AppImage"] not in ("-", ""):
        img_url = f"{base_url}{row['AppImage']}"
        html += f"<img src='{img_url}' width='320' style='margin:12px 0 6px 0;border-radius:6px;'><br>"
    html += "</div>"
    return html

# メール送信（HTMLメール・画像埋め込み・追加/更新タグ）
if new_records:
    for talent_name, records in new_records:
        msg_body = ""
        print(f"### Sending notification for {talent_name} with {len(records)} records")

    for _, row in records.iterrows():
        msg_body += build_event_html(row, PAGES_BASE_URL)

        subject = f"[Fanaby] {talent_name}：スケジュール追加・更新のお知らせ"
        # HTMLメールとして送信
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = formataddr(('Fanaby.com', MAIL_USER))
        msg['To'] = MAIL_TO
        msg.attach(MIMEText(msg_body, "html"))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(MAIL_USER, MAIL_PASS)
            smtp.sendmail(MAIL_USER, MAIL_TO, msg.as_string())
        print(f"通知メールを送信しました: {talent_name}")
else:
    print("新規・更新分なし：通知メールは送信しません")

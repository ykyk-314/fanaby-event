import os
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

# 各タレントごとシートからIsUpdate==1/2だけ抽出
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

# メール送信（HTMLメール・画像埋め込み・追加/更新タグ）
if new_records:
    for talent_name, records in new_records:
        msg_body = ""
        print(f"### Sending notification for {talent_name} with {len(records)} records")
        for _, row in records.iterrows():
            tag = "追加" if str(row["IsUpdate"]) == "1" else "更新"
            msg_body += (
                f"<b>[{tag}]</b> "
                f"【{row['EventTitle']}】<br>"
                f"日付: {row['EventDate']} {row['EventStartTime']}<br>"
                f"会場: {row['TheaterVenue']}<br>"
                f"出演者: {row['EventMembers']}<br>"
                f"リンク: <a href='{row['TicketLink']}'>{row['TicketLink']}</a><br>"
            )
            # 画像
            if row.get("AppImage") and row["AppImage"] not in ("-", ""):
                img_url = f"{PAGES_BASE_URL}{row['AppImage']}"
                msg_body += f"<img src='{img_url}' width='320'><br>"
            msg_body += "<br>"

        subject = f"[Fanaby] {talent_name}：スケジュール追加・更新のお知らせ"
        # HTMLメールとして送信
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = MAIL_USER
        msg['To'] = MAIL_TO
        msg.attach(MIMEText(msg_body, "html"))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(MAIL_USER, MAIL_PASS)
            smtp.sendmail(MAIL_USER, MAIL_TO, msg.as_string())
        print(f"通知メールを送信しました: {talent_name}")
else:
    print("新規・更新分なし：通知メールは送信しません")

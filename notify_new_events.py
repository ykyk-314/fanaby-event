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

key_cols = ["TalentID", "EventTitle", "EventDate", "EventStartTime", "OriginImage"]

# 1. 今回取得データ
dtype_dict = {col: str for col in key_cols}
df_new = pd.read_csv('talent_tickets.csv', encoding='utf-8-sig', dtype=dtype_dict)

# 2. Google Sheets（全記録）から既存データ取得
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
gc = gspread.authorize(creds)
sh = gc.open_by_url(SHEET_URL)

new_records = []

for talent_name, group in df_new.groupby("TalentName"):
    sheet_name = talent_name[:99]
    try:
        worksheet = sh.worksheet(sheet_name)
        existing = worksheet.get_all_values()
        if existing:
            df_exist = pd.DataFrame(existing[1:], columns=existing[0])
        else:
            df_exist = pd.DataFrame(columns=group.columns)
    except gspread.exceptions.WorksheetNotFound:
        df_exist = pd.DataFrame(columns=group.columns)
    # 差分検知：新規または内容変更
    merge = pd.merge(group, df_exist, how="left", on=key_cols, indicator=True, suffixes=('', '_old'))
    added_or_updated = merge[merge['_merge'] == 'left_only']
    if not added_or_updated.empty:
        new_records.append((talent_name, added_or_updated[group.columns]))
        
# 3. メール送信（HTMLメール・画像埋め込み）
if new_records:
    for talent_name, records in new_records:
        msg_body = ""
        for _, row in records.iterrows():
            msg_body += (
                f"【{row['EventTitle']}】<br>"
                f"日付: {row['EventDate']} {row['EventStartTime']}<br>"
                f"会場: {row['TheaterVenue']}<br>"
                f"出演者: {row['EventMembers']}<br>"
                f"リンク: <a href='{row['TicketLink']}'>{row['TicketLink']}</a><br>"
            )
            # ★ 画像カラムがあればimgタグで表示
            if row.get("Image") and row["Image"] not in ("-", ""):
                img_url = f"{PAGES_BASE_URL}{row['Image']}"
                msg_body += f"<img src='{img_url}' width='320'><br>"
            msg_body += "<br>"

        subject = f"[Fanaby] {talent_name}で新しいスケジュール追加/更新"
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

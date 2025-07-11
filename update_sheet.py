import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os

SHEET_URL = os.getenv('GSHEET_URL')
CREDS_PATH = 'credentials.json'

# 1. CSV読み込み＆重複除外
df = pd.read_csv('talent_tickets.csv', encoding='utf-8-sig')
df.drop_duplicates(
    subset=["TalentID", "EventTitle", "EventDate", "EventStartTime"],
    keep="first", inplace=True
)

# 2. Google認証
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
gc = gspread.authorize(creds)

# 3. スプレッドシート取得
sh = gc.open_by_url(SHEET_URL)

# 4. 芸人名ごとにシート分割＆書き込み
for talent_name, group in df.groupby("TalentName"):
    sheet_name = talent_name[:99]  # シート名は最大99文字
    try:
        worksheet = sh.worksheet(sheet_name)
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="100", cols=str(len(group.columns)))
    worksheet.update([group.columns.values.tolist()] + group.values.tolist())

print("Googleスプレッドシートに芸人ごとで分割記録しました。")

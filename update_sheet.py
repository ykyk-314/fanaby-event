import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os

# スプレッドシートのURLまたはID
SHEET_URL = os.getenv('GSHEET_URL')  # シークレット管理を推奨

# サービスアカウントjsonのパス
CREDS_PATH = 'credentials.json'  # ActionsではSecretsから生成/復元して使う

# 1. データのロード
df = pd.read_csv('talent_tickets.csv', encoding='utf-8-sig')

# 2. Google認証
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
gc = gspread.authorize(creds)

# 3. スプレッドシート取得
sh = gc.open_by_url(SHEET_URL)
worksheet = sh.get_worksheet(0)  # 一番左のシートを利用。名前で取得するなら worksheet = sh.worksheet('シート1')

# 4. シート全体クリアして最新データを上書き
worksheet.clear()
worksheet.update([df.columns.values.tolist()] + df.values.tolist())

print("シートにアップロード完了")

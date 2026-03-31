import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os

SHEET_URL = os.getenv('GSHEET_URL')
CREDS_PATH = 'credentials.json'

# 今回取得データ
df_new = pd.read_csv('talent_tickets.csv', encoding='utf-8-sig')

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
gc = gspread.authorize(creds)
sh = gc.open_by_url(SHEET_URL)

# 公演ユニークキー
key_cols = ["TalentID", "EventTitle", "EventDate", "EventStartTime"]

for talent_name, group in df_new.groupby("TalentName"):
    sheet_name = talent_name[:99]
    try:
        worksheet = sh.worksheet(sheet_name)
        # 既存データを取得
        existing = worksheet.get_all_values()
        if existing:
            df_exist = pd.DataFrame(existing[1:], columns=existing[0])
        else:
            df_exist = pd.DataFrame(columns=group.columns)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="100", cols=str(len(group.columns)))
        df_exist = pd.DataFrame(columns=group.columns)
    # ここで「既存・新規」両方のkey_colsをstr型に統一
    for col in key_cols:
        if col in group.columns:
            group[col] = group[col].astype(str)
        if col in df_exist.columns:
            df_exist[col] = df_exist[col].astype(str)
    # 既存＋新規を結合し、ユニークに
    df_all = pd.concat([df_exist, group], ignore_index=True)
    df_all.drop_duplicates(subset=key_cols, keep="first", inplace=True)
    # シート全体を新規で上書き（シート容量気になる場合はここで古いデータを除外も可能）
    worksheet.clear()
    worksheet.update([df_all.columns.values.tolist()] + df_all.values.tolist())

print("全記録用としてスプレッドシートに追記・重複排除しました。")

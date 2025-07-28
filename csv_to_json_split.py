import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

SHEET_URL = os.getenv('GSHEET_URL')
CREDS_PATH = 'credentials.json'
BASE_DIR = "docs/talents"   # 出力先
key_sort = ["EventDate", "EventStartTime", "EventTitle"]

# Google Sheets認証
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
gc = gspread.authorize(creds)
sh = gc.open_by_url(SHEET_URL)

# シート一覧を取得（タレントごと1シート運用を前提）
for worksheet in sh.worksheets():
    # シート名が空/ゴミの場合スキップ
    if worksheet.title.strip() == "":
        continue

    records = worksheet.get_all_records()
    if not records:
        continue
    df = pd.DataFrame(records)

    # タレントIDが存在する行のみ
    if "TalentID" not in df.columns or df["TalentID"].isnull().all():
        continue

    for talent_id, group in df.groupby("TalentID"):
        # ソート（安定化！）
        group = group.sort_values(key_sort, ascending=True, kind="mergesort")
        # 不要な列もここで除外可（必要に応じて）

        target_dir = os.path.join(BASE_DIR, str(talent_id))
        os.makedirs(target_dir, exist_ok=True)
        json_path = os.path.join(target_dir, "schedules.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(group.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
        print(f"書き出し: {json_path}")

print("全タレント分のschedules.jsonの生成が完了しました。")

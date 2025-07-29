import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os
import requests
import hashlib

load_dotenv()

SHEET_URL = os.getenv('GSHEET_URL')
CREDS_PATH = 'credentials.json'

# 公演ユニークキー
key_cols = ["TalentID", "EventTitle", "EventDate", "EventStartTime"]
# 内容差分判定カラム
diff_cols = ["EventMembers", "OriginImage", "TicketLink"]

def download_event_image(origin_url, talent_id, event_title, event_date):
    if not origin_url or origin_url == '-' or pd.isna(origin_url):
        return ""
    # ファイル名（安全かつユニークに）
    safe_title = "".join([c for c in event_title if c.isalnum() or c in " _-"]).rstrip()
    safe_date = event_date.replace('/', '-').replace(' ', '').replace(':','')
    file_hash = hashlib.md5(origin_url.encode()).hexdigest()[:8]
    file_name = f"{safe_date}_{safe_title}_{file_hash}.jpg"
    img_dir = f"docs/img/flier/{talent_id}"
    os.makedirs(img_dir, exist_ok=True)
    save_path = os.path.join(img_dir, file_name)
    if not os.path.exists(save_path):
        try:
            r = requests.get(origin_url, timeout=10)
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                print(f"Image saved: {save_path}")
            else:
                print(f"Failed to download image: {origin_url}")
        except Exception as e:
            print(f"Image download error: {e}")
            return ""
    return f"/img/flier/{talent_id}/{file_name}"

# 取得データ（重複除外）
df_new = pd.read_csv('temp_talent_events.csv', encoding='utf-8-sig', dtype=str).fillna("")
df_new = df_new.drop_duplicates(subset=key_cols, keep="first").reset_index(drop=True)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
gc = gspread.authorize(creds)
sh = gc.open_by_url(SHEET_URL)

for talent_name, group in df_new.groupby("TalentName"):
    sheet_name = talent_name[:99]
    try:
        worksheet = sh.worksheet(sheet_name)
        # 既存データを取得
        existing = worksheet.get_all_values()
        if existing:
            df_exist = pd.DataFrame(existing[1:], columns=existing[0])
        else:
            df_exist = pd.DataFrame(columns=group.columns.tolist() + ["AppImage", "IsUpdate"])
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="100", cols=str(len(group.columns)+2))
        df_exist = pd.DataFrame(columns=group.columns.tolist() + ["AppImage", "IsUpdate"])

    # 型統一
    for col in key_cols:
        if col in group.columns:
            group[col] = group[col].astype(str)
        if col in df_exist.columns:
            df_exist[col] = df_exist[col].astype(str)

    # キー列作成
    group["__key"] = group[key_cols].astype(str).agg("_".join, axis=1)
    df_exist["__key"] = df_exist[key_cols].astype(str).agg("_".join, axis=1)

    # マスタだけにある（過去分など/新規データになかった分＝古い）→上部へ
    df_only_exist = df_exist[~df_exist["__key"].isin(group["__key"])].copy()
    df_only_exist["IsUpdate"] = df_only_exist.get("IsUpdate", "")  # 維持

    # 新規取得分を判定（新しい分）
    rows = []
    for idx, row in group.iterrows():
        key = row["__key"]
        match = df_exist[df_exist["__key"] == key]
        row_out = row.to_dict()
        row_out["AppImage"] = ""
        # 新規
        if match.empty:
            row_out["IsUpdate"] = "1"
            if row_out.get("OriginImage", "") not in ("", "-"):
                row_out["AppImage"] = download_event_image(
                    row_out["OriginImage"], row_out["TalentID"], row_out["EventTitle"], row_out["EventDate"]
                )
        else:
            # 差分チェック
            changed = False
            for col in diff_cols:
                if str(row[col]) != str(match.iloc[0].get(col, "")):
                    changed = True
            row_out["IsUpdate"] = "2" if changed else ""
            prev_origin = match.iloc[0].get("OriginImage", "")
            prev_appimg = match.iloc[0].get("AppImage", "")
            if (
                (str(row_out.get("OriginImage", "")) != str(prev_origin))
                or (not prev_appimg)
                or (prev_appimg == "")
            ):
                row_out["AppImage"] = download_event_image(
                    row_out["OriginImage"], row_out["TalentID"], row_out["EventTitle"], row_out["EventDate"]
                )
            else:
                row_out["AppImage"] = prev_appimg
        rows.append(row_out)

    # 1. マスタだけにあった古い分
    # 2. 新規（今回取得した分、重複除外済み）
    # この順で連結してから書き込み（＝古いデータが上、新規が下に並ぶ）
    combined_rows = df_only_exist.to_dict(orient="records") + rows

    # __key列除去、カラム順序整形
    for row in combined_rows:
        if "__key" in row:
            del row["__key"]
    out_columns = list(group.columns.drop("__key")) + ["AppImage", "IsUpdate"]
    for row in combined_rows:
        for col in out_columns:
            if col not in row:
                row[col] = ""

    # シート全体を新規で上書き
    worksheet.clear()
    worksheet.update([out_columns] + [[str(row.get(col, "")) for col in out_columns] for row in combined_rows])

print("差分判定・重複除去・画像ダウンロードしてスプレッドシートを更新")

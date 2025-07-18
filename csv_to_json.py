import pandas as pd
import json
import os

# 入力CSVファイル
CSV_FILE = "talent_tickets.csv"
# 出力JSONファイル（docs配下がGitHub Pagesのdataディレクトリとして推奨）
JSON_FILE = "docs/data/talent_schedules.json"

# CSV読み込み
df = pd.read_csv(CSV_FILE, dtype=str).fillna("")

# 必要なら、カラム順序や不要カラムの調整（オプション）
# df = df[["TalentName", "TalentID", "EventTitle", ...]]  # 必要なカラムだけ指定

# JSON出力（utf-8, pretty print, 日本語対応）
os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
with open(JSON_FILE, "w", encoding="utf-8") as f:
    json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)

print(f"変換完了: {JSON_FILE}")

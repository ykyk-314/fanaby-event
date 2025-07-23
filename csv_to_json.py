import pandas as pd
import json
import os

CSV_FILE = "talent_tickets.csv"
BASE_DIR = "docs/talents"

# CSV読み込み
df = pd.read_csv(CSV_FILE, dtype=str).fillna("")

# タレントごとに分割
for talent_id, group in df.groupby("TalentID"):
    # ディレクトリ作成
    target_dir = os.path.join(BASE_DIR, str(talent_id))
    os.makedirs(target_dir, exist_ok=True)
    # JSONファイル出力
    json_path = os.path.join(target_dir, "schedules.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(group.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    print(f"書き出し: {json_path}")

print("全タレント分のschedules.jsonの生成が完了しました。")

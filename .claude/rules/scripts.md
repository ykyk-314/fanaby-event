---
paths: scripts/**/*.py
---

# scripts/ — Pythonスクリプト群

## データフロー（順序を守ること）
1. `scrape_profile.py` → `data/profile_events.json`（中間・gitignore）
2. `scrape_theater.py` → `data/theater_events.json`（中間・gitignore）
3. `merge.py` → `data/events.json` + `docs/fliers/`（DL）
4. `notify.py` → Gmail SMTP 送信
5. `build.py` → `docs/index.html`

## 注意事項
- Selenium は `webdriver-manager` 不使用。`webdriver.Chrome(options=options)` のみ
- プロフィールページの日付は M/D 形式（年なし）。`resolve_year()` で年を推定する
- `events.json` への書き込みは **差分マージ**（past events carry-over）。全上書き禁止
- イベントID: `SHA1("{talent_id}:{date}:{normalize_title(title)}")[:8]`
- 変更検知対象（`WATCH_FIELDS`）: `members / image_url / ticket_url / online_url / price / open_time / start_time / end_time / venue`
  - **公演日当日は `members` のみチェック**（ticket_url 等は当日券販売終了で変動するため）
- チケットURL優先順位: 劇場ページ > プロフィールページ先頭 > null
- 劇場の出演者 `members`: `<a>` タグを innerText に置換、他タグ除去したプレーンテキスト（文字列、配列でない）
- `status` 遷移ルール: `new` → `notified`（通知後）/ `notified` → `updated`（変更検知時）
  - 「変更なし」判定時は `updated` を `notified` にリセットする（古い diff の誤通知防止）

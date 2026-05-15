---
paths: scripts/**/*.py
---

# scripts/ — Python スクリプト群

## データフロー（実行順序）

### メインフロー（`main.yml` が JST 9:03 / 17:03 に実行）

```
1. scrape_profile_api.py  → data/profile_events.json（中間・gitignore）
2. scrape_theater_api.py  → data/theater_events.json（中間・gitignore）
3. merge.py               → data/events.json + docs/fliers/（DL）
4. notify.py              → Gmail SMTP 送信
5. build.py               → docs/index.html
```

### リマインドフロー（`remind-check.yml` が JST 8:45〜22:45 毎時実行）

```
1. scrape_ticket.py  → data/ticket_deadlines.json
2. build.py          → docs/index.html
3. remind.py         → Gmail SMTP 送信（ユーザー別）
```

### 登録通知フロー（`notify-register.yml` が `repository_dispatch` で起動）

```
notify_register.py  → Gmail SMTP 送信（管理者宛）
```

---

## スクリプト別仕様

### `scrape_profile_api.py`
- データソース: `https://feed-api.yoshimoto.co.jp/fany/tickets/v2?id={talent_id}`（芸人ごとに 1 リクエスト）
- 入力: `data/config.json` の `talents[]`
- 出力: `data/profile_events.json`
- 同一公演重複除去キー: `(date, title, start_time)`
- 環境変数: なし（API 認証不要）

### `scrape_theater_api.py`
- データソース: `https://feed-api.yoshimoto.co.jp/fany/theater/v1?theater={api_id}&venue=01&date_from=...&date_to=...`
- 期間: 実行日〜2ヶ月後の月末（全期間を 1 リクエストで取得）
- 入力: `data/config.json` の `theaters[]`（`api_id` が無い劇場はスキップ）
- 出力: `data/theater_events.json`
- 登録芸人が 1 人も出演していない公演は除外（`matched_talent_ids` が空なら捨てる）
- 環境変数: なし

### `merge.py`
- 入力: `data/theater_events.json`, `data/profile_events.json`, `data/events.json`, `data/config.json`
- 出力: `data/events.json`, `docs/fliers/*.{jpg,jpeg,png,gif,webp}`
- 環境変数: `REMIND_API_URL`, `REMIND_API_SECRET`（除外リスト取得用）

### `notify.py`
- 対象: `status in (new, updated)` かつ `excluded` でないイベント
- 送信後: `status` を `notified` にリセット
- SMTP: `smtp.gmail.com:465`（SMTP_SSL）
- 環境変数: `MAIL_USER`, `MAIL_PASS`, `MAIL_TO`

### `scrape_ticket.py`
- データソース: `https://ticket.fany.lol/search/event?...`（BeautifulSoup でスクレイピング）
- 入力: `data/events.json` + `/api/remind-list`（KV から remind:true の公演）
- 出力: `data/ticket_deadlines.json`
- 24 時間以内に更新済みの公演はスキップ
- 環境変数: `REMIND_API_URL`, `REMIND_API_SECRET`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`

### `remind.py`
- 入力: `data/ticket_deadlines.json`
- 通知先: `/api/remind-list` から取得したユーザー別メールアドレス
- 通知条件:
  - 先行抽選の受付開始翌日朝（`type=lottery` かつ `start` が昨日）
  - 受付終了 1〜2 時間前（`delta_end ≤ 7200 秒`）
  - 一般販売の受付開始 1 時間前（`type=general` かつ `delta_start ≤ 3600 秒`）
- 環境変数: `MAIL_USER`, `MAIL_PASS`, `REMIND_API_URL`, `REMIND_API_SECRET`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`

### `notify_register.py`
- 用途: 新規登録申請の管理者への通知（承認/拒否リンク付き）
- トリガー: `notify-register.yml` ワークフロー（`repository_dispatch` 経由）
- 環境変数: `MAIL_USER`, `MAIL_PASS`, `ADMIN_EMAIL`, `SITE_ORIGIN`, `REQ_TOKEN`, `REQ_EMAIL`

### `build.py`
- 入力: `data/events.json`, `data/ticket_deadlines.json`, `data/config.json`
- 出力: `docs/index.html`
- `docs/assets/style.css` / `docs/assets/script.js` は変更しない

---

## 実装規約

### イベント ID
```python
# 主キー: SHA1("{date}:{venue}:{start_time}")[:8]
# フォールバック（venue/start_time 不明時）: SHA1("{date}:{normalize_title(title)}")[:8]
# talent_id はハッシュ対象から除外（同一公演に複数芸人が出演するケースで 1 レコードに統合するため）
```
→ `scripts/merge.py` の `make_event_id()` を参照

### 変更検知フィールド（`WATCH_FIELDS`）
```python
["members", "image_url", "ticket_url", "price",
 "open_time", "start_time", "end_time", "venue", "notice"]
```
- **公演日当日は `members` のみチェック**（当日券販売終了で ticket_url 等が変動するため）

### ステータス遷移
```
new → notified（notify.py 送信後）
notified → updated（変更検知時）
updated → notified（変更なし判定時にリセット ← 古い diff の誤通知防止）
```

### events.json の書き込みルール
- **差分マージ必須**（past events carry-over）。全上書き禁止
- `open_time / start_time / end_time` の None 後退を防ぐ（既存値がある場合は上書きしない）
- `online_url` は一度取得したら更新しない
- `exclude_titles`（部分一致）に引っかかる公演は除外

### チケット URL の正規化
- `/event/detail/` パスのもののみ採用し、クエリパラメータを除去
- 優先順位: 劇場 API の `ticket_url` > プロフィール API の `ticket_urls` 先頭 > `null`

# feed-api 取得仕様

Selenium スクレイピングに代わり、`feed-api.yoshimoto.co.jp` から JSON を直接取得する方式。

---

## 1. プロフィール取得（`scrape_profile_api.py`）

### APIエンドポイント

```
GET https://feed-api.yoshimoto.co.jp/fany/tickets/v2?id={talent_id}
```

- `talent_id`：`config.json` の `talents[].id`
- 芸人ごとに1リクエスト
- 期間パラメータなし（APIが今後の公演を自動返却）

### フィールドマッピング

| APIキー | 出力フィールド | 変換処理 |
|---|---|---|
| `name` | `title` | strip のみ |
| `memberId` | ー | config の talent と対応（リクエスト時点で確定） |
| `date1` | `open_time` | ISO形式（`2026-06-10T21:00:00`）→ `HH:MM`。null なら `null` |
| `date2` | `date` / `start_time` | 日付部分 → `YYYY-MM-DD`、時刻部分 → `HH:MM` |
| `member` | `members` | `\r\n` → `\n` に正規化 |
| `isPermanentPlace=true` | `venue` | `placeType` の値をそのまま使用（例: "渋谷よしもと漫才劇場"） |
| `isPermanentPlace=true` | `place` | `city` の値（例: "渋谷"） |
| `isPermanentPlace=false` | `venue` | `place` の値をそのまま使用（例: "ワラケンスタジオ（東京都）"） |
| `isPermanentPlace=false` | `place` | `null` 固定 |
| `url1` | `image_url` | フライヤー画像URL。null なら `null` |
| `urlFullPath` | ー | `/event/detail/` 形式でないため取得しない |

### 出力スキーマ（`profile_events.json` の各要素）

```json
{
  "talent_id": "10708",
  "talent_name": "シンクロニシティ",
  "title": "公演タイトル",
  "date": "2026-06-10",
  "open_time": "21:00",
  "start_time": "21:15",
  "members": "出演者テキスト（改行区切り）",
  "place": "渋谷",
  "venue": "渋谷よしもと漫才劇場",
  "image_url": "https://feed-cdn.yoshimoto.co.jp/...",
  "ticket_urls": [],
  "source": "profile"
}
```

### 特記事項

- 同一公演が複数エントリになるケースは `(date, title, start_time)` キーで統合する（`ticket_urls` は現状常に空のため実質不要だが、既存スキーマとの互換で保持）
- `ticket_urls` は空固定。プロフィールAPIの `urlFullPath` は `/reception/` 形式であり、`merge.py` のチケットURL優先ルール（`/event/detail/` のみ採用）の対象外のため取得しない

---

## 2. 劇場スケジュール取得（`scrape_theater_api.py`）

### APIエンドポイント

```
GET https://feed-api.yoshimoto.co.jp/fany/theater/v1
    ?theater={api_id}&venue=01&date_from={YYYYMMDD}&date_to={YYYYMMDD}
```

- `api_id`：`config.json` の `theaters[].api_id`（例: `shibuya_manzaigekijyo`）
- `venue`：固定値 `01`
- `date_from`：実行日（今日）
- `date_to`：実行月から2ヶ月後の末日（例: 4/15実行 → 6/30）
- 劇場ごとに1リクエスト、全期間を一括取得（月ごとの切替不要）

### フィールドマッピング

| APIキー | 出力フィールド | 変換処理 |
|---|---|---|
| `name` | `title` | そのまま |
| `date` | `date` | `YYYY/MM/DD` → `YYYY-MM-DD` |
| `dateTime1` | `open_time` | そのまま（`HH:MM` 形式） |
| `dateTime2` | `start_time` | そのまま（`HH:MM` 形式） |
| `dateTime3` | `end_time` | そのまま（`HH:MM` 形式） |
| `memberHtml` | `members` | `<br>` → `\n`、`<a>` タグはテキストのみ残して除去、他タグ除去 |
| `memberHtml` | `matched_talent_ids` | `href` の `id=(\d+)` を抽出、`config.json` の talent_ids と照合 |
| `price1` | `price.advance` | `¥1,300` → `1300`（数字以外を除去して int 変換）。null なら省略 |
| `price2` | `price.door` | 同上 |
| `price3` | `price.online` | 同上 |
| `url1` | `ticket_url` | `ticket.fany.lol` ドメインのURLのみ採用。それ以外または null なら `null` |
| `url2` | `online_url` | オンラインチケットURL。null なら `null` |
| `url3` | `image_url` | フライヤー画像URL。null なら `null` |

### 出力スキーマ（`theater_events.json` の各要素）

```json
{
  "talent_id": null,
  "talent_name": null,
  "matched_talent_ids": ["10708", "5114"],
  "title": "公演タイトル",
  "date": "2026-06-10",
  "open_time": "18:45",
  "start_time": "19:00",
  "end_time": "20:00",
  "members": "出演者テキスト（改行区切り）",
  "venue": "渋谷よしもと漫才劇場",
  "place": null,
  "image_url": "https://feed-cdn.yoshimoto.co.jp/...",
  "ticket_url": "https://ticket.fany.lol/event/detail/xxxxx/zzzzz",
  "online_url": "https://online-ticket.yoshimoto.co.jp/...",
  "price": { "advance": 1300, "door": 1600, "online": 1000 },
  "source": "theater:shibuya"
}
```

### 特記事項

- 登録芸人が1人も出演していない公演は除外（`matched_talent_ids` が空なら捨てる）
- `talent_id` / `talent_name` は `null`。`merge.py` で `matched_talent_ids` を使って芸人ごとに展開される
- `price` はすべてのサブフィールドが null の場合は `null`（フィールド自体を省略）
- `ticket_url` はスカラー値（劇場APIは1公演1URL）。`merge.py` の優先ルールで劇場URLがプロフィールURLより優先される

---

## 3. merge.py との連携

| 処理 | 挙動 |
|---|---|
| プロフィール優先 vs 劇場優先 | 劇場スケジュールのデータ（時刻・出演者・料金・チケットURL）が正とし、プロフィールを上書き |
| 劇場にしかない公演 | 新規エントリとして追加 |
| プロフィールにしかない公演 | プロフィールの値のみで登録（open_time / start_time も反映） |
| チケットURL優先ルール | 劇場スケジュールの `ticket_url`（`/event/detail/` 形式）を最優先。なければプロフィールの `ticket_urls` から `/event/detail/` 形式のものを先頭採用 |

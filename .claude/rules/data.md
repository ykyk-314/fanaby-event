---
paths: data/**/*
---

# data/ — JSONデータファイル

## Git管理対象
- `data/events.json` — スクレイピング結果の正本。**過去イベントを除去しない**
- `data/config.json` — 芸人・劇場・除外タイトルの設定

## Git管理外（.gitignore）
- `data/profile_events.json` — scrape_profile.py の中間出力
- `data/theater_events.json` — scrape_theater.py の中間出力

## events.json スキーマ

```json
{
  "updated_at": "2026-04-03T10:00:00+09:00",
  "events": [
    {
      "id": "11da334f",
      "talent_id": "10708",
      "talent_name": "シンクロニシティ",
      "title": "公演タイトル",
      "date": "2026-05-01",
      "open_time": "18:00",
      "start_time": "18:30",
      "end_time": "20:00",
      "members": "出演者テキスト（改行区切り・white-space:pre-line で表示）",
      "venue": "渋谷よしもと漫才劇場",
      "place": null,
      "image_url": "https://...",
      "local_image": "fliers/11da334f.jpg",
      "ticket_url": "https://...",
      "online_url": null,
      "price": { "advance": 2000, "door": 2500, "online": 1500 },
      "status": "new",
      "first_seen": "2026-04-01T10:00:00+09:00",
      "last_updated": "2026-04-01T10:00:00+09:00",
      "notified_at": null,
      "diff": null,
      "sources": ["profile", "theater"]
    }
  ]
}
```

### 重要フィールドの仕様
- `id`: `SHA1("{talent_id}:{date}:{normalize_title(title)}")[:8]`（同一公演は常に同じID）
- `status`: `new` → `notified`（通知後）/ `notified` → `updated`（変更検知時）
- `local_image`: `docs/` からの相対パス
- `diff`: `{"field": {"before": ..., "after": ...}}` 形式。変更なし時は `null`
- `sources`: `["profile"]` / `["theater"]` / `["profile", "theater"]`

## config.json 構造

```json
{
  "talents": [{"id": "10708", "name": "シンクロニシティ"}],
  "theaters": [{"id": "shibuya", "name": "渋谷よしもと漫才劇場", "url": "https://..."}],
  "exclude_titles": ["除外キーワード"]
}
```

- `exclude_titles`: 部分一致で対象公演をフィルタアウト

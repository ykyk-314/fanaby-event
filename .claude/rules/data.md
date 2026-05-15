---
paths: data/**/*
---

# data/ — JSONデータファイル

## Git管理対象
- `data/events.json` — スクレイピング結果の正本。**過去イベントを除去しない**
- `data/config.json` — 芸人・劇場・除外タイトルの設定

## Git管理外（.gitignore）
- `data/profile_events.json` — scrape_profile_api.py の中間出力
- `data/theater_events.json` — scrape_theater_api.py の中間出力

## events.json スキーマ

```json
{
  "updated_at": "2026-04-03T10:00:00+09:00",
  "events": [
    {
      "id": "11da334f",
      "talents": { "10708": "シンクロニシティ", "5114": "マユリカ" },
      "title": "公演タイトル",
      "date": "2026-05-01",
      "open_time": "18:00",
      "start_time": "18:30",
      "end_time": "20:00",
      "members": "出演者テキスト（改行区切り・white-space:pre-line で表示）",
      "venue": "渋谷よしもと漫才劇場",
      "prefecture": "東京都",
      "place": null,
      "image_url": "https://...",
      "local_image": "fliers/11da334f.jpg",
      "ticket_url": "https://ticket.fany.lol/event/detail/xxxxx/zzzzz",
      "online_url": null,
      "price": { "advance": 2000, "door": 2500, "online": 1500 },
      "status": "new",
      "first_seen": "2026-04-01T10:00:00+09:00",
      "last_updated": "2026-04-01T10:00:00+09:00",
      "notified_at": null,
      "diff": null,
      "sources": ["profile", "theater:shibuya"],
      "excluded": true
    }
  ]
}
```

### 重要フィールドの仕様
- `id`: `SHA1("{date}:{venue}:{start_time}")[:8]`（venue/start_time 不明時は `SHA1("{date}:{normalize_title(title)}")[:8]` にフォールバック）。`talent_id` はハッシュ対象から除外（同一公演に複数芸人が出演するケースで 1 レコードに統合するため）
- `talents`: `{talent_id: talent_name}` 形式の辞書。複数芸人が出演する場合は複数エントリ
- `ticket_url`: スカラー文字列。`/event/detail/` パスに正規化済み（クエリパラメータ除去）
- `prefecture`: 都道府県名（`scrape_theater_api.py` が config から設定）
- `status`: `new` → `notified`（通知後）/ `notified` → `updated`（変更検知時）
- `local_image`: `docs/` からの相対パス（`fliers/{id}.{ext}`）
- `diff`: `{"field": {"before": ..., "after": ...}}` 形式。変更なし時は `null`
- `sources`: `["profile"]` / `["theater:shibuya"]` / `["profile", "theater:shibuya"]` など
- `excluded`: `true` のみ存在（省略時は非除外）。`merge.py` が `/api/excluded-events` から取得して付与

### remind / excluded の管理
`remind`（リマインド ON/OFF）と `excluded`（除外）はユーザー別データであるため、
`events.json` には保存せず Cloudflare KV（`status:{sha256(email)}`）で管理する。
`excluded` は例外的に `events.json` に `true` で書き込まれるが、これは merge.py がグローバル除外リスト（`/api/excluded-events`）を参照して付与するもの。

## config.json 構造

```json
{
  "talents": [
    { "id": "10708", "name": "シンクロニシティ" },
    { "id": "5114",  "name": "マユリカ" },
    { "id": "7295",  "name": "ケビンス" }
  ],
  "theaters": [
    {
      "id": "shibuya",
      "name": "渋谷よしもと漫才劇場",
      "prefecture": "東京都",
      "url": "https://shibuya-manzaigekijyo.yoshimoto.co.jp/schedule/",
      "api_id": "shibuya_manzaigekijyo"
    }
  ],
  "exclude_titles": ["渋谷Kiwami極"]
}
```

- `exclude_titles`: 部分一致で対象公演をフィルタアウト
- `theaters[].api_id`: 劇場 API（`scrape_theater_api.py`）で使用するエンドポイント識別子。`api_id` が無い劇場はスキップ

## ticket_deadlines.json スキーマ

```json
{
  "updated_at": "2026-04-03T10:00:00+09:00",
  "events": {
    "11da334f": {
      "title": "公演タイトル",
      "date": "2026-05-01",
      "scraped_at": "2026-04-03T10:00:00+09:00",
      "tickets": [
        {
          "name": "一般発売",
          "type": "general",
          "status_text": "先着発売中",
          "start": "2026/04/10 10:00",
          "end": "2026/05/01 18:00",
          "url": "https://ticket.fany.lol/..."
        },
        {
          "name": "FC先行抽選",
          "type": "lottery",
          "status_text": "抽選受付終了",
          "start": "2026/03/01 10:00",
          "end": "2026/03/10 23:59",
          "url": "https://ticket.fany.lol/..."
        }
      ]
    }
  }
}
```

- `type`: `"general"` (一般発売) / `"lottery"` (先行抽選)
- `start` / `end`: `"YYYY/MM/DD HH:MM"` 形式

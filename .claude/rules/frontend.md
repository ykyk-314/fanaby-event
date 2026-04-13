---
paths: docs/**/*
---

# docs/ — 静的サイト（Cloudflare Pages）

## ファイル管理の原則
- `docs/index.html` は `build.py` が生成する。手動編集は `build.py` に反映されない
- `docs/assets/style.css` / `docs/assets/script.js` は静的ファイル。`build.py` は触れない
- `docs/fliers/` は `merge.py` が管理。手動で削除・追加しない
- `docs/robots.txt` は全クローラー拒否設定。変更不要

## フロントエンド設計
- タブ切り替え: 全カードを単一DOMに置き、JSフィルタで切り替え（DOMを再生成しない）
- ステータス管理: `script.js` 内の `StatusStorage` オブジェクト経由で LocalStorage に保存
  - キー: `fanaby_statuses`
- 過去公演: `<details>` で折りたたみ表示
- フライヤー: クリックでライトボックス拡大

## ユーザーステータス値とUI表示

| key | 表示名 | カード左ボーダー色 |
|---|---|---|
| `want` | 行きたい | 青 #3498db |
| `lottery_applied` | 先行申込済み | オレンジ #e67e22 |
| `lottery_lost` | 落選 | グレー #95a5a6 |
| `purchased` | 購入済み | 緑 #27ae60 |
| `attended` | 行った | 紺 #2c3e50 |

## LocalStorage スキーマ（`fanaby_statuses`）

```json
{
  "schema_version": 1,
  "updated_at": "2026-04-03T10:00:00.000Z",
  "statuses": {
    "11da334f": {
      "status": "purchased",
      "updated_at": "2026-04-01T15:30:00.000Z",
      "memo": "",
      "history": [
        { "status": "want",      "at": "2026-03-20T10:00:00.000Z" },
        { "status": "purchased", "at": "2026-04-01T15:30:00.000Z" }
      ]
    }
  }
}
```

## 将来のAPI移行方針（Phase 2 A）
`StatusStorage` の内部実装（fetch ベースへの差し替え）のみで端末間同期に対応できる設計を維持する。
`StatusStorage.export()` でLocalStorageからデータをエクスポートしてAPIに移行する。

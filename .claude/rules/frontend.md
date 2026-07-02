---
paths: docs/**/*
---

# docs/ — 静的サイト（Cloudflare Pages）

## ファイル管理の原則
- `docs/index.html` は `build.py` が生成する。手動編集は `build.py` に反映されない
- `docs/assets/style.css` / `docs/assets/script.js` は静的ファイル。`build.py` は触れない
- `docs/fliers/` は `merge.py` が管理。手動で削除・追加しない
- `docs/robots.txt` は全クローラー拒否設定。変更不要

## ファイル構成

| パス | 管理者 | 備考 |
|---|---|---|
| `docs/index.html` | `build.py` が生成 | 手動編集不可 |
| `docs/assets/style.css` | 静的（手動管理） | `build.py` は触れない |
| `docs/assets/script.js` | 静的（手動管理） | `build.py` は触れない |
| `docs/fliers/` | `merge.py` が管理 | 手動で削除・追加しない |
| `docs/register.html` | 静的（手動管理） | 新規登録申請フォーム（Access bypass・Turnstile 付き） |
| `docs/assets/register.js` | 静的（手動管理） | 登録フォームの JS |
| `docs/settings.html` | 静的（手動管理） | 個人設定画面（フォロー芸人・除外キーワード） |
| `docs/assets/settings.js` | 静的（手動管理） | 設定画面の JS（`FollowStorage` / `ExcludeKeywordStorage`） |
| `docs/robots.txt` | 静的 | 全クローラー拒否。変更不要 |

## フロントエンド設計
- タブ切り替え: 全カードを単一 DOM に置き、JS フィルタで切り替え（DOM を再生成しない）
- 観覧ステータス管理: `script.js` 内の `ViewingStorage` オブジェクト経由で LocalStorage ↔ Cloudflare KV を透過同期
  - LocalStorage キー: `fanaby_viewing_statuses`
  - API エンドポイント: `/api/viewing-statuses`（CF Access 認証下）
- 過去公演: `<details>` で折りたたみ表示
- フライヤー: クリックでライトボックス拡大

## 観覧ステータス値とUI表示

| key | 表示名 | カード左ボーダー色 |
|---|---|---|
| `want` | 行きたい | 青 #3498db |
| `lottery_applied` | 先行申込済み | オレンジ #e67e22 |
| `lottery_lost` | 落選 | グレー #95a5a6 |
| `purchased` | 購入済み | 緑 #27ae60 |
| `attended` | 行った | 紺 #2c3e50 |

## フィルターバー項目

| 項目 | 説明 |
|---|---|
| キーワード | 公演名・出演者をスペース区切り AND で全文検索（`data-title` / `data-members` 属性） |
| 会場 | よしもと劇場 / その他劇場で `<optgroup>` 分け |
| 観覧ステータス | 5 種 + 未設定 |
| 日付 from/to | 公演日の範囲絞り込み |
| 通知 ON のみ | `remind-btn[data-remind="on"]` で絞り込み |
| 除外済み表示 | デフォルト非表示。チェックで除外公演（サーバー側 `excluded` フラグ + 個人除外キーワードに一致した公演）を表示 |
| 件数 | 表示中件数をリアルタイム更新 |

## 個人除外設定

タイトルの部分一致で公演を非表示にする個人設定。`docs/settings.html` に2セクションある。

### 定常公演を除外する
劇場主催で月内に何度も開催される寄席・冠番組をまとめて除外する設定。3択（`除外しない`/`一括除外する`/`指定劇場を除外する`）+ 劇場チェックボックス（`指定劇場を除外する` 選択時のみ表示）。

- 設定画面: `docs/assets/settings.js` の `StandingExcludeStorage` オブジェクトが LocalStorage（キー `fanaby_standing_exclude`）と `/api/user-standing-exclude`（CF Access 認証下）を透過同期。`FollowStorage` と同型（`init/get/set(mode, venues)`）。劇場一覧は `STANDING_VENUES` 定数（12劇場）
- 表示側: `docs/assets/script.js` の `initStandingExcludeFilter()` が `/api/user-standing-exclude`（ユーザー設定）と `/api/standing-show-keywords`（劇場別キーワードカタログ、共有）を取得し、`standingExclude`/`standingCatalog` に保持。`isStandingExcluded(title, venue)` で判定し、`applyFilters()` が「除外済み表示」チェックボックスの対象に含める
- キーワードカタログ自体はユーザー編集不可（`scripts/_talents_kv.py` の `STANDING_SHOW_KEYWORDS_BY_VENUE` が起源。KV `standing-show-keywords` へ `merge.py` が自動 seed）

### 除外キーワード（任意のタイトル）
ユーザーが自由記述で追加するキーワードリスト。

- 設定画面: `docs/assets/settings.js` の `ExcludeKeywordStorage` オブジェクトが LocalStorage（キー `fanaby_exclude_keywords`）と `/api/user-exclude-keywords`（CF Access 認証下）を透過同期。`FollowStorage` と同型（`init/getKeywords/setKeywords/addKeyword/removeKeyword`）
- 表示側: `docs/assets/script.js` の `initExcludeFilter()` が `/api/user-exclude-keywords` から取得し、グローバル変数 `excludeKeywords` に保持。`applyFilters()` が `c.dataset.title` との部分一致（大小文字区別あり）でマッチした公演を「除外済み表示」チェックボックスの対象に含める
- 未設定ユーザーには空リストが返る（デフォルト値はなし）

## ViewingStorage（`docs/assets/script.js:163-394`）

LocalStorage と Cloudflare KV を透過的に同期するオブジェクト。

公開メソッド一覧:

| メソッド | 説明 |
|---|---|
| `getAll()` | 全ステータスを返す |
| `get(eventId)` | 単一イベントのステータスを返す |
| `set(eventId, status)` | ステータスを設定（LocalStorage + KV PATCH） |
| `remove(eventId)` | ステータスを削除（LocalStorage + KV DELETE） |
| `getMemo(eventId)` | メモを返す |
| `setMemo(eventId, memo)` | メモを保存（1 秒デバウンス） |
| `getRemind(eventId)` | リマインド ON/OFF を返す |
| `setRemind(eventId, bool)` | リマインドを設定 |
| `getExcluded(eventId)` | 除外フラグを返す |
| `setExcluded(eventId, bool)` | 除外フラグを設定 |
| `export()` | LocalStorage データを返す（API 移行用） |
| `import(data)` | データをインポート |

`init()` 時: ローカルとリモートを `updated_at` 比較でマージし、新しい方を採用。
書き込み失敗時は `fanaby_pending_sync` フラグをセット（オフライン保護）。

## LocalStorage スキーマ（`fanaby_viewing_statuses`）

```json
{
  "schema_version": 1,
  "updated_at": "2026-04-03T10:00:00.000Z",
  "statuses": {
    "11da334f": {
      "status": "purchased",
      "updated_at": "2026-04-01T15:30:00.000Z",
      "memo": "",
      "remind": true,
      "excluded": false,
      "history": [
        { "status": "want",      "at": "2026-03-20T10:00:00.000Z" },
        { "status": "purchased", "at": "2026-04-01T15:30:00.000Z" }
      ]
    }
  }
}
```

## 登録申請フォーム（`docs/register.html`）

- Cloudflare Access の bypass パスに配置（未認証ユーザーがアクセス可能）
- Cloudflare Turnstile widget でボット対策
- 送信先: `POST /api/register-request`
- 成功時: 「申請を受け付けました」を表示してフォームリセット

## セキュリティ制約
- memo フィールドを画面表示する際は **必ず `textContent` で代入**（`innerHTML` 禁止・XSS防止）
- ステータス値は `VALID_VIEWING_STATUSES` ホワイトリストで検証してから DOM に反映すること
- APIレスポンスは `_validateRemote()` を経由し、不正なデータはDOM/localStorageに渡さない

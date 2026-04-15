# Phase 2 A: 端末間ステータス同期 — 実装計画

## Context

現在、公演ステータス（行きたい・購入済み等）は `localStorage` のみに保存されており、端末間で同期されない。
Cloudflare Pages Functions + Workers KV を使い、同一ドメイン上にAPIを追加してクラウド同期を実現する。

**制約**: 無料枠のみ（KV: 100k reads/日, 1k writes/日, 1GB）。個人利用のため十分。

## アーキテクチャ

```
[Browser]                      [Cloudflare Edge]
script.js ViewingStorage  --->  Pages Functions (/api/*)  --->  Workers KV
    |                               |
    v                               v
 localStorage                  CF_Authorization
 (キャッシュ/オフライン)        (既存Cloudflare Accessで認証)
```

**Pages Functions を採用**（standalone Workers ではなく）:
- 同一ドメインなので CORS 不要、`CF_Authorization` Cookie が自動送信される
- `cloudflare/pages-action@v1` で自動デプロイ（`functions/` ディレクトリを自動検出）

## KV 設計

- **単一キー方式**: `user_statuses` に全ステータスを1つのJSONとして格納
- スキーマは現行 `localStorage` と同一（`schema_version`, `updated_at`, `statuses`）
- 数百イベント × 300bytes ≈ ~100KB（25MiB上限に対して十分）

## API 設計

| Method | Path | 用途 | KV操作 |
|--------|------|------|--------|
| `GET` | `/api/viewing-statuses` | 全ステータス取得 | 1 read |
| `PUT` | `/api/viewing-statuses` | 全置換（移行・インポート） | 1 write |
| `PATCH` | `/api/viewing-statuses/:eventId` | 単一イベント更新 | 1 read + 1 write |
| `DELETE` | `/api/viewing-statuses/:eventId` | 単一イベント削除 | 1 read + 1 write |

## 同期戦略

- **Write-through**: `set()`/`remove()` は localStorage を即時更新（UI即反映）→ バックグラウンドで API 呼び出し
- **ページロード時**: API から取得し localStorage を更新。API 失敗時は localStorage フォールバック
- **初回移行**: API が空 & localStorage にデータあり → `PUT` で一括アップロード
- **マージ**: 両方にデータがある場合、イベントごとに `updated_at` が新しい方を採用
- **オフライン保護**: API 書き込み失敗時に `fanaby_pending_sync` フラグを localStorage に保存。次回 `init()` で再同期

## 新規・変更ファイル

### 新規作成

| ファイル | 内容 |
|---------|------|
| `functions/api/viewing-statuses/index.js` | `GET` / `PUT` ハンドラ |
| `functions/api/viewing-statuses/[eventId].js` | `PATCH` / `DELETE` ハンドラ |
| `wrangler.toml` | KV namespace バインディング設定 |

### 変更

| ファイル | 変更内容 |
|---------|---------|
| `docs/assets/script.js` | `ViewingStorage` を async + remote sync に書き換え。`init()` 追加、`_patchRemote` / `_deleteRemote` / `_putRemote` 追加。`initStatusUI()` を async 呼び出しに変更 |
| `.github/workflows/main.yml` | Pages Functions デプロイ対応（必要に応じて調整） |

## ViewingStorage 変更方針

```
_load() / _save()  →  localStorage操作はそのまま残す（キャッシュ層として）
init()             →  新規追加。API fetch → localStorage更新 → 移行/マージ
set(eventId, st)   →  localStorage即時更新 + _patchRemote() fire-and-forget
remove(eventId)    →  localStorage即時更新 + _deleteRemote() fire-and-forget
export() / import()→  既存維持 + remote同期追加
```

`set()` / `remove()` は同期メソッドのまま（UIブロックしない）。API呼び出しは非同期。

## 初回セットアップ（手動・1回のみ）

1. Cloudflare ダッシュボードで KV namespace `FANABY_VIEWING_STATUSES` を作成
2. Pages プロジェクト設定 → Functions → KV namespace bindings に追加
3. namespace ID を `wrangler.toml` に記入

## 実装順序

1. **KV namespace 作成 & バインディング設定**（手動）
2. **`wrangler.toml` 作成**
3. **Pages Functions 実装** (`functions/api/viewing-statuses/`)
4. **`script.js` の `ViewingStorage` 書き換え**（async init + write-through + マージ + オフライン保護）
5. **デプロイパイプライン検証**（`functions/` が正しくデプロイされるか確認）
6. **移行テスト**（既存 localStorage データ → KV アップロード → 別端末で確認）

## Phase 2 F（コメント機能）との互換性

- KV スキーマの `memo` フィールドは既に存在
- `PATCH` API は `memo` パラメータを受け付ける設計済み
- Phase 2 F 実装時は UI 追加 + `setMemo()` メソッド追加のみ

## 検証方法

1. ローカルで `wrangler pages dev docs` を実行し Pages Functions の動作確認
2. ブラウザの DevTools Network タブで API リクエスト/レスポンスを確認
3. localStorage にデータがある状態でデプロイし、自動移行を確認
4. 別端末/ブラウザからアクセスし、ステータスが同期されていることを確認
5. オフライン状態でステータス変更 → オンライン復帰後に同期されることを確認

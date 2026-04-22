# Phase 3-B: 公演除外機能 実装計画

## Context

**目的**: 不要な公演を個別に「除外」でき、その後のスケジュール取得・差分通知・HTML表示から外せる機能を追加する。

**背景**:
- 現在は `data/config.json` の `exclude_titles` によるタイトル部分一致での除外のみ対応（`scripts/merge.py:385-393`）
- 個別の公演IDを指定した除外ができず、`config.json` を直接編集する必要がある
- 行くつもりのない公演が差分通知やカード表示に含まれ続け、ノイズになっている

**期待する効果**:
- 公演カードの「除外」ボタン1クリックで、そのイベントを以降の通知・表示から外せる
- 誤操作した場合はフィルターバー経由で除外済みを再表示して「解除」できる
- 既存の `exclude_titles` 機能はそのまま残す（全体ルール）

---

## 設計方針

### データフロー

```
[フロントエンド]
    ↓ POST /api/excluded-events/{eventId}（Cloudflare Access 認証）
[KV: FANABY_VIEWING_STATUSES, キー: excluded_events]
    ↑ GET /api/excluded-events（Bearer REMIND_API_SECRET）
[GitHub Actions: merge.py]
    ↓ events.json の該当イベントに excluded: true を付与
[notify.py] → excluded: true をスキップ
[build.py] → data-excluded="true" 属性を HTML に出力
[script.js] → フィルターで表示/非表示切替、解除ボタン表示
```

### 設計判断（ユーザー確認済み）

| 論点 | 決定 |
|---|---|
| 解除UI | フィルターバーに「除外済みを表示」チェックボックスを追加 |
| 除外時の確認 | `confirm()` ダイアログを表示 |
| KV配置 | 既存 `FANABY_VIEWING_STATUSES` に `excluded_events` キーで統合 |

### KVスキーマ

```
KVキー: excluded_events
値: {
  "ids": ["eventId1", "eventId2", ...],
  "updated_at": "2026-04-21T10:00:00.000Z"
}
```

### events.json 拡張フィールド

```json
{
  "id": "b9a2335e",
  ...既存フィールド...,
  "excluded": true     // ← 新規追加（除外時のみ付与）
}
```

---

## 実装ステップ

### 1. API新設: `functions/api/excluded-events.js`

**エンドポイント**:
- `GET /api/excluded-events` — 除外IDリスト取得（Bearer or CF-Access 認証）
- `POST /api/excluded-events` — 除外ID追加（body: `{eventId}`、CF-Access 認証）
- `DELETE /api/excluded-events` — 除外ID解除（body: `{eventId}`、CF-Access 認証）

**認証パターン**:
```javascript
function isAuthorized(request, env) {
  const authHeader = request.headers.get('Authorization');
  if (authHeader === `Bearer ${env.REMIND_API_SECRET}`) return true;
  return !!request.headers.get('CF-Access-Authenticated-User-Email');
}
```

**参考**: `functions/api/remind-list.js:1-61`（Bearer認証）と `functions/api/viewing-statuses/index.js:12-18`（CF-Access認証）を併用。

### 2. Cloudflare Access ポリシー更新

`/api/excluded-events` を `bypass` ポリシーに追加（GitHub Actions からBearer認証でアクセスできるようにする）。
手動対応項目（Zero Trust ダッシュボードで `fanaby-event-remind-list` アプリの `self_hosted_domains` に `/api/excluded-events` を追加する代わりに、**別アプリを新設するか、既存 remind-list アプリのドメインを拡張**）。

→ 今回の実装ではコード変更のみで対応し、ダッシュボード設定手順は実装完了後に案内する。

### 3. merge.py 改修

**ファイル**: `scripts/merge.py`

**変更内容**:
- 新関数 `fetch_excluded_events()` を追加（`REMIND_API_URL` + `REMIND_API_SECRET` でGET）
- `main()` の末尾（ソート前、`scripts/merge.py:434` 付近）で除外フラグ適用:
  ```python
  excluded_ids = fetch_excluded_events()
  for ev in events:
      if ev["id"] in excluded_ids:
          ev["excluded"] = True
      elif ev.get("excluded"):
          ev.pop("excluded", None)   # 除外解除時にフラグ削除
  ```
- `diff_and_update()` 内で既存の `excluded` フラグを引き継ぎ（`scripts/merge.py:294-359`）
- API取得失敗時は既存の `excluded` フラグをそのまま維持（フェイルセーフ）

### 4. notify.py 改修

**ファイル**: `scripts/notify.py:184`

**変更内容**:
```python
notify_targets = [
    e for e in events
    if e.get("status") in ("new", "updated") and not e.get("excluded")
]
```
除外イベントは通知対象から外す。

### 5. build.py 改修

**ファイル**: `scripts/build.py:84-204`

**変更内容**:
- 公演カードの `<article>` タグに `data-excluded="true|false"` 属性を追加
- 除外カード内に「除外解除」ボタンを追加（`data-excluded="true"` の場合のみ表示）
- 通常の「除外」ボタンも全カードに追加（`data-excluded="false"` の場合のみ表示）
- build.py 自体は除外イベントを出力から削除しない（フィルタはフロント側で切替）

### 6. script.js 改修

**ファイル**: `docs/assets/script.js`

**追加する機能**:
- フィルターバーに `#filterShowExcluded` チェックボックスを追加
- `applyFilters()` 内（`docs/assets/script.js:79-141`）で、チェックOFF時は `data-excluded="true"` のカードを非表示
- 「除外」ボタンのクリックハンドラー:
  ```javascript
  async function excludeEvent(eventId) {
    if (!confirm('この公演を除外しますか？以降の通知・表示から外れます。')) return;
    await fetch('/api/excluded-events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ eventId }),
    });
    const card = document.querySelector(`[data-event-id="${eventId}"]`);
    if (card) { card.dataset.excluded = 'true'; applyFilters(); }
  }
  ```
- 「除外解除」ボタンは DELETE を呼び、`data-excluded="false"` にしてフィルタ再適用

### 7. main.yml 改修

**ファイル**: `.github/workflows/main.yml:51-61`

**変更内容**:
- `Merge and detect diffs` ステップに環境変数 `REMIND_API_URL` / `REMIND_API_SECRET` を追加
- `Send notifications` は events.json のフラグだけ見るため変更不要

---

## 修正対象ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `functions/api/excluded-events.js`（新規） | API実装 |
| `scripts/merge.py` | 除外フラグ適用・引き継ぎ |
| `scripts/notify.py` | excluded イベントのスキップ |
| `scripts/build.py` | data-excluded 属性と除外/解除ボタン |
| `docs/assets/script.js` | UI・フィルタ・API連携 |
| `docs/assets/style.css` | 除外/解除ボタンのスタイル |
| `.github/workflows/main.yml` | 環境変数追加 |

---

## 検証方法

1. **API動作確認**:
   - `curl -H "Authorization: Bearer $REMIND_API_SECRET" https://fanaby-event.pages.dev/api/excluded-events` で `{ids: []}` が返ることを確認
   - Cloudflare Access ログイン済みブラウザから POST/DELETE を実行し、KV が更新されることを確認

2. **フロントエンド動作確認**:
   - 公演カードの「除外」ボタンをクリック → 確認ダイアログ → KV更新 → カード非表示
   - フィルターバーの「除外済みを表示」チェック → 除外カードが見える → 「解除」ボタンで元に戻る

3. **CI/CD動作確認**:
   - `workflow_dispatch` で `skip_scrape: true` を指定して手動実行
   - `data/events.json` の該当イベントに `excluded: true` が付与されることを確認
   - 除外イベントが通知メールから除外されることを確認（次回スクレイプ時）

4. **手動対応項目**:
   - Cloudflare Zero Trust で `/api/excluded-events` へのバイパスポリシー設定（GitHub Actions 用）
   - GitHub Secrets に `REMIND_API_URL` / `REMIND_API_SECRET` は既設済みなので追加不要

# Cloudflare セットアップ手順

端末間ステータス同期（Phase 2 A）を有効化するための Cloudflare 設定手順。
**一回だけ実施すれば OK。以降は GitHub Actions が自動デプロイする。**

---

## 前提

- Cloudflare アカウントにログイン済み
- fanaby-event の Pages プロジェクトが既に存在する

---

## Step 1 — KV 名前空間を作成する

> Workers KV は「観覧ステータス」データのクラウド保存先。

1. Cloudflare ダッシュボード左サイドバー
   → **「ストレージとデータベース」** → **「Workers KV」**

2. 右上の **「名前空間の作成」** ボタンをクリック

3. 名前を入力:
   ```
   FANABY_VIEWING_STATUSES
   ```

4. **「追加」** をクリック

5. 作成された名前空間の **「ID」列の文字列（UUID形式）をコピー**
   ```
   例: a1b2c3d4-e5f6-7890-abcd-ef1234567890
   ```

---

## Step 2 — wrangler.toml を更新する

プロジェクトのルートにある `wrangler.toml` を開き、
`REPLACE_WITH_YOUR_KV_NAMESPACE_ID` を Step 1 でコピーした ID に書き換える。

**変更前:**
```toml
[[kv_namespaces]]
binding = "FANABY_VIEWING_STATUSES"
id = "REPLACE_WITH_YOUR_KV_NAMESPACE_ID"
```

**変更後:**
```toml
[[kv_namespaces]]
binding = "FANABY_VIEWING_STATUSES"
id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"  ← Step1でコピーしたIDに置き換え
```

保存して Git にコミット・プッシュする（次の Step 3 の後でもよい）。

---

## Step 3 — Pages プロジェクトに KV をバインドする

> Pages Functions（API）が KV にアクセスするために必要。

1. Cloudflare ダッシュボード左サイドバー
   → **「Workers & Pages」** → **「fanaby-event」**

2. 上部タブから **「設定」**（Settings）をクリック

3. 左メニュー or セクション内の **「Functions」** をクリック

4. **「KV namespace bindings」** セクションまでスクロール

5. **「追加」** ボタンをクリックし、以下を入力:

   | 項目 | 値 |
   |------|-----|
   | Variable name | `FANABY_VIEWING_STATUSES` |
   | KV namespace | Step 1 で作成した `FANABY_VIEWING_STATUSES` を選択 |

6. **「保存」** をクリック

---

## Step 4 — Cloudflare Access の適用範囲を確認する

> API エンドポイント（`/api/*`）が認証なしでアクセスできないことを確認。

1. Cloudflare ダッシュボード左サイドバー
   → **「Zero Trust」**（または「Access」）

2. **「Access」** → **「Applications」**

3. `fanaby-event.pages.dev`（またはカスタムドメイン）の Application を開く

4. **「Overview」タブ** でドメインが以下のように設定されていることを確認:

   ```
   ドメイン: fanaby-event.pages.dev
   パス: （空欄 or *）
   ```

   パスが空欄または `*` であれば `/api/*` も保護済み。
   特定パス（例: `/`）のみになっていたら、パスを空欄に変更する。

---

## Step 5 — デプロイして動作確認する

### 5-1. GitHub にプッシュ

```bash
git add wrangler.toml
git commit -m "chore: set KV namespace ID for viewing status sync"
git push
```

→ GitHub Actions が自動実行され Pages Functions がデプロイされる

### 5-2. API 疎通確認

ブラウザで以下の URL にアクセスし、JSON が返ってくれば成功:

```
https://fanaby-event.pages.dev/api/viewing-statuses
```

期待レスポンス（初回は空）:
```json
{"schema_version":1,"statuses":{}}
```

Cloudflare Access のログイン画面が表示された場合は、ログインすると確認できる。
`{"error": ...}` が返る場合は Step 3 の KV バインディングを再確認。

### 5-3. Web アプリで観覧ステータスを動作確認

1. `https://fanaby-event.pages.dev` を開く
2. 任意の公演に観覧ステータスを設定
3. 別の端末（またはシークレットウィンドウ）で同じ URL を開く
4. 設定したステータスが表示されていれば同期成功

---

## トラブルシューティング

| 症状 | 確認箇所 |
|------|---------|
| `/api/viewing-statuses` が 404 | Pages Functions が正しくデプロイされているか確認（`functions/api/viewing-statuses/` ディレクトリが Git に含まれているか） |
| `/api/viewing-statuses` が 500 | Step 3 の KV バインディングが保存されているか確認 |
| `/api/viewing-statuses` が Access ログイン画面にリダイレクトされる | Step 4 で確認した Access ポリシーのドメイン設定を確認 |
| ステータスが同期されない | ブラウザの DevTools → Network タブで `/api/viewing-statuses` へのリクエストがエラーになっていないか確認 |
| wrangler.toml の ID が間違っている | Step 1 でコピーした UUID を再確認。ダッシュボードの Workers KV 一覧で ID を再コピー |

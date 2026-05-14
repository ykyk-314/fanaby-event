# 新規ユーザー登録申請 + 管理者承認フロー

`.claude/rules/phase3.md` の **D タスク** 対応。

## Context

現状、`fanaby-event.pages.dev` は Cloudflare Access で全パスを保護しているが、Access のメール OTP 認証は「誰でもメールアドレスを入力できる」状態にあり、ポリシー未登録のメールアドレスを入力しても**OTPコード入力画面まで遷移はするがメールは届かない**（CF Access の意図的なセキュリティ仕様）。これでは「自分以外の閲覧者を増やしたい」場合に、運営者が手動で Cloudflare ダッシュボードを操作する以外の手段がない。

このプランは、サービスサイト上から**新規登録申請フォーム**で申請を行い、管理者がメールに届く**承認リンク**をクリックすると Cloudflare Access のポリシーに自動でメールアドレスが追加される、というセルフサービス的な登録ワークフローを構築する。すべて Cloudflare 無料枠 + 既存 GitHub Actions（Gmail SMTP）で完結させる。

## アーキテクチャ

```
[未登録ユーザー]
   │
   ▼
/register.html （Access bypass で公開、Turnstile widget 埋込）
   │ POST email + cf-turnstile-response
   ▼
POST /api/register-request （Access bypass で公開）
   ├─ Turnstile siteverify
   ├─ KV ratelimit:register:{ip} で IP レート制限（1h で5回まで）
   ├─ KV register-email:{sha256(email)} で重複申請ガード（pending時は受付済み扱い）
   ├─ token = crypto.randomUUID()
   ├─ KV register-req:{token} = {email, created_at, status:"pending"} TTL 24h
   ├─ KV register-email:{sha256(email)} = {token, status:"pending", created_at} TTL 24h
   └─ fetch → GitHub API repos/.../dispatches (event_type: register-request, payload: {token, email})
              │
              ▼
       [.github/workflows/notify-register.yml]
              │ on: repository_dispatch [register-request]
              ▼
        python scripts/notify_register.py
              │ smtplib SMTP_SSL → ADMIN_EMAIL 宛
              ▼
        管理者メール
           承認: SITE_ORIGIN/api/register-approve?token={token}
           拒否: SITE_ORIGIN/api/register-reject?token={token}

[管理者がリンクをクリック]
   │
   ▼
GET /api/register-approve?token=xxx （Cloudflare Access 認証必須）
   ├─ CF-Access-Authenticated-User-Email が env.ADMIN_EMAILS に含まれるか検証 → 否なら 403
   ├─ KV register-req:{token} 取得 → 期限切れ/存在せずなら 410
   ├─ status=="approved" なら冪等成功（既処理）
   ├─ Cloudflare API: PATCH /accounts/{acc}/access/groups/{group_id}
   │     既存 include[] に {"email": {"email": email}} を append して PATCH
   │     "duplicate" 系エラーは成功扱い
   ├─ KV register-req:{token}.status = "approved" + approved_at
   ├─ KV register-email:{hash}.status = "approved" + TTL 30日に延長
   └─ 成功HTML（簡素な「承認しました」ページ）を返す

GET /api/register-reject?token=xxx （同じく Access 必須・admin 判定）
   ├─ KV を rejected に更新
   └─ 「拒否しました」HTML を返す
```

## Cloudflare Access 手動セットアップ（1回のみ）

1. **Zero Trust → Access → Groups → Create Group**
   - 名前: `fanaby-approved-users`
   - Include: 既存ユーザー2名のメールアドレスを Emails ルールで追加
   - グループID（UUID形式）をメモ → `CF_ACCESS_GROUP_ID` env として後で使用

2. **Zero Trust → Access → Applications → fanaby-event** のメインポリシーを編集
   - Include を「Emails 直接指定」から「Access Group: fanaby-approved-users」に切替
   - 動作確認: 既存ユーザー2名でログインできること

3. **同アプリにポリシー追加 or 既存にbypass rule追加**:
   - Path patterns: `/register.html`, `/api/register-request`, `/cdn-cgi/*`（Turnstile asset）
   - Action: Bypass（無認証アクセス許可）
   - 既存の保護パスより上に配置

4. **API Token 発行**
   - My Profile → API Tokens → Create Token
   - 権限: `Account → Access: Organizations, Identity Providers, and Groups → Edit`
   - スコープ: 該当アカウントのみ
   - トークン値をメモ → `CF_API_TOKEN` env

5. **Cloudflare Turnstile Site 発行**
   - Turnstile → Add Site → `fanaby-event.pages.dev`
   - Site Key（クライアント用、公開可）と Secret Key（サーバー用）を取得

## 環境変数・シークレット追加

### Cloudflare Pages の環境変数（Settings → Environment variables → Production）

| 変数名 | 値 | 用途 |
|---|---|---|
| `CF_API_TOKEN` | （上記4で発行） | Access Group 編集 |
| `CF_ACCOUNT_ID` | アカウントID | API 呼び出し |
| `CF_ACCESS_GROUP_ID` | （上記1のID） | グループ指定 |
| `GH_DISPATCH_TOKEN` | fine-grained PAT（`Actions: write` のみ） | repository_dispatch 発火 |
| `GH_REPO` | `yokoyan/fanaby-event` | dispatch URL 組立 |
| `ADMIN_EMAILS` | カンマ区切り（小文字） | 承認者判定 |
| `SITE_ORIGIN` | `https://fanaby-event.pages.dev` | メール内リンク組立 |
| `TURNSTILE_SECRET_KEY` | （上記5） | siteverify |
| `TURNSTILE_SITE_KEY` | （上記5、公開可） | register.html 埋込用（ビルド時定数 or fetch経由） |

### GitHub リポジトリの Secrets / Variables

| 名前 | 種別 | 用途 |
|---|---|---|
| `MAIL_USER` / `MAIL_PASS` | Secret（既存） | 流用 |
| `ADMIN_EMAIL` | Secret（新規） | 管理者通知先（単一アドレス） |
| `SITE_ORIGIN` | Variable（新規） | メール本文の URL 組立 |

## KV キー設計（既存 `FANABY_VIEWING_STATUSES` namespace に相乗り）

| キー | 値 | TTL | 用途 |
|---|---|---|---|
| `register-req:{token}` | `{email, created_at, status, approved_at?, rejected_at?}` | 24h（approved時 30日に延長） | 承認/拒否時の primary lookup |
| `register-email:{sha256(email)}` | `{token, status, created_at}` | 24h（approved時 30日） | 重複申請ガード |
| `ratelimit:register:{ip}` | `{count, first_at}` | 1h | IP レート制限 |

既存キー（`status:*` / `user:*` / `excluded_events`）とは prefix が重複しないので相乗り安全。

## 追加ファイル一覧

| パス | 役割 |
|---|---|
| `docs/register.html` | 申請フォーム + Turnstile widget |
| `functions/api/register-request.js` | POST受付 + Turnstile検証 + KV保存 + GH dispatch |
| `functions/api/register-approve.js` | GET 承認（管理者限定 + CF API 呼び出し） |
| `functions/api/register-reject.js` | GET 拒否（管理者限定 + KV更新のみ） |
| `functions/_lib/auth.js` | `getAdminEmail(request, env)` 共通化（CF Access ヘッダー検証 + ADMIN_EMAILS 照合） |
| `scripts/notify_register.py` | repository_dispatch から起動、ADMIN_EMAIL に承認/拒否 URL メール送信 |
| `.github/workflows/notify-register.yml` | `on: repository_dispatch [register-request]` トリガー |

`functions/_lib/auth.js` は新設の共通モジュール。既存 `me.js` / `viewing-statuses/*.js` の `getUserHash` 重複も将来移設候補だが、本タスクでは新規ファイルでの利用に留める（既存改変なし）。

## 実装ディテール

### `functions/api/register-request.js`

```js
// 主要ロジック
export async function onRequestPost({ request, env }) {
  // 1. body 取得 + email バリデーション (RFC 5322 簡易正規表現)
  // 2. Turnstile siteverify (https://challenges.cloudflare.com/turnstile/v0/siteverify)
  //    secret=TURNSTILE_SECRET_KEY, response=body['cf-turnstile-response'], remoteip=CF-Connecting-IP
  // 3. IP レート制限 (KV.get -> increment -> KV.put with 3600 TTL, 5回超で 429)
  // 4. register-email:{sha256(email)} の既存チェック
  //    - pending: { ok:true, message:"申請済み" } 200 で早期return（dispatchもskip）
  //    - approved: 409 既登録
  // 5. token = crypto.randomUUID()
  // 6. KV put register-req:{token} と register-email:{hash} (両方 TTL 86400)
  // 7. fetch POST https://api.github.com/repos/{GH_REPO}/dispatches
  //      Authorization: Bearer {GH_DISPATCH_TOKEN}
  //      body: {event_type:"register-request", client_payload:{token, email}}
  //    失敗時は KV を両方削除 + 500 返す
  // 8. { ok:true } 200 を返す
}
```

レスポンスは「成功 / すでに申請済み / 既登録 / レート超過 / 検証失敗」の5系統。

### `functions/api/register-approve.js` / `register-reject.js`

```js
// 共通: env.ADMIN_EMAILS.split(',').map(trim+lower).includes(currentEmail)
// approve:
//   1. token をクエリから取得
//   2. KV register-req:{token} 取得 → 無/期限切れ なら 410
//   3. status === "approved" なら冪等成功HTML
//   4. CF API: PATCH /accounts/{acc}/access/groups/{group_id}
//      実装: 既存 group を GET → include 配列に {"email":{"email":email}} append → PUT
//      "duplicate" 検知用に GET レスポンスの include を email lower-case で比較してスキップ
//   5. KV register-req:{token} を { ...prev, status:"approved", approved_at } で update (TTL 30日)
//   6. KV register-email:{hash} も同様 update
//   7. 成功HTML返却（リンクで /register.html や / に戻れる）
// reject:
//   - CF API は呼ばず KV のみ rejected に更新
```

### `docs/register.html`

最小構成（既存 `assets/style.css` を読み込み再利用）:

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>新規登録申請 - fanaby-event</title>
  <link rel="stylesheet" href="assets/style.css">
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
</head>
<body>
  <header><h1>新規登録申請</h1></header>
  <main class="container">
    <p>サービス利用には管理者の承認が必要です。申請を送信すると、管理者にメール通知が届きます。</p>
    <form id="register-form">
      <input type="email" name="email" required placeholder="email@example.com">
      <div class="cf-turnstile" data-sitekey="__TURNSTILE_SITE_KEY__"></div>
      <button type="submit" class="btn">申請する</button>
    </form>
    <div id="result"></div>
  </main>
  <script src="assets/register.js"></script>
</body>
</html>
```

- `__TURNSTILE_SITE_KEY__` は `wrangler.toml` の `[vars]` 経由か、build.py 拡張ではなく **ビルド時にプレースホルダ置換** する単純なシェルステップを `notify-register.yml` 以外の deploy 系ワークフローに入れる…のは複雑化するので、**Site Key はクライアント公開可能な値なのでハードコードでも安全**。Site Key だけは直書きする運用にする（Secret Keyだけは厳重に env で管理）。

`docs/assets/register.js` を追加し、form submit → fetch POST → `result` 表示。

### `scripts/notify_register.py`

```python
# 主要ロジック
# - 環境変数: MAIL_USER, MAIL_PASS, ADMIN_EMAIL, SITE_ORIGIN, REQ_TOKEN, REQ_EMAIL
# - smtplib.SMTP_SSL("smtp.gmail.com", 465) で接続
# - HTML 本文に下記リンクを埋込：
#     https://{SITE_ORIGIN}/api/register-approve?token={REQ_TOKEN}
#     https://{SITE_ORIGIN}/api/register-reject?token={REQ_TOKEN}
# - 件名: 【fanaby-event 登録申請】{REQ_EMAIL}
```

既存 `scripts/notify.py:166-175` の `send_mail` を踏襲したシンプルな実装。`notify.py` は変更しない（責務分離）。

### `.github/workflows/notify-register.yml`

```yaml
name: notify-register
on:
  repository_dispatch:
    types: [register-request]
permissions:
  contents: read
jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install python-dotenv
      - env:
          MAIL_USER:    ${{ secrets.MAIL_USER }}
          MAIL_PASS:    ${{ secrets.MAIL_PASS }}
          ADMIN_EMAIL:  ${{ secrets.ADMIN_EMAIL }}
          SITE_ORIGIN:  ${{ vars.SITE_ORIGIN }}
          REQ_TOKEN:    ${{ github.event.client_payload.token }}
          REQ_EMAIL:    ${{ github.event.client_payload.email }}
        run: python scripts/notify_register.py
```

## 既存パターン再利用ポイント

| 既存実装 | 参照箇所 | 再利用内容 |
|---|---|---|
| `json()` ヘルパー | `functions/api/excluded-events.js:43-48` | そのまま流用 |
| `isCfAccessAuthorized()` | `functions/api/excluded-events.js:25-29` | 承認/拒否エンドポイントで活用 |
| `getUserHash()` | `functions/api/me.js:7-10` | sha256(email) のハッシュ生成 |
| KV namespace 名 | `wrangler.toml` | `FANABY_VIEWING_STATUSES` 相乗り |
| smtplib SMTP_SSL パターン | `scripts/notify.py:166-175` | notify_register.py で同形 |
| `Authorization: Bearer` 認証パターン | `functions/api/remind-list.js:12-19` | 不採用（管理者は CF Access で識別） |
| `workflow_dispatch` / repository_dispatch 構造 | `.github/workflows/remind-check.yml` | yml 構造の雛形 |

## 変更しないファイル

- `scripts/notify.py`（責務違いのため拡張せず別ファイル）
- `scripts/build.py`（register.html は静的ファイル、ビルド対象外）
- 既存 `functions/api/*.js`（変更不要、新規ファイルのみ追加）
- `data/*.json`（影響なし）

## ブランチ・コミット運用

- ブランチ: `feature/260514`（CLAUDE.md の規約に従う）
- コミットを段階的に分割:
  1. `feat: add register pages function and frontend`（functions/api/register-*.js + docs/register.html + register.js）
  2. `feat: add register notification workflow`（scripts/notify_register.py + .github/workflows/notify-register.yml）
  3. `chore: document register approval flow`（`.claude/rules/phase3.md` の D タスクを完了マーク、本プランの完了記録）

## 検証手順

### 1. 設定確認（実装前）

- [ ] Cloudflare Access Group `fanaby-approved-users` を作成し、既存2ユーザーを移行できることをダッシュボードで確認
- [ ] CF API Token を発行し、`curl -H "Authorization: Bearer $CF_API_TOKEN" https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/access/groups/$CF_ACCESS_GROUP_ID` で GET 200 が返ることをローカルで確認
- [ ] Turnstile Site Key / Secret Key を発行

### 2. デプロイ後の E2E 確認

- [ ] 未認証のブラウザで `https://fanaby-event.pages.dev/register.html` にアクセスできる（Access のメール入力画面に遷移しない）
- [ ] 申請フォームから自分の別メールアドレス（未登録）で申請 → 「申請を受け付けました」が表示される
- [ ] ADMIN_EMAIL 宛にメールが届く（承認・拒否リンク入り）
- [ ] **承認リンクをログイン済みブラウザでクリック** → 「承認しました」HTML が表示される
- [ ] Cloudflare ダッシュボードで `fanaby-approved-users` グループに該当メールが追加されている
- [ ] 申請したメールアドレスで通常ログイン → OTP コードが実際に届き、サイトにアクセスできる
- [ ] 承認済みリンクを再クリック → 冪等成功 HTML が表示される（CF API 二重呼び出ししない）
- [ ] 同じメールで再申請 → 「すでに申請済み」が返る
- [ ] 別のメールで申請 → 拒否リンククリック → KV が rejected になり CF Access には追加されない

### 3. セキュリティ確認

- [ ] `/api/register-request` を Turnstile トークンなしで叩く → 検証失敗で 400
- [ ] 同じ IP から6回連続 POST → 6回目で 429
- [ ] 非管理者ユーザーで `/api/register-approve?token=xxx` を叩く → 403
- [ ] 承認エンドポイントを未ログイン状態で叩く → Cloudflare Access の認証画面に遷移（bypass されていない）

### 4. エラーリカバリ確認

- [ ] `GH_DISPATCH_TOKEN` を一時的に無効化して申請 → 500 が返り、KV に pending が残らない
- [ ] 不正なトークンで承認リンクを叩く → 410
- [ ] 24h 経過後（または KV を手動削除）に同じトークンで承認 → 410

## リスクと留意事項

- **CF API レスポンス形式の変動**: Access Group の PATCH API は include 配列の完全置換である可能性が高い。実装前に curl で動作確認し、append でなく既存 + 新規の合成 PUT を行う必要があるなら採用する（実装ディテールは Implementation 中に curl で再確認）。
- **GitHub Actions の repository_dispatch 遅延**: 通常数秒以内に発火するが、稀に1-2分遅延することがある。ユーザーには「申請を受け付けました。管理者の承認をお待ちください」とだけ表示し、メール到着時刻には期待を持たせない。
- **Turnstile セットアップが詰まった場合**: 一時的に Turnstile スキップ（IP レート制限のみ）に縮退できるよう、env `TURNSTILE_SECRET_KEY` 未設定時は siteverify をスキップする実装にする。
- **既存ユーザー移行**: メインポリシーを Emails 直接指定 → Access Group に切替える瞬間、設定が反映されるまで（数秒〜数十秒）既存ユーザーがアクセス不能になる可能性。サービス停止時間帯（深夜等）に実施推奨。

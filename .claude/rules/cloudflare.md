---
paths: functions/**/*
---

# Cloudflare — Pages Functions / KV / Access

## API エンドポイント一覧

| パス | メソッド | 認証 | 実装ファイル | 役割 |
|---|---|---|---|---|
| `/api/me` | GET | CF Access | `functions/api/me.js` | 認証ユーザー情報返却 + `user:{hash}` を KV に保存 |
| `/api/viewing-statuses` | GET, PUT | CF Access | `functions/api/viewing-statuses/index.js` | 全観覧ステータス取得 / 一括置換（PUT は 1MB 制限） |
| `/api/viewing-statuses/:eventId` | PATCH, DELETE | CF Access | `functions/api/viewing-statuses/[eventId].js` | 単一イベントの観覧ステータス・メモ・remind・excluded 更新/削除 |
| `/api/remind-list` | GET | Bearer `REMIND_API_SECRET` | `functions/api/remind-list.js` | KV 走査して `remind:true` の `{eventId, email}` 一覧を返す |
| `/api/excluded-events` | GET / POST / DELETE | GET: Bearer、POST/DELETE: CF Access | `functions/api/excluded-events.js` | 除外イベント ID リスト管理 |
| `/api/register-request` | POST | Public (bypass) | `functions/api/register-request.js` | Turnstile + IP レート制限 + GitHub dispatch |
| `/api/register-approve` | GET | CF Access + admin | `functions/api/register-approve.js` | Cloudflare Access Rule Group にメール追加 |
| `/api/register-reject` | GET | CF Access + admin | `functions/api/register-reject.js` | KV のみ `rejected` に更新 |
| `/api/talents` | GET, POST, PUT | GET: Bearer or CF Access、POST: CF Access、PUT: Bearer | `functions/api/talents/index.js` | 芸人マスタ一覧取得 / 新規追加 / 全置換 |
| `/api/talents/:talentId` | PATCH, DELETE | PATCH: Bearer、DELETE: CF Access + admin | `functions/api/talents/[talentId].js` | name/image_url 補完 / 物理削除 |
| `/api/user-talents` | GET, PUT | CF Access | `functions/api/user-talents.js` | ユーザー別フォロー talent_ids 取得 / 全置換 |
| `/api/notify-targets` | GET | Bearer `REMIND_API_SECRET` | `functions/api/notify-targets.js` | KV 走査して全ユーザーの `{email, talent_ids}` 一覧を返す（notify.py 用） |

- 認証ユーティリティ: `functions/_lib/auth.js` (`sha256hex` / `getCallerEmail` / `getAdminEmails` / `isAdmin`)
- 呼び出し元メールアドレス: `CF-Access-Authenticated-User-Email` ヘッダーから取得

---

## Workers KV キー構造

バインディング名: `FANABY_VIEWING_STATUSES`（`wrangler.toml` に ID `5b93698258b54a379d7b05c2dafe9739` を設定済み）

| キー | TTL | 値の形式 | 用途 |
|---|---|---|---|
| `status:{sha256(email)}` | なし | `{statuses: {eventId: {status, updated_at, memo, remind, excluded, history[]}}}` | アカウント別観覧ステータスマスタ |
| `user:{sha256(email)}` | なし | `{email, updated_at}` | メールアドレス解決用（`/api/remind-list` / `/api/notify-targets` が参照） |
| `excluded_events` | なし | `{ids: [eventId, ...], updated_at}` | グローバル除外公演 ID リスト |
| `talents` | なし | `{schema_version, talents: [{id, name, image_url, profile_url, added_at, added_by}], updated_at}` | グローバル芸人マスタ |
| `user-talents:{sha256(email)}` | なし | `{schema_version, talent_ids: [...], updated_at}` | ユーザー別フォロー芸人 ID リスト |
| `register-req:{token}` | 24h → 承認時 30d | `{email, created_at, status: pending/approved/rejected}` | 登録申請データ |
| `register-email:{sha256(email)}` | 24h → 承認時 30d | `{token, status, created_at, approved_at?}` | メール重複申請ガード |
| `ratelimit:register:{ip}` | 1h | カウンタ（上限 5 回/h） | 登録申請 IP レート制限 |

---

## Cloudflare Access 構成

- 認証方式: メール OTP（`CF-Access-Authenticated-User-Email` ヘッダーで識別）
- アクセス制御: Rule Group `fanaby-approved-users` に含まれるメールアドレスのみアクセス可
- **bypass パス**（未認証ユーザーがアクセス可能）:
  - `POST /api/register-request`
  - `/register.html`
- `/api/excluded-events` の GET は bypass 配下のため、`CF_Authorization` Cookie の存在で CF Access 認証を判定する代替実装

---

## 登録承認フロー

1. 未認証ユーザーが `/register.html` でメール入力 + Turnstile 回答 → `POST /api/register-request`
2. `register-request.js` が Turnstile 検証 / IP レート制限 / 重複チェック後、トークンを KV 保存 + GitHub `repository_dispatch(register-request)` を発火
3. `notify-register.yml` → `scripts/notify_register.py` が `ADMIN_EMAIL` 宛に承認/拒否リンク付きメールを送信
4. 管理者が CF Access 認証下で `/api/register-approve?token=...` にアクセス（`isAdmin()` で検証）
5. `register-approve.js` が Cloudflare API で Rule Group の `include` にメール追加 + KV を `approved`（TTL 30日）に更新
6. 以降、該当メールアドレスで CF Access OTP ログインが可能になる

拒否時: `/api/register-reject?token=...` が KV を `rejected` に更新するのみ

---

## Cloudflare Pages 必須環境変数

| 変数名 | 用途 |
|---|---|
| `REMIND_API_SECRET` | リマインダー API / 除外イベント API の Bearer 認証 |
| `CF_API_TOKEN` | Cloudflare API 呼び出し（Access:Groups:Edit 権限が必要） |
| `CF_ACCOUNT_ID` | Cloudflare アカウント ID |
| `CF_ACCESS_GROUP_ID` | 承認済みユーザーを管理する Rule Group の ID |
| `ADMIN_EMAILS` | 管理者メールアドレス（カンマ区切り）。`isAdmin()` での検証に使用 |
| `GH_REPO` | GitHub リポジトリ名（例: `owner/repo`）。dispatch の発火先 |
| `GH_DISPATCH_TOKEN` | GitHub Personal Access Token（`repo` スコープ）。dispatch 用 |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile シークレット。未設定時は検証スキップ |
| `TURNSTILE_SITE_KEY` | Turnstile サイトキー（`docs/register.html` に埋め込み済み） |

---

## 初回セットアップ手順（別環境への移行・再構築時）

1. **KV namespace の作成**
   - Cloudflare ダッシュボード → Workers & Pages → KV → 新規作成
   - 名前: `FANABY_VIEWING_STATUSES`（任意）
   - 発行された ID を `wrangler.toml` の `id` に設定

2. **Pages プロジェクトへの KV バインディング追加**
   - Pages → Settings → Functions → KV namespace bindings
   - 変数名: `FANABY_VIEWING_STATUSES`（`wrangler.toml` の `binding` 値と一致させる）

3. **Pages 環境変数の設定**
   - 上記「必須環境変数」表の全項目を Settings → Environment variables に追加
   - Production / Preview 両方に設定する

4. **Cloudflare Access Rule Group の作成**
   - Zero Trust → Access → Groups で新規グループを作成
   - グループ ID を `CF_ACCESS_GROUP_ID` に設定
   - Access Application のポリシーにこのグループを含める

5. **デプロイ & 疎通確認**
   - GitHub Actions の `main.yml` を手動実行（workflow_dispatch + skip_scrape=true）
   - `/api/me` にアクセスしてレスポンスが返ることを確認

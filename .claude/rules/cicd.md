---
paths: .github/workflows/**/*
---

# CI/CD — GitHub Actions

## ワークフロー一覧

### `main.yml` — スクレイプ & デプロイ

| 項目 | 値 |
|---|---|
| トリガー | `cron: "3 0,8 * * *"`（JST 9:03 / 17:03）/ `workflow_dispatch`（`skip_scrape` フラグあり） |
| 権限 | `contents: write`, `deployments: write` |

実行ステップ（順序）:
1. checkout
2. Python 3.11 セットアップ
3. Chrome インストール（`skip_scrape=false` 時のみ）
4. `pip install -r requirements.txt`
5. `python scripts/scrape_profile_api.py`
6. `python scripts/scrape_theater_api.py`
7. `python scripts/merge.py`
8. `python scripts/notify.py`
9. `python scripts/build.py`（`skip_scrape=true` でも実行）
10. `git add data/events.json docs/index.html docs/fliers/` → commit & push
11. `cloudflare/pages-action@v1` で `docs/` を Cloudflare Pages にデプロイ

使用 Secrets / Variables:

| ステップ | Secrets / Variables |
|---|---|
| merge.py | `REMIND_API_URL`, `REMIND_API_SECRET` |
| notify.py | `MAIL_USER`, `MAIL_PASS`, `MAIL_TO` |
| デプロイ | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `GITHUB_TOKEN`（自動提供） |

---

### `remind-check.yml` — チケットリマインドチェック & 送信

| 項目 | 値 |
|---|---|
| トリガー | 複数 cron（JST 8:45〜22:45 の毎時）/ `workflow_dispatch` |
| 権限 | `contents: write`, `deployments: write` |

cron 設定:
```
"45 23 * * *"        # JST 8:45
"45 0,3,7,10,13 * * *"  # JST 9:45 / 12:45 / 16:45 / 19:45 / 22:45
```

実行ステップ（順序）:
1. checkout
2. Python 3.11 セットアップ
3. `pip install requests beautifulsoup4 python-dotenv`
4. `python scripts/scrape_ticket.py`
5. `python scripts/build.py`
6. `git add data/ticket_deadlines.json docs/index.html` → commit & push
7. `cloudflare/pages-action@v1` でデプロイ
8. `python scripts/remind.py`（デプロイ後に送信）

使用 Secrets:

| ステップ | Secrets |
|---|---|
| scrape_ticket.py | `REMIND_API_URL`, `REMIND_API_SECRET`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` |
| remind.py | `MAIL_USER`, `MAIL_PASS`, `REMIND_API_URL`, `REMIND_API_SECRET`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` |
| デプロイ | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `GITHUB_TOKEN`（自動提供） |

---

### `talent-added.yml` — 新規芸人追加時の即時スクレイプ

| 項目 | 値 |
|---|---|
| トリガー | `repository_dispatch: [talent-added]`（`/api/talents` POST から発火） |
| 権限 | `contents: write`, `deployments: write` |

実行ステップ（順序）:
1. checkout
2. Python 3.11 セットアップ
3. `pip install requests python-dotenv`（Chrome 不要）
4. `python scripts/scrape_profile_api.py`（名前・画像・スケジュール取得）
5. `python scripts/scrape_theater_api.py`
6. `python scripts/merge.py`
7. `python scripts/notify.py`（新規公演をユーザー別に通知）
8. `python scripts/build.py`
9. `git add data/events.json docs/index.html docs/fliers/` → commit & push
10. `cloudflare/pages-action@v1` でデプロイ

使用 Secrets:

| ステップ | Secrets |
|---|---|
| scrape_*.py / merge.py / build.py | `REMIND_API_URL`, `REMIND_API_SECRET` |
| notify.py | `MAIL_USER`, `MAIL_PASS`, `MAIL_TO`, `REMIND_API_URL`, `REMIND_API_SECRET` |
| デプロイ | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `GITHUB_TOKEN`（自動提供） |

発火元: `functions/api/talents/index.js` の POST ハンドラ（KV 保存成功後、`GH_REPO` / `GH_DISPATCH_TOKEN` が設定されている場合のみ）
レスポンス: `{ ok: true, talent: {...}, scrape_triggered: true/false }`

---

### `notify-register.yml` — 登録申請通知

| 項目 | 値 |
|---|---|
| トリガー | `repository_dispatch: [register-request]`（`/api/register-request` から発火） |
| 権限 | `contents: read` |

実行ステップ:
1. checkout
2. Python 3.11 セットアップ
3. `pip install python-dotenv`
4. `python scripts/notify_register.py`

使用 Secrets / Variables:

| Secrets | Variables |
|---|---|
| `MAIL_USER`, `MAIL_PASS`, `ADMIN_EMAIL` | `SITE_ORIGIN` |

- `REQ_TOKEN` / `REQ_EMAIL` は `github.event.client_payload` から直接取得（Secrets 登録不要）

---

## GitHub Secrets 一覧

| 種別 | Name | 利用ワークフロー | 利用スクリプト | 用途 |
|---|---|---|---|---|
| Secret | `MAIL_USER` | main / notify-register / remind-check | notify.py / notify_register.py / remind.py | Gmail SMTP 送信元アカウント |
| Secret | `MAIL_PASS` | main / notify-register / remind-check | notify.py / notify_register.py / remind.py | Gmail アプリパスワード（SMTP 認証） |
| Secret | `MAIL_TO` | main | notify.py | スケジュール更新通知の宛先メール |
| Secret | `ADMIN_EMAIL` | notify-register | notify_register.py | 登録承認リクエスト通知の管理者宛先メール |
| Secret | `CLOUDFLARE_API_TOKEN` | main / remind-check | ー | Cloudflare Pages デプロイ用 API トークン |
| Secret | `CLOUDFLARE_ACCOUNT_ID` | main / remind-check | ー | Cloudflare アカウント ID（デプロイ用） |
| Secret | `REMIND_API_URL` | main / remind-check | merge.py / remind.py / scrape_ticket.py | リマインダー API エンドポイント URL |
| Secret | `REMIND_API_SECRET` | main / remind-check | merge.py / remind.py / scrape_ticket.py | リマインダー API 認証シークレット |
| Secret | `CF_ACCESS_CLIENT_ID` | remind-check | remind.py / scrape_ticket.py | Cloudflare Access サービストークン（ID） |
| Secret | `CF_ACCESS_CLIENT_SECRET` | remind-check | remind.py / scrape_ticket.py | Cloudflare Access サービストークン（シークレット） |
| Variable | `SITE_ORIGIN` | notify-register | notify_register.py | サイトのオリジン URL（承認リンク生成に使用） |

### 未使用 Secrets（削除候補）

以下は現在のコードに参照が無い。用途不明なら削除を推奨。

| Name | 備考 |
|---|---|
| `GH_PAT` | コード内に参照なし |
| `GSHEET_CREDENTIALS_JSON` | コード内に参照なし |
| `GSHEET_URL` | コード内に参照なし |

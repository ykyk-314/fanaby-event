---
paths: "**/*"
---

# Phase 2 タスク

**大前提: 無料・無課金で完結すること（最重要制約）**

---

## ✅ 完了済み

### A. 端末間ステータス同期（P2-account）
- Cloudflare Access + Pages Functions + KV によるアカウント別ステータス管理を実装
- `ViewingStorage` が LocalStorage ↔ `/api/viewing-statuses` を透過的に同期
- KVキー: `status:{sha256(email)}`（メールアドレスをKVに平文保存しない）
- API: `GET/PATCH/DELETE /api/viewing-statuses/:eventId`、`GET /api/me`

### E. 検索機能の拡充（P2-Search-Condition）
- 公演名・出演者のキーワード検索（スペース区切りAND）を実装
- フィルターバーにキーワード入力欄を追加
- `data-title` / `data-members` 属性を使った DOM フィルタ

### F. コメント機能（P2-Comment）
- 公演カードにメモ欄（textarea）を追加
- 1秒デバウンスで自動保存（LocalStorage → KV 同期）

### B. チケット販売期間リマインダー通知（P2-ticket-reminder）
- fany.lol からチケット受付期間をスクレイピング（requests + BeautifulSoup）
- `data/ticket_deadlines.json` に保存し、公演カードに受付種別・期間を表示
- 通知条件:
  - 先行抽選 受付開始 2時間前
  - 先行抽選 受付終了 2時間前
  - 一般発売 受付開始 1時間前
- GitHub Actions `remind-check.yml` が JST 8:45〜22:45 の1時間ごとに実行
- リマインドON/OFF ボタンを公演カードに追加
- フィルターバーに「🔔 通知ONのみ」チェックボックスを追加
- `functions/api/remind-list.js` で KV を走査してリマインドON の公演IDリストを返す
- GitHub Secrets に `REMIND_API_URL` / `REMIND_API_SECRET` を追加済み
- CloudFlareのPages に環境変数 `REMIND_API_SECRET`を設定済み

---

## 未実装（残タスク）

### C. 対象芸人の追加UI

- **方針:** Web UI 上で `data/config.json` の `talents[]` を追加・管理
- 依存: A（Workers 実装）✅ 完了済みのため着手可
- 現状回避策: `data/config.json` を直接編集
- 実装が必要なもの: KV または GitHub API 経由での `config.json` 書き込みAPI

### D. Googleカレンダー連携

- **方針:** `purchased` ステータスの公演を自動でGoogleカレンダーに登録
- OAuth 認証フローが必要（個人用でも実装コストが最も高い）
- 無料範囲内だが優先度は最低

---

## 実装ロードマップ

```
✅ 完了  E（検索拡充）・F（コメント）・A（端末間同期）・B（リマインダー）
  ↓
中期    C（芸人追加UI）  ← A 完了済みのため着手可
  ↓
長期    D（Googleカレンダー）
```

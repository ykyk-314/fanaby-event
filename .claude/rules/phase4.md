# Phase 4 タスク

**大前提: 無料・無課金で完結すること（最重要制約）**

Phase 2 / Phase 3 の完了後に残った未実装タスクを整理。
対応順序に希望はない。効率的に対応できる順番で設計・実装を進める。

---

## A. アカウント別芸人登録 ✅ 実装完了

**背景**: 現在はサービス固定で `data/config.json` の `talents[]` に登録した芸人を全ユーザー共通で取得している。ログインアカウントごとに対象芸人を選択できるようにしたい。

**実装済み内容**:

| レイヤー | 実装 |
|---|---|
| 芸人マスタ（KV） | `functions/api/talents/index.js` GET/POST/PUT、`functions/api/talents/[talentId].js` PATCH/DELETE |
| ユーザー別フォロー（KV） | `functions/api/user-talents.js` GET/PUT、KVキー `user-talents:{sha256(email)}` |
| 設定UI | `docs/settings.html` + `docs/assets/settings.js`（FollowStorage: LocalStorage↔KV透過同期） |
| スクレイプ連携 | `scripts/_talents_kv.py`（全スクリプトが KV から芸人マスタ取得、config.json フォールバック） |
| 新規追加時即時スクレイプ | `.github/workflows/talent-added.yml`（POST /api/talents 成功後に GitHub dispatch） |
| ユーザー別通知 | `scripts/notify.py`（`/api/notify-targets` から芸人別にメール送信） |

**設定ページ機能**（`docs/settings.html`）:
- フォロー中の芸人一覧 + 解除ボタン
- グローバルマスタから選択してフォロー追加
- プロフィール URL 入力でマスタへ新規登録 → 自動フォロー追加（409 の場合はフォローのみ追加）

**現状の芸人マスタ**（KV `talents` キー: 5件）:
| ID | 名前 |
|---|---|
| 10708 | シンクロニシティ |
| 5114 | マユリカ |
| 7295 | ケビンス |
| （ID未確認） | kento fukaya |
| （ID未確認） | ビスケットブラザーズ |

**未着手の要件**:
- 芸人名でのキーワード検索・候補一覧表示（現状は profile.yoshimoto.co.jp で調べてURL入力が必要）

---

## B. ピックアップ公演取得 ❌ 未着手

**背景**: 現在はマスタ登録芸人が出演する公演しか取り込めない。特定の公演や芸人を個別に取り込みたいケースに対応したい。

**要件**:
- 公演名またはアーティスト名で検索し、個別公演情報を取り込む
- 取り込んだ公演は `events.json` に追加され、通常公演と同様に表示・管理される

**検討事項**:
- feed-api (`/fany/tickets/v2` または `/fany/theater/v1`) で検索 API が存在するか（未調査）
- 手動追加 UI の設計（管理者専用か全ユーザー可か）

---

## C. LINE 通知 / Web Push 通知 ❌ 未着手

**背景**: 現在のメール通知を LINE 通知や Push 通知に置き換えたい。

**現状の通知手段**: Gmail SMTP（`notify.py`）のみ

**要件**:
- ユーザーが LINE 情報（notify token など）を登録できる UI
- 通知送信時: LINE 登録ありなら LINE 通知、なければメール通知（フォールバック）

**制約**: **LINE 連携が課金必須なら断念**。完全無料・無課金での実装が可能な場合のみ進める。

**検討事項**:
- LINE Notify は 2025 年 3 月にサービス終了済み → 使用不可
- LINE Messaging API の無料枠（月 200 通）で代替可能か要調査
- 無料代替: Web Push（Service Worker + VAPID）への変更も検討対象
  - PWA 基盤はすでに存在（`site.webmanifest`, `icon-192.png`, `icon-512.png`）
  - Cloudflare Workers / KV で Push サブスクリプション管理が可能（無料枠内）

---

## D. Google カレンダー連携（優先度: 低）⚠️ 手動ボタンのみ実装済み

**背景**: `purchased`（購入済み）ステータスの公演を Google カレンダーに登録したい。

**実装済み**:
- `build.py:98` `make_gcal_url()` — 全公演カードに「📅」ボタンを生成
- クリックすると Google カレンダーの予定追加ページが開く（手動での一件ずつ追加）

**未実装**:
- `purchased` にステータス変更した瞬間に自動登録する仕組み
- OAuth 2.0 フロー（実装コスト最大）

**制約**: 無料範囲内だが実装コストが最も高い。手動ボタンで代替できているため優先度は最低。

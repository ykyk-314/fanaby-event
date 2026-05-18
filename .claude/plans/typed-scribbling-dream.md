# Phase 4-A: アカウント別芸人登録

## Context

現在、`data/config.json` の `talents[]` に登録された 3 組の芸人を全ユーザー共通でスクレイプ・通知している。これを以下に変更する：

- 芸人マスタを Cloudflare KV に移行し、ログインユーザーが追加可能にする（追加は誰でも可・物理削除は管理者のみ）
- ユーザーごとに「フォロー芸人」を選択でき、通知・タブ表示はフォロー芸人に基づく
- 新規追加は「よしもとプロフィール URL」を入力する方式。芸人名・プロフィール画像は API で取得できないため、次回 CI 実行時にプロフィールページをスクレイプして補完する
- フォロー 0 件のユーザーには空表示＋設定への案内を出す（既存 3 芸人を強制フォローはしない）

実装範囲が広いため 5 ステップに分け、ステップごとに動作確認しながら進める。

---

## データ設計

### KV キー（既存の `FANABY_VIEWING_STATUSES` namespace を再利用）

| キー | 値 | 備考 |
|---|---|---|
| `talents` | `{schema_version, talents: [{id, name, image_url, profile_url, added_at, added_by}], updated_at}` | グローバルマスタ。`excluded_events` と同じ単一キー方式 |
| `user-talents:{sha256(email)}` | `{schema_version, talent_ids: [...], updated_at}` | ユーザー別フォロー。`status:{hash}` と同パターン |

- `name` / `image_url` は初回登録時は `null`、次回 CI で補完
- `added_by` は監査用のメールアドレス（誰が追加したかをログとして残すのみ）
- `profile_url` は再スクレイプ用に保持

### config.json の扱い

- `talents[]` は **削除せず空配列にする**（フォールバック・後方互換のため残す）
- 既存 3 芸人は手動で KV `talents` に投入する（migration）

---

## API 設計（新規 Functions）

### `/api/talents/index.js` — マスタ CRUD

| メソッド | 認証 | 役割 |
|---|---|---|
| GET | CF Access **または** Bearer | マスタ一覧返却。Bearer はスクリプト用（既存 `REMIND_API_SECRET` 流用） |
| POST | CF Access | 新規追加。`{ url または id, name? }` を受け取り、URL から ID 抽出 → 重複チェック → KV に追加 |
| PUT | Bearer | マスタ全体更新（スクリプトによる name/image_url 補完用） |

### `/api/talents/[talentId].js` — 個別操作

| メソッド | 認証 | 役割 |
|---|---|---|
| PATCH | Bearer | name/image_url 補完（スクリプト用） |
| DELETE | CF Access + `isAdmin` | マスタから物理削除 |

### `/api/user-talents.js` — ユーザー別フォロー

| メソッド | 認証 | 役割 |
|---|---|---|
| GET | CF Access | 自分のフォロー talent_ids 取得（未登録なら `{talent_ids: []}` 返却） |
| PUT | CF Access | フォロー全置換 `{ talent_ids: [...] }` |

### バリデーション

- `TALENT_ID_RE = /^\d+$/`（feed-api のIDは数値文字列）
- URL からの ID 抽出: `/[?&]id=(\d+)/` で `profile.yoshimoto.co.jp/talent/detail?id=XXXX` を解析
- `talent_ids` 配列は最大 50 件（KV 肥大化防止）

### 再利用するパターン（既存コード）

| 関数 | 場所 |
|---|---|
| `sha256hex` | `functions/_lib/auth.js` を import |
| `getCallerEmail` / `isAdmin` | `functions/_lib/auth.js` |
| Bearer 認証パターン | `functions/api/excluded-events.js` の `isBearerAuthorized` |
| GET/PUT ペアの実装 | `functions/api/viewing-statuses/index.js` |
| 個別操作（PATCH/DELETE） | `functions/api/viewing-statuses/[eventId].js` |

---

## フロントエンド設計

### 新規 `docs/settings.html`

ヘッダー（既存ユーザーアバター流用）＋以下のセクション：

```
[フォロー中の芸人]
  [画像] シンクロニシティ  [解除]
  [画像] マユリカ          [解除]

[マスタから追加]
  □ ケビンス
  □ ○○（他のユーザーが追加した芸人）
  [選択した芸人を追加]

[新規追加（マスタへ）]
  プロフィール URL: [_________]
  例: https://profile.yoshimoto.co.jp/talent/detail?id=10708
  [追加] → 名前と画像は次回更新（最大9時間後）で反映されます
```

### `docs/assets/settings.js`

`ViewingStorage` を雛形に `FollowStorage` を実装：
- LocalStorage キー: `fanaby_follow_talents`
- `/api/user-talents` GET/PUT で同期
- `/api/talents` GET でマスタ取得
- `/api/talents` POST で新規追加

### `docs/index.html` の変更（build.py 経由）

1. ヘッダーに「⚙ 設定」リンクを追加
2. タブは全マスタ芸人分を生成（build.py が KV からマスタを取得して生成）
3. JS 側で動的に非表示にする

### `docs/assets/script.js` の変更

`initFollowFilter()` を新規追加：
1. `/api/user-talents` を fetch して `followedTalents = [...]` 取得
2. `data-tab` がフォロー外の `.tab-btn` を `display:none`
3. `applyFilters()` の判定に追加: 「全員」タブでも `card.dataset.talent.split(' ').some(t => followedTalents.includes(t))` を要件にする
4. フォロー 0 件なら結果カウントエリアに「設定からフォロー芸人を追加してください」案内表示

---

## バックエンド（Python スクリプト）の変更

既存の `REMIND_API_URL` / `REMIND_API_SECRET` 環境変数を流用して `/api/talents` `/api/user-talents` を叩く。

### `scripts/scrape_profile_api.py`

1. 起動時に `GET /api/talents`（Bearer）でマスタ取得
2. config.json の talents[] は無視（または空フォールバック）
3. 各 talent をループして feed-api で公演取得
4. **name または image_url が null の talent について**:
   - `https://profile.yoshimoto.co.jp/talent/detail?id={id}` を `requests` で fetch
   - HTML から `<title>` や `<meta property="og:image">` を抽出
   - `PATCH /api/talents/{id}` で KV を更新
5. 失敗時は null のまま残す（次回再挑戦）

### `scripts/scrape_theater_api.py`

- 起動時に `GET /api/talents` でマスタ取得
- `talent_ids = {t["id"] for t in master["talents"]}` に変更

### `scripts/merge.py`

- `build_events_from_theater()` の `talent_map` を KV マスタから構築
- `talent_map = {t["id"]: t["name"] or t["id"] for t in master["talents"]}`（name 未確定なら ID を仮表示）

### `scripts/build.py`

- `talents = master["talents"]` で KV から取得
- タブ生成は同様（順序: マスタの登録順）
- ヘッダーに「⚙ 設定」リンク追加

### `scripts/notify.py`（最大の変更）

現状: 単一の `MAIL_TO` に全芸人ぶん送信
変更: ユーザー別にフィルタリングして各ユーザーのメールに送信

実装：
1. KV を走査して全 `user:{hash}` キーをリスト（既存の `/api/remind-list` パターン参考）
2. 各ユーザーについて `user-talents:{hash}` を取得
3. 該当ユーザーがフォロー中の芸人の通知のみ抽出して送信
4. フォロー 0 件のユーザーには何も送らない
5. `MAIL_TO` フォールバックは廃止（または管理者用に残す）

新規 API: `GET /api/notify-targets`（Bearer）— 全ユーザーの `{email, talent_ids}` を返す。

---

## 実装ステップ（5段階）

各ステップ完了後に動作確認し、問題なければ次へ。

### Step 1: KV スキーマ + Functions API

- `functions/api/talents/index.js`, `functions/api/talents/[talentId].js`, `functions/api/user-talents.js` を新規作成
- KV `talents` に既存 3 芸人を手動投入（Cloudflare ダッシュボードから）
- 各 API を curl/Postman で疎通確認

### Step 2: settings.html UI

- `docs/settings.html`, `docs/assets/settings.js` を新規作成
- ブラウザで動作確認：マスタ取得・フォロー追加/解除・新規追加（name=null のまま登録できることを確認）

### Step 3: スクレイプスクリプトの KV 対応

- `scripts/scrape_profile_api.py`: KV からマスタ取得 + プロフィールページから name/image_url を補完
- `scripts/scrape_theater_api.py`: KV からマスタ取得
- `scripts/merge.py`: KV からマスタ取得
- `scripts/build.py`: KV からマスタ取得（タブ生成）
- CI 手動実行で `data/events.json` が正しく生成されることを確認

### Step 4: index.html のユーザー別タブ制御

- `docs/assets/script.js` に `initFollowFilter()` 追加
- 各種フォロー状態で正しいタブ・カードが表示されることを確認
- ゼロフォロー時の案内表示

### Step 5: ユーザー別メール通知

- `functions/api/notify-targets.js` 新規作成（Bearer 認証で全ユーザーのフォロー一覧返却）
- `scripts/notify.py`: ユーザー別フィルタ + 各メールアドレス宛送信
- 既存の `MAIL_TO` 環境変数は管理者用（送信エラー通知）として残す or 廃止

---

## 修正・新規作成ファイル一覧

### 新規

| パス | 内容 |
|---|---|
| `functions/api/talents/index.js` | マスタ GET/POST/PUT |
| `functions/api/talents/[talentId].js` | PATCH/DELETE |
| `functions/api/user-talents.js` | ユーザー別フォロー GET/PUT |
| `functions/api/notify-targets.js` | 通知用 Bearer API |
| `docs/settings.html` | フォロー芸人管理画面 |
| `docs/assets/settings.js` | settings.html の JS |
| `.claude/rules/phase4-a.md` | Phase 4-A 仕様書（実装後の参照用） |

### 変更

| パス | 変更内容 |
|---|---|
| `scripts/scrape_profile_api.py` | KV マスタ取得 + プロフィールページから name/image_url 補完 |
| `scripts/scrape_theater_api.py` | KV マスタ取得 |
| `scripts/merge.py` | KV マスタ取得 |
| `scripts/build.py` | KV マスタ取得 + 設定リンク追加 |
| `scripts/notify.py` | ユーザー別フィルタリング + 個別メール送信 |
| `docs/assets/script.js` | `initFollowFilter()` 追加・タブ動的制御・ゼロフォロー案内 |
| `data/config.json` | `talents[]` を空配列に（既存設定はKVへ移行済み） |

---

## 検証手順

### Step 1 検証
```
curl -H "Authorization: Bearer $REMIND_API_SECRET" https://fanaby-event.pages.dev/api/talents
→ { talents: [{id:"10708", name:"シンクロニシティ", ...}, ...] }
```

### Step 2 検証
- `/settings.html` を開く
- 既存芸人がマスタに表示される
- 新規 URL を追加できる（name=null で）
- フォロー追加/解除が KV に反映される

### Step 3 検証
- GitHub Actions の `main.yml` を手動実行
- `data/events.json` が正しく生成される
- name=null の芸人が次回実行で補完される

### Step 4 検証
- フォロー 2 芸人時：その 2 タブのみ表示、全員タブはその 2 芸人の公演のみ
- フォロー 0 件時：案内表示
- フォロー解除即時反映

### Step 5 検証
- 複数ユーザーで異なるフォロー設定 → 各自に該当芸人ぶんのみメール届く

---

## 既知のリスク・トレードオフ

- **プロフィールページのスクレイプが Bot ブロックされる可能性**: その場合は手動で KV を編集して名前・画像を補完するフローを案内
- **KV 書き込み頻度**: name/image_url 補完は CI 実行ごとに走るが、変更があった芸人のみ PATCH するので問題なし
- **GitHub Actions のスクリプトが Pages API に依存**: Pages 側がダウンしているとスクレイプも失敗。既存の `/api/excluded-events` 取得と同じ依存度
- **複数ユーザー通知での Gmail 送信制限**: 無料 Gmail は 1日 500通制限。ユーザー数が増えたら別 SMTP 検討
- **マスタの追加上限なし**: 悪意のあるユーザーが大量追加するリスクは現状ない（CF Access で限定された友達のみ）が、必要なら将来追加件数制限を入れる

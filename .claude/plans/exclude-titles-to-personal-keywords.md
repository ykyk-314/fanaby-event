# 除外タイトルの個人設定化

## Context

現状、除外公演は `data/config.json` の `exclude_titles`（17件）で管理され、`scripts/merge.py:376-384` がタイトル部分一致でヒットした公演を **ビルド時に全ユーザー共通で** `events.json` から完全除去している。これを **ユーザーごとの個人除外キーワード** に移行し、各自が自分の除外リストを持てるようにする。

- グローバル `exclude_titles` は廃止し、完全に個人設定へ一本化する
- 除外判定は現状通り「タイトル部分一致」
- 現行17件は「全ユーザーの初期値」として引き継ぐ
- 除外は **一覧表示（index.html）とメール通知（notify.py）の両方** に反映する

この機能はプロジェクト既存の per-user 基盤（Cloudflare KV + Pages Functions、`/api/user-talents` と同型）を踏襲して実装する。

## 設計の要点: デフォルト17件の単一ソース

デフォルトキーワードは「フロント表示（script.js）」「設定UI（settings.js）」「通知（notify.py の直接KVパス）」の3系統で必要。3系統すべてが到達できる媒体は **KV のみ**（Functions は `data/config.json` を読めず、Python 直接KVパスは JS 定数を読めない）。

- **真実源 = KV グローバルキー `exclude-keywords-default`**（スキーマ `{schema_version:1, keywords:[...], updated_at}`）
- **起源となる17件 = `scripts/_talents_kv.py` の Python 定数 `DEFAULT_EXCLUDE_KEYWORDS`**（seed 専用、runtime では使わない）
- `merge.py` 起動時に `ensure_default_exclude_keywords()` が KV に無ければ1回だけ seed（冪等）。以後 KV が真実源

これは既存 `talents`（KV 真実源 + config.json フォールバック）と同型。既存 `_get_kv_json`/`_put_kv_json`（`_talents_kv.py:33,50`）を流用する。

## 実装手順（依存順）

### 1. KV seed 基盤 — `scripts/_talents_kv.py`
- `DEFAULT_EXCLUDE_KEYWORDS = [...]`（現行 config.json の17件をコピー）
- `ensure_default_exclude_keywords()`: `_get_kv_json(..., "exclude-keywords-default")` が無ければ `_put_kv_json` で seed
- `fetch_default_exclude_keywords() -> list[str]`: KV `exclude-keywords-default` の `keywords` を返す（無ければ `[]`）

### 2. 新API — `functions/api/user-exclude-keywords.js`（新規）
`functions/api/user-talents.js` を雛形にコピー。差分:
- `KV_PREFIX='user-exclude-keywords:'`、`DEFAULT_KEY='exclude-keywords-default'`、`MAX_KEYWORDS=100`、`MAX_KW_LEN=100`
- **GET**: `getCallerEmail`→401判定。ユーザーキーがあれば返す。無ければ `exclude-keywords-default` を読み `{schema_version:1, keywords:<default ?? []>, updated_at:null, is_default:true}` を返す（`updated_at:null` により後述のフロント同期で「ユーザー編集が常に勝つ」）
- **PUT** body `{keywords:[...]}`: 配列/件数/型を検証 → `trim`→空除去→`MAX_KW_LEN`検証→`Set`で重複除去 → `{schema_version:1, keywords, updated_at}` 保存
- `sha256hex`/`getCallerEmail`（`functions/_lib/auth.js`）と `json()` ヘルパを流用

### 3. notify-targets 拡張（各ユーザーの除外キーワードを配る）
- `functions/api/notify-targets.js`: ループ前に `exclude-keywords-default` を1回読み `defaultKw` に。ループ内で `user-exclude-keywords:{hash}` を引き、無ければ `defaultKw`。`targets.push({email, talent_ids, exclude_keywords})`
- `scripts/_talents_kv.py:fetch_notify_targets_kv()`（252-277行）: 同型に `exclude_keywords` を各 target に付与

### 4. 通知フィルタ — `scripts/notify.py`
- ユーザー別分岐（`main()` 309-334行）: `user_events` 構築直後に
  ```python
  exclude_keywords = target.get("exclude_keywords", [])
  if exclude_keywords:
      user_events = [ev for ev in user_events
                     if not any(kw in (ev.get("title") or "") for kw in exclude_keywords)]
  if not user_events:
      continue
  ```
  （`kw in title` の部分一致・大小区別あり = merge.py 旧挙動と一致）
- フォールバック分岐（MAIL_TO, 335-358行）: `fetch_default_exclude_keywords()` で得たデフォルトで `notify_events` を同様フィルタ

### 5. グローバル除外の削除 — `scripts/merge.py` / `data/config.json`
- **前提: 手順2・3のデプロイと手順1の seed 完了後に実施**（config を先に消すと除外が全消失する空白期間が生じる）
- `merge.py:376-384` の除外フィルタブロックを削除
- `merge.py:main()` 冒頭（config 読込直後, 350行付近）に `ensure_default_exclude_keywords()` を追加
- `data/config.json:7-26` の `exclude_titles` を削除

### 6. フロント表示フィルタ — `docs/assets/script.js`
- グローバル変数 `let excludeKeywords = [];`（16行付近）
- `initExcludeFilter()`: `fetch('/api/user-exclude-keywords')` → `excludeKeywords = data.keywords`（`initFollowFilter` 583行を参考）
- init IIFE（649行）の `Promise.all([...])` に `initExcludeFilter()` を追加
- `applyFilters()` の `excludedOk`（143行）を差し替え:
  ```js
  const title = c.dataset.title || '';
  const kwExcluded = excludeKeywords.length > 0 && excludeKeywords.some(kw => title.includes(kw));
  const excludedOk = showExcluded || (c.dataset.excluded !== 'true' && !kwExcluded);
  ```
  → 既存の「除外済み表示」チェックボックス（`filterShowExcluded`）でキーワード除外分もまとめて表示可能。UI追加不要

### 7. 設定UI — `docs/settings.html` / `docs/assets/settings.js`
- **settings.html**: 「フォロー中の芸人」セクション直後に `.settings-section` を1つ追加（h2「除外キーワード」+ `#excludeKeywordList` + `.add-form`（`#addKeyword`/`#addKeywordBtn`）+ `#keywordMsg`）。既存クラス `.add-form`/`.btn-add`/`.status-msg`/`.empty-msg` を流用
- **settings.js**: `FollowStorage`（6-90行）を雛形に `ExcludeKeywordStorage` を追加
  - `LS_KEY='fanaby_exclude_keywords'`、`_fetchRemote→/api/user-exclude-keywords`、`_putRemote→PUT {keywords}`
  - `init()` は FollowStorage と同じ updated_at 比較（新規ユーザーは remote `updated_at:null` + local `null` → `!local.updated_at` が真でデフォルト採用。編集後は local 保持）
  - `getKeywords/setKeywords(trim+空除去+dedupe)/addKeyword/removeKeyword`
  - `renderExcludeKeywords()`（`renderFollowedList` 参考。キーワードは **`textContent`** で挿入しXSS防止。空は `.empty-msg`）
  - `handleAddKeyword()`/`handleRemoveKeyword(kw, btn)`（`handleFollow`/`handleUnfollow` 踏襲）
  - 初期化 IIFE（319行）の `Promise.all` に `ExcludeKeywordStorage.init()` を追加し `renderExcludeKeywords()` 呼び出し

### 8. ドキュメント更新（`.claude/rules/`）
- **data.md**: config.json スキーマから `exclude_titles` 削除。除外がユーザー別KVへ移行した旨を追記
- **cloudflare.md**: API表に `/api/user-exclude-keywords`（GET/PUT, CF Access）追加。`/api/notify-targets` を `{email, talent_ids, exclude_keywords}` に更新。KV表に `user-exclude-keywords:{sha256(email)}` と `exclude-keywords-default` 追加
- **frontend.md**: 「除外済み表示」にキーワード除外を含む旨、settings セクション追加、`ExcludeKeywordStorage` / LocalStorage キー `fanaby_exclude_keywords` を追記
- **scripts.md**: `merge.py` 書き込みルールから `exclude_titles` 記述削除。`notify.py` に「ユーザー別 exclude_keywords でタイトル部分一致除外」追記

## 既知の副作用（実装時に確認）

`merge.py` のグローバル除外を外すと、旧17件該当公演（平日公演・寄席など件数が多い可能性）が `events.json` に流入し、`download_flyers`（398行）がそれらのフライヤーもDL・コミットする → **リポジトリ肥大・帯域増**（無課金制約に影響しうる）。

- 推奨: **(a) 受容**（要件に忠実・最もシンプル）
- 初回ビルドで `docs/fliers/` の増加量を確認し、過大なら flyer DL のみデフォルトキーワードでスキップする対策を後追い検討

通知面は、流入公演が status=new でも各ユーザーのデフォルト17件キーワードで弾かれるため実質通知されない（問題なし）。

## 検証

1. **API疎通**（デプロイ後）: `GET /api/user-exclude-keywords` が未設定ユーザーにデフォルト17件を返す。`PUT` 後に反映されることを確認
2. **seed**: `merge.py` を1回実行し KV `exclude-keywords-default` に17件が入ることを確認（config 削除前）
3. **表示**: 設定画面でキーワードを追加/削除 → index.html を再読込し、該当公演が非表示になる／「除外済みを表示」で再表示されることをブラウザで確認
4. **通知**: notify.py をローカル実行（またはCI）し、デフォルト該当公演が各ユーザーのメールから除外されることをログで確認
5. CI（main.yml）でスクレイプ→merge→notify→build の一連が回ること

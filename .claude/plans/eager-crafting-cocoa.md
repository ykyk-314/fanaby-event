# 定常公演の一括／劇場指定除外

## Context

前回の実装で「除外キーワード」を個人設定化したが、それは単純な自由記述キーワードのフラットリストだった。今回、ユーザーから「定常公演」（劇場が主催し月内に何度も＝ほぼ毎日/毎週開催される寄席・冠番組）を、①一括で全劇場分除外する、②劇場を指定してその劇場分だけ除外する、という2モードで扱いたいという要望が来た。加えて既存の「任意のタイトルを除外する」（自由記述）は残し、併用できるようにする。

定常公演かどうかはタイトルパターンでしか判定できない（イベントデータに「種別」フラグは無い）ため、`feed-api.yoshimoto.co.jp/fany/theater/v1` から12劇場分の生スケジュール（未フィルタ）を実際に取得し、2ヶ月間で高頻度出現するタイトルを分析して、劇場ごとの定常公演キーワードカタログを確定した（ユーザーとの対話で確認済み）。このカタログはコード内の固定カタログとして持ち、ユーザーはチェックボックスで「使う/使わない」を選ぶだけで、キーワード自体を編集する UI は設けない。

## 確定した劇場別キーワードカタログ

```python
STANDING_SHOW_KEYWORDS_BY_VENUE = {
    "渋谷よしもと漫才劇場":        ["渋谷マンゲキお笑いライブ", "渋谷Kiwami極"],
    "神保町よしもと漫才劇場":      ["神保町マンゲキお笑いライブ", "神保町Kakeru翔"],
    "ルミネtheよしもと":          ["の部", "夏休み特別公演", "お盆特別興行", "シルバーウィーク特別公演"],
    "YOSHIMOTO ROPPONGI THEATER": ["六本木お笑いコントライブ", "六本木コントライブ"],
    "大宮ラクーンよしもと劇場":    ["大宮ラクーンよしもと寄席"],
    "よしもと幕張イオンモール劇場": ["幕張平日ネタ", "幕張土日祝ネタ", "幕張お盆ネタ"],
    "よしもと漫才劇場":           ["Kiwami極LIVE", "マンゲキお笑いライブ", "マンゲキLIVE夏休みSP"],
    "森ノ宮よしもと漫才劇場":      ["森ノ宮マンゲキお笑いライブ", "森ノ宮Kakeru翔"],
    "よしもと福岡 大和証券劇場":   ["福岡よしもとお笑いライブ", "福岡ネタまつり"],
    "よしもと道頓堀シアター":      ["よしもとお笑いレストラン"],
    "沼津ラクーンよしもと劇場":    ["沼津週末寄席", "沼津ラクーンよしもと寄席"],
    "なんばグランド花月":         ["本公演", "夏休み特別興行", "お盆特別興行", "シルバーウィーク特別興行"],
}
```
（各キーワードは feed-api の生データで実タイトルを確認済み。「の部」はルミネの他タイトル74件と衝突しないことを確認済み）

## 設計方針の転換点

- **既存の「任意のタイトルを除外する」機能（`ExcludeKeywordStorage` / `/api/user-exclude-keywords`）はそのまま維持**。ただし、これはもう「定常公演のデフォルト値」を保持する役目を持たない。新規ユーザーの初期値は**空リスト**にする（定常公演の既定除外は下記の新機能が担う）。
- 前回実装した `exclude-keywords-default` KV・`ensure_default_exclude_keywords()`・`fetch_default_exclude_keywords()`・`DEFAULT_EXCLUDE_KEYWORDS` は**役目を新カタログに置き換える**。`user-exclude-keywords.js` の GET から「デフォルトへのフォールバック」ロジックを削除し、常に空リストベースにする。
- 新設定は排他的な3択（ラジオボタン）: `除外しない` / `一括除外する` / `指定劇場を除外する`（+ 劇場チェックボックス）。新規ユーザーの既定値は `一括除外する`（従来のグローバル除外が全ユーザーに効いていた挙動を踏襲し、無関係な定常公演で一覧が埋まらないようにする）。

## データモデル

- 新規 KV グローバルキー **`standing-show-keywords`**: `{schema_version:1, venues: {"渋谷よしもと漫才劇場":["渋谷マンゲキお笑いライブ","渋谷Kiwami極"], ...}, updated_at}`。真実源。`merge.py` 起動時に無ければ seed（既存の `ensure_default_exclude_keywords` と同じ冪等パターン）。
- 新規 KV ユーザーキー **`user-standing-exclude:{sha256(email)}`**: `{schema_version:1, mode:"off"|"all"|"venues", venues:[...], updated_at}`。未設定時のデフォルトは `{mode:"all", venues:[], updated_at:null, is_default:true}`。
- 既存 KV ユーザーキー `user-exclude-keywords:{sha256(email)}` はそのまま（任意タイトル用）。デフォルトフォールバックだけ撤去（空リストが初期値）。
- 廃止: KV `exclude-keywords-default`（新規ユーザーはもう使わない。既存データが残っていても実害はないが、今後は参照しない）。

## 実装ファイル

### `scripts/_talents_kv.py`
- `DEFAULT_EXCLUDE_KEYWORDS` / `ensure_default_exclude_keywords()` / `fetch_default_exclude_keywords()` を削除。
- `STANDING_SHOW_KEYWORDS_BY_VENUE`（上記カタログ）を追加。
- `ensure_standing_show_keywords()`: KV `standing-show-keywords` が無ければ seed（`_get_kv_json`/`_put_kv_json` 流用、`ensure_default_exclude_keywords` と同型）。
- `fetch_standing_show_keywords() -> dict`: KV `standing-show-keywords` の `venues` を返す（失敗時 `{}`）。
- `fetch_notify_targets_kv()`: 各ユーザーの `exclude_keywords` に加え、`user-standing-exclude:{hash}` を読み `standing_exclude: {mode, venues}` を追加（未設定時 `{mode:"all", venues:[]}`）。

### `functions/api/user-exclude-keywords.js`
- GET のデフォルトフォールバック（`exclude-keywords-default` 参照）を削除し、未設定時は常に `{schema_version:1, keywords:[], updated_at:null, is_default:true}` を返す。PUT はそのまま。

### `functions/api/user-standing-exclude.js`（新規）
`user-talents.js` を雛形に:
- KV_PREFIX = `'user-standing-exclude:'`
- **GET**: 未設定時 `{schema_version:1, mode:"all", venues:[], updated_at:null, is_default:true}` を返す。設定済みならそのまま返す。
- **PUT** body `{mode, venues}`: `mode` は `"off"|"all"|"venues"` のホワイトリスト検証。`venues` は配列（`mode!=="venues"` のときは空配列に正規化）。既知12劇場名のホワイトリストで各要素を検証（不正値は無視）。

### `functions/api/notify-targets.js`
- ループ内で `user-standing-exclude:{hash}` を取得し、`targets.push({email, talent_ids, exclude_keywords, standing_exclude})` に拡張（未設定時 `{mode:"all", venues:[]}`）。
- グローバルカタログ自体は notify.py 側で別途 `fetch_standing_show_keywords()` から取得するので、ここでは venues/mode のみ返す（レスポンス肥大化を避ける）。

### `scripts/notify.py`
- `main()` 冒頭で `catalog = fetch_standing_show_keywords()` を1回取得。
- ヘルパー関数 `is_standing_excluded(ev, standing_exclude, catalog)` を追加:
  ```python
  def is_standing_excluded(ev, standing_exclude, catalog):
      mode = standing_exclude.get("mode", "off")
      if mode == "off":
          return False
      venue = ev.get("venue")
      keywords = catalog.get(venue, [])
      if not keywords:
          return False
      title = ev.get("title") or ""
      if mode == "all":
          return any(kw in title for kw in keywords)
      if mode == "venues":
          return venue in standing_exclude.get("venues", []) and any(kw in title for kw in keywords)
      return False
  ```
- ユーザー別分岐（既存の `exclude_keywords` フィルタの隣）に `standing_exclude = target.get("standing_exclude", {})` を追加し、`user_events` から `is_standing_excluded` に該当するものを除外。
- フォールバック分岐（MAIL_TO）: 挙動を維持するため `standing_exclude={"mode":"all","venues":[]}` 相当（全劇場一括）で `catalog` を使ってフィルタ。

### `docs/assets/script.js`
- グローバル変数 `let standingExclude = {mode:'off', venues:[]};` `let standingCatalog = {};`
- `initExcludeFilter()` を拡張（または新規 `initStandingExcludeFilter()` を追加）: `/api/user-standing-exclude` と `/api/standing-show-keywords`（新規 GET エンドポイント、カタログをそのまま返すだけ・認証は既存パターンに合わせ CF Access）を fetch。
- `applyFilters()` の `kwExcluded` 判定に、venue 情報 `c.dataset.venue` を使った `isStandingExcluded(title, venue)` を OR 条件で追加。

### `functions/api/standing-show-keywords.js`（新規、読み取り専用）
- **GET**（CF Access）: KV `standing-show-keywords` をそのまま返す（`{venues: {...}}`）。ユーザーごとの差はない共有カタログ。

### `docs/settings.html` / `docs/assets/settings.js`
- 既存「除外キーワード」セクションの**上**に新セクション「定常公演を除外する」を追加。
  - ラジオボタン3択: `除外しない` / `一括除外する` / `指定劇場を除外する`
  - 「指定劇場を除外する」選択時のみ、12劇場のチェックボックスを表示（`disabled` 切り替え）
- `settings.js` に `StandingExcludeStorage`（`FollowStorage`/`ExcludeKeywordStorage` と同型: `/api/user-standing-exclude` と localStorage `fanaby_standing_exclude` を同期、`init/get/setMode/setVenues`）を追加。
- レンダリング関数 `renderStandingExclude()`、ハンドラ `handleStandingModeChange()` / `handleStandingVenueToggle()`。
- 初期化 IIFE に `StandingExcludeStorage.init()` を追加。

### ドキュメント
- `.claude/rules/cloudflare.md`: API表に `/api/user-standing-exclude`、`/api/standing-show-keywords` を追加。KV表に `standing-show-keywords`、`user-standing-exclude:{sha256(email)}` を追加、`exclude-keywords-default` の行を削除。
- `.claude/rules/data.md` / `frontend.md` / `scripts.md`: 定常公演除外の説明を追記、旧デフォルトキーワード関連の記述を更新。

## 実装順序

1. `_talents_kv.py`: カタログ定数・seed・fetch関数の追加、旧デフォルト機構の削除
2. Functions: `user-standing-exclude.js`、`standing-show-keywords.js` 新規作成、`user-exclude-keywords.js` のデフォルトフォールバック削除、`notify-targets.js` 拡張
3. `merge.py`: `ensure_standing_show_keywords()` 呼び出しに置き換え
4. `notify.py`: `is_standing_excluded` 追加、両分岐に適用
5. `docs/assets/script.js`: フェッチ・判定ロジック追加
6. `docs/settings.html` / `docs/assets/settings.js`: UI追加
7. ドキュメント更新

## 検証

1. Python構文チェック（`python3 -m py_compile`）、JS構文チェック（`node --check` / `--input-type=module`）
2. `jq empty` で JSON 妥当性確認
3. デプロイ後、`merge.py` を1回実行して KV `standing-show-keywords` が正しく seed されることを確認
4. 設定画面で「一括除外する」「指定劇場を除外する」を切り替え、index.html の該当劇場の定常公演が表示/非表示になることをブラウザで確認
5. notify.py をローカル実行し、定常公演がメールから除外されることをログで確認

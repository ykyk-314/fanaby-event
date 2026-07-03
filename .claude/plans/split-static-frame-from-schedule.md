# index.html の静的化と build.py のコンテンツ分離

## Context

現在 `build.py` は `docs/index.html` の全体（ヘッダー・芸人タブ・フィルターバー・スケジュールカード）を生成している。そのため、スクレイピングと無関係な「枠」（フィルター・タブ）を修正しても、スクレイピング系ワークフロー（`main.yml` / `remind-check.yml` / `talent-added.yml`）が走って `build.py` が index.html を再生成・コミットするまで反映されない。

一方 Cloudflare Pages は既に GitHub リポジトリと Git 連携済みで、`settings.html` / `exclude-settings.html` のような静的ファイルは main マージ時に自動デプロイされている。

**ゴール**: `docs/index.html` を静的な手動管理ファイル（`settings.html` と同格）にし、`build.py` はスケジュールの**コンテンツ部分だけ**を別ファイル `docs/schedule.html`（HTMLフラグメント）に出力する。index.html はロード時に `schedule.html` を fetch して差し込む。これで枠の修正は main マージ→Cloudflare 自動デプロイで即反映され、スケジュールの更新は従来どおりスクレイピングワークフローが `schedule.html` を更新・デプロイする。

**今回のスコープは枠分離のみ。カレンダー風レイアウトは別途対応。**

## 設計の要点

- **配信方式**: HTMLフラグメント方式（`render_event_card` の既存 Python 描画をそのまま流用、改修最小）。
- **芸人タブ**: 現在 `build.py` が talent マスタからサーバーレンダリングしているが、`script.js` の `initFollowFilter()`（`docs/assets/script.js:639`）が既に `/api/user-talents` + `/api/talents` から追従タブを動的生成できる。静的 index.html には「全員」タブのみ置き、残りは全てクライアント生成に一本化する（＝ライブKVベースで常に最新）。
- **build.py の master 依存除去**: `render_event_card` はイベント埋め込みの `ev["talents"]` のみ使用（`build.py:275`）で master 不要。タブ廃止に伴い `fetch_talents_master` の import と呼び出しを削除でき、`build.py` は純粋なローカルファイル変換になる。
- **最終更新日時**: 現在ヘッダーに `最終更新: ...` を出力している。ヘッダーは静的化するため、`build.py` が `schedule.html` 先頭に `<div id="scheduleMeta" data-updated="..." hidden></div>` を出力し、JS が読み取って静的ヘッダーの `<p id="lastUpdated">` に反映する。

## 変更ファイル

### 1. `docs/index.html`（新規・静的化）
現在 `build.py` のテンプレート（`build.py:367-436` 相当）から枠部分だけを抜き出して手動管理の静的ファイルにする。構成:
- `<header>`: 現行と同じ（`最終更新` は `<p id="lastUpdated">最終更新: —</p>` プレースホルダに）。`header-right` の ⊘/⚙ アイコンと `userAvatar` も含める。
- `.container` > `.sticky-controls`（`.tabs` は `<button class="tab-btn active" data-tab="all">全員</button>` の1個のみ + `.filter-bar` 一式）
- `.container` 内に `<div id="scheduleRoot"><div class="loading-overlay">読み込み中...</div></div>`
- `#lightbox`、`#backToTop`、`<script src="assets/script.js"></script>`

### 2. `scripts/build.py`
- docstring / 完了ログの `index.html` を `schedule.html` に変更。
- `from _talents_kv import fetch_talents_master` と `talents = fetch_talents_master(...)`、`tab_buttons` 生成ブロック（`build.py:324-339`）を削除。
- `main()` 末尾: 巨大な全ページ f-string テンプレートを撤去し、フラグメントだけを組み立てて `docs/schedule.html` に書き出す:
  ```
  meta = f'<div id="scheduleMeta" data-updated="{escape_html(updated_str)}" hidden></div>'
  fragment = meta + (content_html or '<p class="empty">公演情報がありません</p>')
  (DOCS_DIR / "schedule.html").write_text(fragment, encoding="utf-8")
  ```
- `content_html`（future の `.section` / past の `.section-past`）生成ロジックはそのまま流用。

### 3. `docs/assets/script.js`
- **スケジュール差し込み関数を追加**:
  ```js
  async function injectSchedule() {
    const root = document.getElementById('scheduleRoot');
    try {
      const res = await fetch('schedule.html', { cache: 'no-cache' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      root.innerHTML = await res.text();
      const meta = document.getElementById('scheduleMeta');
      const p = document.getElementById('lastUpdated');
      if (meta && p) p.textContent = '最終更新: ' + (meta.dataset.updated || '—');
    } catch (e) {
      root.innerHTML = '<p class="empty">スケジュールの読み込みに失敗しました</p>';
    }
  }
  ```
  ※ `schedule.html` は `build.py` が全て `escape_html` 済みの自己生成フラグメントのため `innerHTML` 差し込みで安全（メモ等のユーザー入力は従来どおり別途 `textContent` 制御）。
- **初期化 IIFE（`script.js:690-703`）を再構成**: カードが DOM に無いと `initStatusUI`/`initRemindUI`/`initMemoUI`/`initExcludeUI`/`buildVenueOptions`/`injectTalentAvatars`/`applyFilters` が機能しないため、**先に `await injectSchedule()` を実行**してから既存シーケンスを回す。`viewing-select` の disable 処理も差し込み後に移動。
  ```js
  (async () => {
    await injectSchedule();
    document.querySelectorAll('.viewing-select').forEach(s => s.disabled = true);
    await Promise.all([ViewingStorage.init(), initUserUI(), initFollowFilter(), initExcludeFilter(), initStandingExcludeFilter()]);
    initStatusUI(); initRemindUI(); initMemoUI(); initExcludeUI();
    buildTabImgMap(); injectTalentAvatars(); buildVenueOptions(); applyFilters();
    document.querySelectorAll('.viewing-select').forEach(s => s.disabled = false);
  })();
  ```
- `initFollowFilter()` は静的 index.html に「全員」タブしか無い状態でも、追従芸人を全て「missing」として動的生成する既存経路（`script.js:658-688`）で正しく動作する。`buildTabImgMap()` は動的生成後の DOM を読むため変更不要。

### 4. ワークフロー（`git add` のパス変更のみ、wrangler デプロイは現状維持）
- `.github/workflows/main.yml:104`、`talent-added.yml:85`: `docs/index.html` → `docs/schedule.html`
- `.github/workflows/remind-check.yml:53`: `docs/index.html` → `docs/schedule.html`
- ※ `docs/index.html` は静的ソースとして Git 管理を継続（build.py は触れない）。Cloudflare Git 連携が main マージ時に自動デプロイ。スクレイピング系は従来どおり `wrangler pages deploy docs` で `schedule.html` を含む `docs/` をデプロイ（コミット push による Git 連携デプロイと二重になるが現状と同じ挙動）。

### 5. ドキュメント（`.claude/rules/`）
- `scripts.md`: `build.py` の出力を `docs/schedule.html`（フラグメント）に更新。データフロー図の `build.py → docs/index.html` を修正。
- `frontend.md`: ファイル構成表に「`docs/index.html`＝静的（手動管理）・枠のみ」「`docs/schedule.html`＝`build.py` 生成・スケジュールカードのフラグメント」を追記。芸人タブがクライアント生成である旨を明記。
- `cicd.md`: 各ワークフローの `git add` 対象を `docs/schedule.html` に更新。
- ルート `CLAUDE.md`: コマンド表の「HTML生成 build.py」説明を `schedule.html` 生成に更新。

## 検証

Python/JS はローカル実行しない方針のため静的レビュー + 構文チェックのみ:
1. `python3 -m py_compile scripts/build.py`（構文）
2. `node --check docs/assets/script.js`（構文）
3. デプロイ後ブラウザ確認:
   - index.html を開き `schedule.html` が fetch・差し込みされ、カード・観覧ステータス・リマインド・メモ・除外・フライヤーライトボックスが従来どおり動く
   - 芸人タブが追従芸人ぶんクライアント生成され、切り替え・会場フィルター・件数が正しく更新される
   - ヘッダーの「最終更新」がフラグメントの `scheduleMeta` から反映される
   - スティッキー追従・最上部へ戻るボタンが引き続き機能する
4. 枠のみ変更（例: filter-bar のラベル文言）を main にマージ→スクレイピング無しで Cloudflare 自動デプロイに反映されることを確認
5. スクレイピングワークフロー実行→`docs/schedule.html` が更新・コミット・デプロイされ、index.html に最新スケジュールが出ることを確認

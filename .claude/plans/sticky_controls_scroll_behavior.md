# コントロールバーのスクロール挙動改善

## Context（背景）

`docs/index.html` の芸人タブ＋フィルターバーをまとめた `.sticky-controls`（以下「コントロールバー」）が、現状 `position: sticky; top: 0` で**常時**画面上部に追従している（`docs/assets/style.css:31-39`）。スクロール中もずっと居座るため邪魔、という課題。

**目指す挙動（ユーザー要望）:**
1. **最上部付近**（`scrollY` が「ヘッダー＋コントロールバー＋20px」以内）→ 通常のフルレイアウトで常に表示
2. **スクロール中**（上記範囲を越えている間）→ 上へスライドして隠す
3. **スクロール停止から200ms後**→ 隠れていたものが**コンパクト版（B案：縮小・1行・アイコン化）**で再表示

ライブラリは使わず、既存の軽量な素のJS（`docs/assets/script.js` の backToTop IIFE と同型）＋CSSトランジションで実装する。

## 変更対象ファイル

- `docs/index.html` … センチネル要素の追加＋フィルターバーのラベルにアイコン化用フックを付与
- `docs/assets/style.css` … コントロールバーの状態別スタイル（`.is-hidden` / `.is-compact`）＋トランジション
- `docs/assets/script.js` … IntersectionObserver（最上部判定）＋ scroll ハンドラ（隠す／停止検知）

いずれも `build.py` が触れない静的ファイル（`.claude/rules/frontend.md` 準拠）。`docs/schedule.html` は対象外。

## 実装方針

### 1. 最上部判定 — IntersectionObserver + センチネル

`window.scrollY` の閾値をヘッダー高さから手計算すると脆いため、**ゼロ高さのセンチネル要素**を `.sticky-controls` の直後（`#scheduleRoot` の前）に置き、その可視状態で判定する。

`docs/index.html` の `.sticky-controls`（L64 の閉じ `</div>` 直後、`<div id="scheduleRoot">` の前）に追加:

```html
<div id="controlsSentinel" aria-hidden="true"></div>
```

- センチネルはコントロールバー直下に位置するため、`scrollY ≈ ヘッダー高 + コントロールバー高` でビューポート上端を抜ける = ちょうどコントロールバーが隠れ始める点。
- `rootMargin: '20px 0px 0px 0px'`（正の top）でルート上端を20px外側へ広げ、判定を20px分遅らせる → 要望の「＋20px の遊び」を実現（値は調整可能）。
- センチネルが**見えている間** = 「最上部」= フル表示。**見えなくなったら** = 「固定ゾーン」= 隠す／コンパクト挙動を有効化。

### 2. scroll ハンドラ — 隠す＋停止検知（`docs/assets/script.js`）

backToTop の IIFE（L76-85）と同様に、独立した passive リスナーの IIFE を追加:

```js
// ---- コントロールバーのスクロール挙動 ----
(() => {
  const controls = document.querySelector('.sticky-controls');
  const sentinel = document.getElementById('controlsSentinel');
  if (!controls || !sentinel) return;

  let atTop = true;
  let stopTimer = null;

  const io = new IntersectionObserver(([e]) => {
    atTop = e.isIntersecting;
    if (atTop) {                       // 最上部に戻ったら全状態を解除しフル表示
      clearTimeout(stopTimer);
      controls.classList.remove('is-hidden', 'is-compact');
    }
  }, { rootMargin: '20px 0px 0px 0px', threshold: 0 });
  io.observe(sentinel);

  window.addEventListener('scroll', () => {
    if (atTop) return;                 // 最上部付近は常にフル表示
    controls.classList.add('is-hidden');   // スクロール中は隠す
    clearTimeout(stopTimer);
    stopTimer = setTimeout(() => {         // 停止200ms後にコンパクトで再表示
      controls.classList.remove('is-hidden');
      controls.classList.add('is-compact');
    }, 200);
  }, { passive: true });
})();
```

挙動整理:
- 最上部 → 両クラス無し（フル・通常追従）
- 固定ゾーンでスクロール中 → `.is-hidden`（上へスライドして退避）
- 固定ゾーンで停止200ms後 → `.is-hidden` 解除 + `.is-compact`（縮小版でスライドイン）
- 一度コンパクトになった後は、再スクロールで隠れ→停止で再びコンパクト（＝「スクロール後は別レイアウト」を維持）

### 3. 状態別スタイル（`docs/assets/style.css`）

既存の `.sticky-controls`（L31-39）に `transition: transform .25s ease;` を追加し、以下を新規追加:

```css
.sticky-controls.is-hidden { transform: translateY(-110%); }   /* 影ごと隠す */

/* コンパクト版（B案：縮小・1行・アイコン化） */
.sticky-controls.is-compact .tabs { margin-bottom: 6px; }
.sticky-controls.is-compact .tab-btn { padding: 3px 10px; font-size: 12px; }
.sticky-controls.is-compact .filter-bar { padding: 6px 10px; gap: 8px; margin-bottom: 8px; }
/* 平文ラベル（キーワード/会場/観覧ステータス/日付）をアイコン化 */
.sticky-controls.is-compact .filter-bar label.filter-label { font-size: 0; }
.sticky-controls.is-compact .filter-bar label.filter-label::before { font-size: 14px; }
```

**ラベルのアイコン化フック**: `docs/index.html` のフィルターバー内の平文 `<label>` に `class="filter-label"` と絵文字を渡すため `data-icon` を付与し、CSSの `::before { content: attr(data-icon); }` で表示する。対象:
- `キーワード` → 🔍（L34）
- `会場` → 📍（L38）
- `観覧ステータス` → 👀（L42）
- `日付（から）` / `（まで）` → 📅 / 〜（L54,56）

チェックボックス系ラベル（`.filter-remind-label` L58 / `.filter-exclude-label` L59）は**チェックボックスが label 内包**のため `font-size:0` にすると崩れる。これらはコンパクト時もそのまま（絵文字が既に付いており視認可能）とし、`.filter-label` は付けない。

`.filter-reset`（L59）・`.filter-count`（L61）はそのまま維持。

### 4. モバイル・アクセシビリティ配慮

- 既存の `@media (max-width: 560px)`（L127-132）でフィルターバーは複数行に折り返す。コンパクト版でも**1行を強制せず折り返し許可**のまま（縮小 padding のみ適用）。狭幅で無理に1行化しない。
- `@media (prefers-reduced-motion: reduce) { .sticky-controls { transition: none; } }` を追加し、モーション過敏に配慮。

## 検証（Verification）

`build.py` 不要。静的ファイルのみのため、ローカルで `docs/` を配信して目視確認する:

```
cd docs && python3 -m http.server 8000
# ブラウザで http://localhost:8000/ を開く
```

（※ プロジェクト方針で Python スクリプトの手元実行は避けるが、これは標準ライブラリの静的配信であり `scripts/` の実行ではない。難しければユーザーに `! cd docs && python3 -m http.server 8000` の実行を促す）

確認項目:
1. **最上部**: フルレイアウトで表示され、少しスクロールしても（ヘッダー＋バー＋20px 以内は）そのまま
2. **スクロール中**: 上記を越えるとコントロールバーが上へスライドして消える
3. **停止200ms後**: コンパクト版（タブ小・フィルター1行・ラベルがアイコン）でスライドイン
4. **最上部へ戻す**: フルレイアウトに復帰
5. **機能維持**: コンパクト時もキーワード入力・会場/観覧セレクト・日付・通知/除外チェック・リセットが全て動作
6. **backToTop ボタン**が従来どおり動く（scroll リスナー併存の確認）
7. モバイル幅（560px以下）で崩れない

## 補足

- 承認後は CLAUDE.md のブランチ規則に従い `feature/YYMMDD` ブランチを作成し、branch→commit→push→PR作成→`gh pr merge --merge` の完結フローで進める（前回合意済み）。

# 公演カードのコンパクト化＋詳細モーダル化

## Context

現在の公演カード（`scripts/build.py` の `render_event_card`）は、1枚に「日時・会場・出演者・料金・チケット受付・お知らせ・チケット/配信/カレンダー各ボタン・ステータスセレクト・リマインド・除外・メモ欄（常時2行）・フライヤー」を全部詰め込んでいる。そのため縦に長く、出演者が多い公演やメモ欄で一覧のスクロール量が膨らみ、目的の公演を探しにくい。

**ゴール**: カードは一覧で必要な最小情報だけを表示し、カードをタップすると詳細をモーダルで開く。既存機能（`ViewingStorage` によるステータス/メモ/リマインド/除外の KV 同期、除外キーワード/定常公演フィルタ、芸人アイコン注入、フィルターバー、ライトボックス）は一切壊さない。

ユーザー確定事項:
- カードに残す重要情報 = **バッジ / タイトル / 日時 / 出演者（省略表示）/ フライヤーサムネイル / 芸人アイコン / ステータス（ラベル）**
- それ以外（会場・料金・チケット受付・お知らせ・各種ボタン・メモ・ステータス変更操作）は**すべてモーダルへ**
- ステータス変更・リマインド等のクイック操作もモーダルに集約（カード上には操作を置かない＝見るだけ）

## 変更ファイル

| ファイル | 変更内容 |
|---|---|
| `scripts/build.py` | `render_event_card` を「サマリ部（常時表示）＋詳細部（`hidden`、開いたらモーダルへ移動）」の2ブロック構成に再構築 |
| `docs/index.html` | 詳細モーダルの器（`#eventModal`）を静的に追加（ライトボックスと同様、手動管理ファイル） |
| `docs/assets/style.css` | カードサマリ／モーダルのスタイル、出演者1行省略（line-clamp）、ステータスラベル、既存 `.card-body`/`.flyer` 系の再編 |
| `docs/assets/script.js` | モーダル開閉（詳細ノードの move/戻し）、ステータスラベル更新、除外/ステータス反映を event-id ベースに変更 |

`docs/schedule.html` は `build.py` 生成物のため直接編集しない（`build.py` の出力変更で反映）。

## 設計

### 1. カード構造（build.py: `render_event_card`）

ルート `.event-card` の **data-* 属性は現状維持**（`data-talent` / `data-venue` / `data-prefecture` / `data-date` / `data-event-id` / `data-title` / `data-members` / `data-viewing-status`）。フィルタは DOM の表示位置に依存せず data 属性で動くため、詳細部をモーダルへ移動しても影響しない。

**サマリ部 `.card-summary`（常時表示）**:
- `badge`（NEW/UPDATED）＋ `.card-title`
- 日時（`日付 開演HH:MM` のみ。開場/終演はモーダル）
- 出演者（`.members-text` を1行 line-clamp。全文はモーダル）
- フライヤーサムネイル `.flyer-thumb`（小さめ・`loading="lazy"`）
- ステータスラベル `.status-label`（JS が更新。空なら非表示）
- 芸人アイコン `.card-talent-icons`（現状どおり `injectTalentAvatars()` が注入）

**詳細部 `.card-detail`（`hidden`、モーダルへ move）**:
- 会場（`venue / prefecture`）、出演者全文、料金、チケット受付（`render_ticket_deadlines`）
- お知らせ `<details>`（`notice`）
- ボタン群：チケット購入 / 配信チケット / カレンダー / ステータス `<select>` / リマインド / 除外
- メモ `textarea`

`render_ticket_deadlines` / `render_badge` / `make_gcal_url` / `format_*` など既存ヘルパーはそのまま流用。生成する HTML 断片を2ブロックに振り分けるだけで、新規ヘルパーは追加しない。

### 2. モーダルの器（index.html）

ライトボックス（`#lightbox`）と同型のオーバーレイを1つだけ静的に追加:

```
#eventModal（オーバーレイ, クリックで閉じる）
  .modal-panel
    button.modal-close（×）
    .modal-header（タイトル・日時）
    img#eventModalFlyer（クリックで既存 openLightbox）
    #eventModalBody（ここに .card-detail を move）
```

### 3. JS（script.js）

**モーダル開閉**（ライトボックスの IIFE と同型の素の JS）:
- `openEventModal(card)`:
  1. 既に別カードの詳細が開いていれば先に `closeEventModal()` で戻す
  2. `card.querySelector('.card-detail')` を `#eventModalBody` に `appendChild`（clone せず move。textarea 値・select 状態・登録済みリスナーを保持するため）
  3. モーダルのタイトル/日時をサマリから流し込み、`#eventModalFlyer.src` をサマリの `.flyer-thumb` から取得（無ければ非表示）
  4. `#eventModal` を open。`openCard` に元カード参照を保持
- `closeEventModal()`: 詳細部を元カード（`openCard`）へ戻し、モーダルを閉じる
- クリック委譲: `document` の click で `e.target.closest('.card-summary')`（またはカード内サマリ）→ `openEventModal`。サマリ内に操作要素は無いので誤爆しない
- Escape: ライトボックスが開いていれば従来どおり閉じ、そうでなければモーダルを閉じる（既存 keydown ハンドラを拡張）

**move による副作用対策**（重要）:
- `applyExcludedToCard` / `applyStatusToCard` は現状 `card.querySelector('.exclude-btn')` など**カード配下**を前提にしている。詳細部がモーダルへ移動している間はカード配下に無いため、**event-id で `document` 全体から引く**方式に変更する（`.viewing-select[data-event-id="X"]` / `.exclude-btn,.unexclude-btn[data-event-id="X"]`）。`viewing-wrap` には `data-event-id` を build.py で付与し、同様に引けるようにする。
- `applyStatusToCard(card, status)` は「①`card.dataset.viewingStatus`（ルート＝常在）②サマリの `.status-label`（常在）③select/wrap（event-id で解決）」の順に更新。左ボーダー色はルート data 属性で従来どおり効く。
- `initStatusUI` / `initMemoUI` / `initRemindUI` / `initExcludeUI` は**ロード時に一度**カード配下を走査してリスナー登録・初期値反映する。この時点では詳細部はまだカード内にあるため現状の初期化はそのまま動く。以降の move はノードごと動くのでリスナー・入力状態は保持される。

**ステータスラベル**:
- `const VIEWING_STATUSES` の `label`/`color` を流用し、`updateStatusLabel(card, status)` を追加。`applyStatusToCard` から呼ぶ。空文字なら `.status-label` を空＋非表示。

### 4. CSS（style.css）

- `.card-summary`: 1行〜2行に収まる横並びレイアウト（左：テキスト、右：`.flyer-thumb`）。カード全体に `cursor: pointer`
- `.members-text`（サマリ内）: `-webkit-line-clamp:1` で省略、`…`
- `.flyer-thumb`: 幅60〜72px 程度
- `.status-label`: ステータス色の小さめピル。`data-viewing-status` 別の色は既存の CSS 変数（`--status-*`）を流用
- `#eventModal` / `.modal-panel` / `.modal-close`: `#lightbox` と同系。スクロール可・中央寄せ・モバイル全幅
- z-index: `#lightbox` > `#eventModal` になるよう調整（モーダル内フライヤーを拡大表示できる）
- 既存の `.card-body`/`.card-left`/`.card-info`/`.card-btns`/`.memo-wrap`/`.flyer` 系は詳細部（＝モーダル内）向けに整理。`@media (max-width:560px)` のカード段組みルールはモーダル内レイアウトへ読み替え

## 検証

`build.py` の実行はローカルで行わない方針（CI/CD 任せ）だが、フロントは静的ファイルのみで確認できる。

1. `docs/` をローカル配信（例: 別ターミナルで `python -m http.server` 等をユーザーが起動）し、`schedule.html` を既存生成物のまま `index.html` から読み込み
   - ※`build.py` を回さないと新カード構造の `schedule.html` は出ないため、**カード構造の目視確認は既存 `schedule.html` を手で1件だけ新HTMLに差し替えたサンプル**、もしくは CI 反映後に本番で確認する。ローカルでは主にモーダル開閉・move/戻し・ステータスラベル・除外/メモ/リマインドの動作を確認
2. 確認項目:
   - カードタップでモーダルが開き、詳細（会場・料金・受付・お知らせ・ボタン・メモ）が表示される
   - モーダルでステータス変更 → 閉じても一覧カードの左ボーダー色・ステータスラベルに反映
   - メモ入力 → 閉じて再度開くと保持（`ViewingStorage` 経由で KV 同期）
   - リマインド ON/OFF、除外/解除がモーダル内で動作し、閉じた後の一覧（フィルタ・件数）に反映
   - モーダル内フライヤークリックでライトボックス拡大（z-index 順）
   - Escape でライトボックス→モーダルの順に閉じる
   - フィルターバー（キーワード・会場・日付・ステータス・通知ON・除外表示）と件数が従来どおり動作
3. モバイル幅（Safari/iPhone 想定）でカード1行表示・モーダル全幅を確認

## 留意点

- `docs/index.html` / `style.css` / `script.js` は静的手動管理。`build.py` はこれらに触れないので整合は保たれる（`.claude/rules/frontend.md` 準拠）
- カード構造を変えると `build.py` 生成の `schedule.html` と静的側 JS/CSS の**両方を同一 PR で**変える必要がある（片方だけデプロイすると表示崩れ）
- 本プランは3ステップ以上の変更のため、承認後 `feature/YYMMDD` ブランチを切って実装する

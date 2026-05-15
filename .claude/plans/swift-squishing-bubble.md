# Phase-α: FANY マイページ購入/申込履歴ビューワー

## Context

FANY の「購入/申込履歴一覧」（`https://ticket.fany.lol/history`）は検索機能が貧弱（発券状況・落選非表示・予約/公演日時の昇順降順のみ）で、毎月複数公演に行くユーザーには使い物にならない。FANY 側の改善が見込めないため、自前で使いやすい検索ビューワーを実装する。

**最重要制約（ユーザー確認済み）**:
- **fanaby-event を一切利用しない**（KV / Functions / Access に依存しない）
- **fanaby-event 本体は友達に共有しない**（マイページビューワーのみ友達も使えるようにする）
- **FANY のログイン情報・履歴データをサーバー側に持たない**（純粋なクライアントサイド処理）
- **iPhone Safari がメインブラウザ**（Tampermonkey / Chrome 拡張は使えない）

これを満たすため「**ブックマークレット + 独立静的 Web アプリ + postMessage**」構成にする。FANY のログインセッションはブラウザ内に留まり、ブックマークレットが same-origin fetch で全ページを取得・DOM パース → `window.postMessage` で別タブのビューワーに転送 → LocalStorage に永続保存する。サーバー側には何も送らない。

---

## ディレクトリ構成

fanaby-event リポジトリ内に独立フォルダを切る。Cloudflare Pages の別プロジェクト（`mypage-viewer`）として独立サブドメイン（`mypage-viewer.pages.dev`）にデプロイするため、ドメインは完全分離される。

```
fanaby-event/
├── docs/                    # 既存: fanaby-event 本体（Cloudflare Pages プロジェクト1）
└── mypage-viewer/           # 新規: 独立 Cloudflare Pages プロジェクト2
    ├── index.html           # ビューワー本体（フィルタ UI + 結果表示）
    ├── install.html         # ブックマークレット導入手順ページ（友達への共有用）
    ├── assets/
    │   ├── style.css        # ビューワーのスタイル
    │   ├── viewer.js        # ビューワーの JS（postMessage 受信・LocalStorage・フィルタ）
    │   └── bookmarklet.js   # ブックマークレットのソース（minify 前）
    └── README.md            # プロジェクト説明（任意）
```

**Cloudflare Pages の Build 設定**:
- プロジェクト名: `mypage-viewer`
- Production branch: `main`
- Build command: なし（静的）
- Build output directory: `mypage-viewer`
- 公開 URL: `https://mypage-viewer.pages.dev`
- **Cloudflare Access は設定しない**（友達が自分の端末から自分の FANY セッションで使うため、ビューワー側に認証ゲートを置く意味がない）

---

## アーキテクチャ概要

```
┌─────────────────────────────────┐        ┌─────────────────────────────────┐
│ ticket.fany.lol（FANY ログイン済） │       │ mypage-viewer.pages.dev          │
│                                 │        │                                 │
│  [ブックマークレット実行]         │        │  [ビューワーアプリ]              │
│   ↓                             │        │   ↓                             │
│  same-origin fetch で           │        │  window.addEventListener        │
│  ?ticket_page=1〜19 を順次取得   │        │   ("message", ...)              │
│   ↓                             │  postMessage                            │
│  DOMParser でパース             │  ─────→│  LocalStorage 保存              │
│   ↓                             │        │   ↓                             │
│  window.open("mypage-viewer")   │        │  フィルタ UI + 結果表示          │
│   + postMessage で送信          │        │                                 │
└─────────────────────────────────┘        └─────────────────────────────────┘
```

データの流れは一方向（FANY → ビューワー）で、サーバーへは何も送らない。

---

## ブックマークレットの実装（`mypage-viewer/assets/bookmarklet.js`）

`ticket.fany.lol` 上で実行することを前提とする。

**処理ステップ**:
1. 現在のドメインが `ticket.fany.lol` であることを確認（違ったら `alert` で警告して終了）
2. `window.open("https://mypage-viewer.pages.dev/", "_mypage_viewer")` でビューワーを開く（既に開いていればフォーカス）
3. `fetch("/history?ticket_page=N", { credentials: "include" })` を N=1 から順次実行
4. レスポンス HTML を `DOMParser` でパースし、以下のセレクタで抽出:
   - メイン行: `tr.g-table_borderless`
   - 詳細行: その次の `tr.g-table_spanned`（ペア）
   - イベント名: `td[data-label="イベント名"]`
   - 申込番号: `td[data-label="申込番号"]`
   - 予約日時: `td[data-label="予約日時"]`
   - 状況: `td[data-label="状況"]`（落選判定は `.g-tag-ng` の有無、当選は `.g-tag-ok`）
   - 公演日: `td[data-label="公演日"]`（日付 + 開場/開演時刻 + タイトルが混在 → 正規表現で分解）
   - 会場名: `td[data-label="会場名"]`
   - 席種: `td[data-label="席種"]`
   - 数量: `td[data-label="数量"]`
   - 金額: `td[data-label="金額"]`
   - 詳細リンク: `a.g-link-key` の `href`（落選は無し）
5. 次ページ判定: ページ内に「次へ」リンクが無い、または抽出件数が 0 になったら停止（最大 19 ページで安全停止）
6. 全件取得完了後、`viewerWindow.postMessage({ type: "fanaby-history", payload: [...], scrapedAt: ISO8601 }, "https://mypage-viewer.pages.dev")` で送信
7. 取得中は `document.title` を「取得中 N/19」に書き換えて進捗表示

**注意点**:
- `fetch` は `credentials: "include"` で同一オリジン Cookie が自動付与される
- レート制御: ページ間に 300ms 程度の `await` を入れて FANY サーバーに負荷をかけない
- エラー時は `alert` でユーザーに通知（HTTP 401 = セッション切れ など）

**ブックマークレット化**:
`assets/bookmarklet.js` を minify して `javascript:` プレフィックスを付けたものを `install.html` 内にコピペ用リンクとして配置する。

---

## ビューワーアプリの実装（`mypage-viewer/index.html` + `assets/viewer.js`）

### LocalStorage スキーマ

```json
{
  "schema_version": 1,
  "scraped_at": "2026-05-15T10:00:00.000Z",
  "entries": [
    {
      "id": "申込番号またはハッシュ",
      "title": "公演タイトル",
      "performance_date": "2026-06-10",
      "open_time": "18:30",
      "start_time": "19:00",
      "venue": "渋谷よしもと漫才劇場",
      "reserved_at": "2026-04-01 10:00",
      "status": "paid",          // "paid"|"unticketed"|"won"|"lost"
      "status_text": "入金済",
      "seat_type": "自由席",
      "quantity": 1,
      "price": 2000,
      "detail_url": "https://ticket.fany.lol/history/detail/xxxxx"
    }
  ]
}
```

- LocalStorage キー: `fanaby_mypage_history`
- スキーマは将来の項目追加に備えて `schema_version` を持つ
- 上書き保存（毎回全件取得する想定。差分マージは不要）

### フィルタ UI

| フィルタ | UI |
|---|---|
| 自由文字列検索 | input（公演名 + 会場 + 席種を対象に AND 部分一致、スペース区切り） |
| 会場 | `<select>`（取得済みデータからユニークな会場を抽出） |
| 公演日 from / to | `<input type="date">` × 2 |
| ステータス | チェックボックス 4 種（入金済 / 未発券 / 当選 / 落選）。**落選のみデフォルト OFF**、他はデフォルト ON |
| 件数表示 | フィルタ結果のリアルタイム件数 |
| データ更新日時 | `scraped_at` を画面上部に表示 |
| 再取得 | 「ブックマークレットを実行してください」案内 + 履歴ページへのリンク |

### 表示

- カードまたはテーブル形式（iPhone Safari 縦画面で読みやすくするためカード推奨）
- カード上部: 公演日 + 開演時刻 + タイトル
- 中段: 会場 + 席種 + 数量 + 金額
- 下段: ステータスバッジ + 予約日時 + 詳細リンク（落選以外）
- 落選は色を抑える（透明度 0.6）

### postMessage 受信

```js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://ticket.fany.lol") return;
  if (event.data?.type !== "fanaby-history") return;
  // payload を正規化して LocalStorage に保存し、フィルタ UI を再描画
});
```

- origin を厳格にチェック（`ticket.fany.lol` 以外からのメッセージは破棄）
- データを正規化（`status` の判定、数値変換など）してから保存

---

## install.html（友達への共有用ガイド）

iPhone Safari ユーザー向けの導入手順を視覚的に説明する。

**内容**:
1. このツールの概要（FANY 履歴を高機能に検索できる、ログイン情報は送られない）
2. **iPhone Safari の場合のブックマーク登録手順**:
   - 適当なページをブックマーク追加 → ブックマーク編集で URL を `javascript:...` に置換
   - スクリーンショット付きで案内
3. **PC Chrome の場合**:
   - ブックマークバーにドラッグ&ドロップ可能なリンクを配置
4. 使い方:
   - `ticket.fany.lol/history` を開いてログイン
   - ブックマークから「FANY履歴取得」を実行
   - 自動で `mypage-viewer.pages.dev` が開き、データが転送される

---

## セキュリティ・プライバシー設計

| 項目 | 対策 |
|---|---|
| FANY ログイン情報 | ブックマークレットは Cookie に触らない（fetch の `credentials: "include"` で自動付与のみ）。サーバーには何も送らない |
| 履歴データ | LocalStorage に保存。ビューワーから外部へは送信しない |
| postMessage の origin 検証 | 送信側 / 受信側ともに固定オリジンを指定 |
| XSS | DOM 挿入時は `textContent` のみ使用（`innerHTML` 禁止）。詳細 URL は `https://ticket.fany.lol/` で始まることを検証 |
| サーバーログ | Cloudflare Pages の静的配信のみ。Functions / KV / Access は使わない |
| 第三者への漏洩 | ビューワーアプリには認証ゲートを置かないが、データは各端末の LocalStorage のみに存在するため共有されない |

---

## 修正・新規作成ファイル

| パス | 種別 | 内容 |
|---|---|---|
| `mypage-viewer/index.html` | 新規 | ビューワー本体 |
| `mypage-viewer/install.html` | 新規 | 導入手順ページ |
| `mypage-viewer/assets/style.css` | 新規 | ビューワーのスタイル |
| `mypage-viewer/assets/viewer.js` | 新規 | postMessage 受信 + フィルタ + LocalStorage |
| `mypage-viewer/assets/bookmarklet.js` | 新規 | ブックマークレットのソース（minify 前） |
| `.claude/rules/phase-alpha.md` | 新規 | Phase-α の仕様書（実装後の参照用） |

**fanaby-event 本体（`docs/`, `scripts/`, `functions/` 等）には一切手を加えない**。

---

## 参考: DOM 構造

`.claude/issues/Pα-mypage-histories/histories.html`（ユーザー提供サンプル）で確認済み:

```html
<tr class="g-table_borderless">
  <td data-label="イベント名">...</td>
  <td data-label="申込番号">...</td>
  <td data-label="予約日時">...</td>
</tr>
<tr class="g-table_spanned">
  <td data-label="状況"><span class="g-tag-ok">当選</span> または <span class="g-tag-ng">落選</span></td>
  <td data-label="公演日">YYYY/MM/DD ＋ 開場/開演 ＋ タイトル（混在）</td>
  <td data-label="会場名">...</td>
  <td data-label="席種">...</td>
  <td data-label="数量">...</td>
  <td data-label="金額">...</td>
  <a class="g-link-key" href="/history/detail/...">（落選には無し）</a>
</tr>
```

落選エントリは行全体に `class="g-color-disabled"` が付くケースもある（追加検証が必要）。

ページネーション: `?ticket_page=N`（1〜最大 19）

---

## 検証手順

1. **ローカルでビューワー単体を開いて UI 確認**
   - `mypage-viewer/index.html` を `file://` または `python -m http.server` で開く
   - サンプル JSON を LocalStorage に直接投入してフィルタ動作確認
   - 落選デフォルト非表示 / ステータストグル / 自由文字列検索 / 会場 / 日付 from-to が正しく動くこと

2. **ブックマークレット動作確認**
   - PC Chrome で `https://ticket.fany.lol/history` を開いてログイン
   - DevTools コンソールに `bookmarklet.js` の中身をペーストして実行
   - 全ページ取得 → ビューワータブが開く → データ転送 → LocalStorage 保存を確認

3. **Cloudflare Pages デプロイ後の確認**
   - `mypage-viewer.pages.dev` にアクセスして表示確認
   - ブックマークレットの postMessage 先 origin を本番 URL に修正してから動作確認
   - iPhone Safari でブックマーク登録 → 実行 → ビューワー表示までを E2E 確認

4. **セキュリティ確認**
   - DevTools の Network タブで、ビューワー側からの外部送信が無いことを確認
   - postMessage の origin 検証が正しく機能することを、別 origin からの偽メッセージで確認
   - LocalStorage 以外にデータが保存されていないことを確認

---

## 未確定事項（実装中に判断）

- 落選行の正確な判定セレクタ（`.g-color-disabled` か `td[data-label="状況"] .g-tag-ng` か）→ 実装時に実データで確認
- 公演日セル内の「日付・開場・開演・タイトル」分解ルール → 実装時に複数パターンを正規表現で対応
- ブックマークレットの容量制限（Safari は 2KB 程度の制限あり） → 必要なら viewer.js 側で重い処理を肩代わりさせる

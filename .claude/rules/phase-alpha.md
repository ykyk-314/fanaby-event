---
paths: mypage-viewer/**/*
---

# Phase-α: FANY マイページ履歴ビューワー（`mypage-viewer/`）

## 概要

FANY（`ticket.fany.lol`）の購入・申込履歴を、公演名・会場・公演日・ステータスで絞り込めるビューワー。
**fanaby-event とは完全独立**。サーバー側にログイン情報・履歴データを一切持たない純粋クライアントサイド実装。

## アーキテクチャ

```
ticket.fany.lol（ブックマークレット実行）
  ↓ same-origin fetch /history?ticket_page=N
  ↓ DOMParser でパース
  ↓ window.postMessage（origin 固定: https://mypage-viewer.pages.dev）
mypage-viewer.pages.dev（ビューワー）
  ↓ origin 検証 + バリデーション
  ↓ LocalStorage 保存（キー: fanaby_mypage_history）
  ↓ フィルタ UI で表示
```

## Cloudflare Pages 設定

| 項目 | 値 |
|---|---|
| プロジェクト名 | `mypage-viewer` |
| Build command | なし（静的） |
| Build output directory | `mypage-viewer` |
| Cloudflare Access | **なし**（友達も自分のFANYセッションで使う）|
| 公開 URL | `https://mypage-viewer.pages.dev` |

## ファイル構成

| ファイル | 役割 |
|---|---|
| `mypage-viewer/index.html` | ビューワー本体（フィルタ UI + カード表示） |
| `mypage-viewer/install.html` | ブックマークレット導入手順（友達共有用） |
| `mypage-viewer/assets/style.css` | ビューワーのスタイル（iPhone Safari 対応レスポンシブ） |
| `mypage-viewer/assets/viewer.js` | postMessage 受信・バリデーション・LocalStorage・フィルタ |
| `mypage-viewer/assets/collector.js` | ブックマークレット本体（ticket.fany.lol 上で実行） |
| `mypage-viewer/_headers` | Cloudflare Pages カスタムヘッダー（CORS: collector.js） |

## ブックマークレット（`collector.js`）

`ticket.fany.lol` 上で動作。`install.html` が `fetch('assets/collector.js')` で読み込んで minify し `javascript:` URL として提供する。

**動作フロー**:
1. `location.hostname !== 'ticket.fany.lol'` なら `alert` して終了
2. `window.open('https://mypage-viewer.pages.dev', '_mypage_viewer')` でビューワーを開く
3. `/history?ticket_page=N` を 1 から順次 `fetch`（`credentials: 'include'`、ページ間 400ms 待機）
4. `DOMParser` で `tr.g-table_borderless` + `tr.g-table_spanned` ペアをパース
5. 全件取得後 2.5秒待ってから `postMessage`（target origin: `https://mypage-viewer.pages.dev`）

**ページ終了判定**: `tr.g-table_borderless` が 0 件 → ループ終了。最大 19 ページで安全停止。

## DOM パース仕様

```
<tr class="g-table_borderless">                   ← メイン行
  <td data-label="イベント名">                     → title
  <td data-label="申込番号">                       → id
  <td data-label="予約日時">（<br>で日付/時刻分割） → reserved_at
<tr class="g-table_spanned">                      ← 詳細行（nested table 内）
  <td data-label="状況">
    （なし）入金済                                  → status: paid
    .g-tag-ok + p.g-color-key "入金済"             → status: paid（当選入金済）
    .g-tag-ok のみ                                 → status: won
    .g-tag-ng                                      → status: lost
    "未発券"                                       → status: unticketed
  <td data-label="公演日">
    正規表現 /(\d{4})\/(\d{2})\/(\d{2})/          → performance_date (YYYY-MM-DD)
    正規表現 /開場\s*(\d{2}:\d{2})/               → open_time
    正規表現 /開演\s*(\d{2}:\d{2})/               → start_time
  <td data-label="会場名">                         → venue
  <td data-label="席種">                           → seat_type
  <td data-label="数量">（N枚）                    → quantity (int)
  <td data-label="金額">（¥ N,NNN）               → price (int, 数字のみ抽出)
  <a class="g-link-key" href="...">               → detail_url（落選には無し）
```

## LocalStorage スキーマ（`fanaby_mypage_history`）

```json
{
  "schema_version": 1,
  "scraped_at": "2026-05-15T10:00:00.000Z",
  "entries": [
    {
      "id": "866264113",
      "title": "山口コンボイMVPへの道",
      "performance_date": "2026-06-15",
      "open_time": "21:00",
      "start_time": "21:15",
      "venue": "YOSHIMOTO ROPPONGI THEATER(東京都)",
      "reserved_at": "2026/05/05 (火) 10:01:17",
      "status": "paid",
      "status_text": "入金済",
      "seat_type": "整理番号付き自由席",
      "quantity": 1,
      "price": 2000,
      "detail_url": "https://ticket.fany.lol/history/detail/5468194"
    }
  ]
}
```

## ビューワーのフィルタ仕様

| フィルタ | 対象フィールド | デフォルト |
|---|---|---|
| キーワード（スペース区切り AND） | title + venue + seat_type | 空（全件） |
| 会場 | venue（ユニーク値から select 生成） | すべて |
| 公演日 from/to | performance_date（YYYY-MM-DD 比較） | 空 |
| ステータス: 入金済 | status === 'paid' | ON |
| ステータス: 当選 | status === 'won' | ON |
| ステータス: 未発券 | status === 'unticketed' | ON |
| ステータス: 落選 | status === 'lost' | **OFF** |
| ステータス: その他 | status === 'other' | ON |

## セキュリティ制約

- `viewer.js` はすべての DOM 挿入を `textContent` で行う（`innerHTML` 禁止）
- `detail_url` は `https://ticket.fany.lol/history/detail/` で始まることをバリデーション
- `postMessage` の origin は `https://ticket.fany.lol` のみ受け付ける
- `collector.js` の CORS ヘッダー: `Access-Control-Allow-Origin: https://ticket.fany.lol`（fanaby-eventの KV/Functions は不使用）

## 既知の制限

- Safari のブックマークレット URL 長制限: `collector.js` を minify した `javascript:` URL が長い場合、Safari が切り詰める可能性がある。その場合は `install.html` のローダー方式（`<script src>` 注入）を案内する
- ticket.fany.lol が CSP で外部スクリプトを拒否する場合、ローダー方式は使えない（self-contained `javascript:` URL のみ有効）
- 公演日セル内のタイトルは長い場合「・・・」と切り詰められる場合あり（イベント名は別セルで正確に取得済み）

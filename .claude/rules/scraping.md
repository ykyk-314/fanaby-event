---
paths: scripts/scrape_*.py
---

# スクレイピング対象サイト仕様

## 1. 芸人プロフィールページ

**URL形式:** `https://profile.yoshimoto.co.jp/talent/detail?id={talent_id}`

**取得対象要素:** `<div id="feed_ticket_info2">` 内の `<li class="feed-item-container">`

| フィールド | 取得元 |
|---|---|
| 公演名 | `<div class="feed-ticket-title">` |
| 公演日・開演時間 | `<div class="opt-feed-ft-dateside">` 内の `<p>`（M/D形式・年なし） |
| 出演者 | `<div class="opt-feed-ft-element-member">` |
| 所在地 | `<div class="opt-feed-ft-element-place">`（吉本所有劇場のみ記載） |
| 会場名 | `<div class="opt-feed-ft-element-venue">`（吉本非所有は「会場名（都道府県）」形式） |
| チケットURL | `<a class="feed-item-link">` の href |
| フライヤー画像 | `<img class="feed-item-img">` の src（登録なし時はタグ自体なし） |

**注意:**
- 日付は M/D 形式のみ（年なし）。`resolve_year()` で将来日として年を推定する
- JavaScript レンダリングが必要なため Selenium 使用

## 2. 劇場スケジュールページ

**URL形式:** `https://{theater_subdomain}.yoshimoto.co.jp/schedule/`
- サブドメインが劇場ごとに異なる（config.json の `theaters[].url` を参照）

**取得対象要素:**
- 月選択: `<ul class="calendar-month">` の `<li><a data-y="YYYY" data-m="MM">` をクリックで月切替
- 公演日: 親要素 `<div class="schedule-block" id="schedule{YYYY-MM-DD}">` の id から取得
- 公演データ: `<div class="schedule-time">` および `<div class="schedule-detail">`

| フィールド | 取得元 |
|---|---|
| 公演名 | `<div class="schedule-time"> <strong>` |
| 開場・開演・終演時間 | `<span class="bold em">` のテキスト |
| 出演者 | `<dd class="schedule-detail-member">` の `<a>` タグを innerText に置換、他タグ除去 |
| 前売・当日料金 | `<dd>` （料金の `<dl>`） |
| オンライン配信料金 | `<dd>` （オンラインの `<dl>`） |
| チケットURL | `.btn.is-s`（非ピンク）の href |
| 配信チケットURL | `.btn.is-s.is-pink` の href |

**注意:**
- 月切替は内部APIで `<div class="schedule">` のみ更新される（SPA的挙動）
- 出演者の `members` フィールドは文字列（配列でない）、改行区切り

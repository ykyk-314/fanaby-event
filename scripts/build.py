"""
events.json を読み込み、docs/index.html を生成するスクリプト。
CSS/JS は docs/assets/ に静的ファイルとして置いており、このスクリプトは触れない。
"""

import json
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
EVENTS_PATH = BASE_DIR / "data" / "events.json"
CONFIG_PATH = BASE_DIR / "data" / "config.json"
DOCS_DIR    = BASE_DIR / "docs"

WEEKDAYS = "月火水木金土日"


def format_date(iso_date: str) -> str:
    try:
        y, m, d = map(int, iso_date.split("-"))
        wd = WEEKDAYS[date(y, m, d).weekday()]
        return f"{y}/{m}/{d}({wd})"
    except Exception:
        return iso_date


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def format_price(price: dict | None) -> str:
    if not price:
        return ""
    parts = []
    if "advance" in price:
        parts.append(f"前売 ¥{price['advance']:,}")
    if "door" in price:
        parts.append(f"当日 ¥{price['door']:,}")
    if "online" in price:
        parts.append(f"配信 ¥{price['online']:,}")
    return " / ".join(parts)


def render_badge(status: str) -> str:
    if status == "new":
        return '<span class="badge badge-new">NEW</span>'
    if status == "updated":
        return '<span class="badge badge-updated">UPDATED</span>'
    return ""


def render_event_card(ev: dict) -> str:
    badge = render_badge(ev.get("status", ""))
    title = escape_html(ev.get("title", ""))
    date_str = format_date(ev.get("date", ""))
    ev_date = ev.get("date", "")

    times = []
    if ev.get("open_time"):
        times.append(f"開場 {ev['open_time']}")
    if ev.get("start_time"):
        times.append(f"開演 {ev['start_time']}")
    if ev.get("end_time"):
        times.append(f"終演 {ev['end_time']}")
    time_str = " | ".join(times)

    venue_raw = ev.get("venue") or ev.get("place") or ""
    venue     = escape_html(venue_raw)
    members   = escape_html(ev.get("members") or "")
    price_str = escape_html(format_price(ev.get("price")))

    ticket_btns = ""
    if ev.get("ticket_url"):
        ticket_btns += (
            f'<a href="{escape_html(ev["ticket_url"])}" '
            f'target="_blank" class="btn btn-ticket">チケット購入</a>'
        )
    if ev.get("online_url"):
        ticket_btns += (
            f'<a href="{escape_html(ev["online_url"])}" '
            f'target="_blank" class="btn btn-online">配信チケット</a>'
        )

    # フライヤー: ローカル画像優先、なければ外部URL
    img_src = ev.get("local_image") or ev.get("image_url") or ""
    flyer = ""
    if img_src:
        flyer = (
            f'<div class="flyer">'
            f'<img src="{escape_html(img_src)}" alt="フライヤー" loading="lazy" '
            f'class="flyer-img" onclick="openLightbox(this.src)">'
            f'</div>'
        )

    past_class = (
        "event-card past" if ev_date < date.today().isoformat() else "event-card"
    )

    info_rows = (
        f'<div class="info-row">'
        f'<span class="info-label">日時</span>'
        f'<span>{date_str}{" " + time_str if time_str else ""}</span>'
        f'</div>'
    )
    if venue:
        info_rows += (
            f'<div class="info-row">'
            f'<span class="info-label">会場</span><span>{venue}</span>'
            f'</div>'
        )
    if members:
        info_rows += (
            f'<div class="info-row">'
            f'<span class="info-label">出演者</span>'
            f'<span class="members-text">{members}</span>'
            f'</div>'
        )
    if price_str:
        info_rows += (
            f'<div class="info-row">'
            f'<span class="info-label">料金</span><span>{price_str}</span>'
            f'</div>'
        )

    status_select = (
        f'<div class="viewing-wrap" data-viewing-status="">'
        f'<select class="viewing-select" data-event-id="{escape_html(ev.get("id", ""))}">'
        f'<option value="">＋ 記録する</option>'
        f'<option value="want">行きたい</option>'
        f'<option value="lottery_applied">先行申込済み</option>'
        f'<option value="lottery_lost">落選</option>'
        f'<option value="purchased">購入済み</option>'
        f'<option value="attended">行った</option>'
        f'</select>'
        f'</div>'
    )
    btns_html = f'<div class="card-btns">{ticket_btns}{status_select}</div>'

    return (
        f'<div class="{past_class}" '
        f'data-talent="{escape_html(ev.get("talent_id", ""))}" '
        f'data-venue="{escape_html(venue_raw)}" '
        f'data-date="{escape_html(ev_date)}" '
        f'data-event-id="{escape_html(ev.get("id", ""))}" '
        f'data-viewing-status="">'
        f'<div class="card-header">{badge}<span class="card-title">{title}</span></div>'
        f'<div class="card-body">'
        f'<div class="card-left"><div class="card-info">{info_rows}</div>{btns_html}</div>'
        f'{flyer}'
        f'</div>'
        f'</div>'
    )



def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data   = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    events: list[dict] = data.get("events", [])
    updated_at: str    = data.get("updated_at") or ""
    talents = config["talents"]
    today   = date.today().isoformat()

    all_future = [e for e in events if e.get("date", "") >= today]
    all_past   = [e for e in events if e.get("date", "") < today]

    # タブボタン
    tab_buttons = '<button class="tab-btn active" data-tab="all">全員</button>'
    for t in talents:
        tab_buttons += (
            f'<button class="tab-btn" data-tab="{t["id"]}">'
            f'{escape_html(t["name"])}</button>'
        )

    # 全カードを単一DOMに配置（タブ切り替えはJSのフィルタで行う）
    future_cards = "".join(render_event_card(e) for e in all_future)
    past_cards   = "".join(render_event_card(e) for e in all_past)

    content_html = ""
    if all_future:
        content_html += (
            f'<div class="section" id="section-future">'
            f'<h3 class="section-title">今後の公演'
            f'（<span class="section-count">{len(all_future)}</span>件）</h3>'
            f'{future_cards}</div>'
        )
    if all_past:
        content_html += (
            f'<details class="section-past" id="section-past">'
            f'<summary>過去の公演'
            f'（<span class="section-count">{len(all_past)}</span>件）</summary>'
            f'{past_cards}</details>'
        )
    if not all_future and not all_past:
        content_html = '<p class="empty">公演情報がありません</p>'

    updated_str = (
        updated_at.replace("T", " ").replace("+09:00", " JST") if updated_at else "—"
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>公演スケジュール</title>
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
  <header>
    <h1>公演スケジュール</h1>
    <p>最終更新: {escape_html(updated_str)}</p>
  </header>
  <div class="container">
    <div class="tabs">
      {tab_buttons}
    </div>
    <div class="filter-bar" id="filterBar">
      <div>
        <label>会場</label>
        <select id="filterVenue">
          <option value="">すべて</option>
        </select>
        <label>観覧ステータス</label>
        <select id="filterViewingStatus">
          <option value="">すべて</option>
          <option value="want">行きたい</option>
          <option value="lottery_applied">先行申込済み</option>
          <option value="lottery_lost">落選</option>
          <option value="purchased">購入済み</option>
          <option value="attended">行った</option>
          <option value="none">未設定</option>
        </select>
      </div>
      <div>
        <label>日付（から）</label>
        <input type="date" id="filterDateFrom">
        <label>（まで）</label>
        <input type="date" id="filterDateTo">
        <button class="filter-reset" id="filterReset">リセット</button>
        <span class="filter-count" id="filterCount"></span>
      </div>
    </div>
    {content_html}
  </div>
  <div id="lightbox" onclick="closeLightbox()">
    <img id="lightboxImg" src="" alt="フライヤー拡大">
  </div>
  <script src="assets/script.js"></script>
</body>
</html>"""

    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")

    print(
        f"build 完了: 今後 {len(all_future)} 件、過去 {len(all_past)} 件\n"
        f"  → {DOCS_DIR / 'index.html'}"
    )


if __name__ == "__main__":
    main()

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

    btns_html = f'<div class="card-btns">{ticket_btns}</div>' if ticket_btns else ""

    return (
        f'<div class="{past_class}" '
        f'data-talent="{ev.get("talent_id", "")}" '
        f'data-venue="{escape_html(venue_raw)}" '
        f'data-date="{ev_date}">'
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

    talent_sections = []
    for t in talents:
        tid = t["id"]
        talent_sections.append({
            "id":     tid,
            "name":   t["name"],
            "future": [e for e in all_future if e.get("talent_id") == tid],
            "past":   [e for e in all_past   if e.get("talent_id") == tid],
        })

    # タブボタン
    tab_buttons = '<button class="tab-btn active" data-tab="all">全員</button>'
    for t in talent_sections:
        tab_buttons += (
            f'<button class="tab-btn" data-tab="{t["id"]}">'
            f'{escape_html(t["name"])}</button>'
        )

    def section_html(label: str, evs: list[dict], collapsible: bool = False) -> str:
        if not evs:
            return ""
        cards      = "".join(render_event_card(e) for e in evs)
        count_span = (
            f'<span class="section-count" data-total="{len(evs)}">'
            f'{len(evs)}</span>'
        )
        if collapsible:
            return (
                f'<details class="section-past">'
                f'<summary>{label}（{count_span}件）</summary>'
                f'{cards}</details>'
            )
        return (
            f'<div class="section">'
            f'<h3 class="section-title">{label}（{count_span}件）</h3>'
            f'{cards}</div>'
        )

    panels_html = ""

    panels_html += '<div class="tab-panel active" data-panel="all">'
    panels_html += section_html("今後の公演", all_future)
    panels_html += section_html("過去の公演", all_past, collapsible=True)
    if not all_future and not all_past:
        panels_html += '<p class="empty">公演情報がありません</p>'
    panels_html += "</div>"

    for t in talent_sections:
        panels_html += f'<div class="tab-panel" data-panel="{t["id"]}">'
        panels_html += section_html("今後の公演", t["future"])
        panels_html += section_html("過去の公演", t["past"], collapsible=True)
        if not t["future"] and not t["past"]:
            panels_html += '<p class="empty">公演情報がありません</p>'
        panels_html += "</div>"

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
      <label>会場</label>
      <select id="filterVenue">
        <option value="">すべて</option>
      </select>
      <label>日付（から）</label>
      <input type="date" id="filterDateFrom">
      <label>（まで）</label>
      <input type="date" id="filterDateTo">
      <button class="filter-reset" id="filterReset">リセット</button>
      <span class="filter-count" id="filterCount"></span>
    </div>
    {panels_html}
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

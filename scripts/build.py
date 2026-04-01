"""
events.json を読み込み、docs/index.html を生成するスクリプト。
データをHTMLにインライン埋め込みするため、GitHub Pages での file:// 閲覧も不要。
"""

import json
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
EVENTS_PATH = BASE_DIR / "data" / "events.json"
CONFIG_PATH = BASE_DIR / "data" / "config.json"
OUTPUT_PATH = BASE_DIR / "docs" / "index.html"

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
    venue = escape_html(venue_raw)
    members = escape_html(ev.get("members") or "")
    price_str = escape_html(format_price(ev.get("price")))

    ticket_btns = ""
    if ev.get("ticket_url"):
        ticket_btns += f'<a href="{escape_html(ev["ticket_url"])}" target="_blank" class="btn btn-ticket">チケット購入</a>'
    if ev.get("online_url"):
        ticket_btns += f'<a href="{escape_html(ev["online_url"])}" target="_blank" class="btn btn-online">配信チケット</a>'

    flyer = ""
    if ev.get("image_url"):
        img_url = escape_html(ev["image_url"])
        flyer = (
            f'<div class="flyer">'
            f'<img src="{img_url}" alt="フライヤー" loading="lazy" '
            f'class="flyer-img" onclick="openLightbox(this.src)">'
            f'</div>'
        )

    past_class = "event-card past" if ev_date < date.today().isoformat() else "event-card"

    info_rows = f'<div class="info-row"><span class="info-label">日時</span><span>{date_str}{" " + time_str if time_str else ""}</span></div>'
    if venue:
        info_rows += f'<div class="info-row"><span class="info-label">会場</span><span>{venue}</span></div>'
    if members:
        info_rows += f'<div class="info-row"><span class="info-label">出演者</span><span class="members-text">{members}</span></div>'
    if price_str:
        info_rows += f'<div class="info-row"><span class="info-label">料金</span><span>{price_str}</span></div>'

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
    data = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    events: list[dict] = data.get("events", [])
    updated_at: str = data.get("updated_at") or ""
    talents = config["talents"]
    today = date.today().isoformat()

    all_future = [e for e in events if e.get("date", "") >= today]
    all_past = [e for e in events if e.get("date", "") < today]

    talent_sections = []
    for t in talents:
        tid = t["id"]
        talent_sections.append({
            "id": tid,
            "name": t["name"],
            "future": [e for e in all_future if e.get("talent_id") == tid],
            "past":   [e for e in all_past  if e.get("talent_id") == tid],
        })

    # タブボタン
    tab_buttons = '<button class="tab-btn active" data-tab="all">全員</button>'
    for t in talent_sections:
        tab_buttons += f'<button class="tab-btn" data-tab="{t["id"]}">{escape_html(t["name"])}</button>'

    def section_html(label: str, evs: list[dict], collapsible: bool = False) -> str:
        if not evs:
            return ""
        cards = "".join(render_event_card(e) for e in evs)
        count_span = f'<span class="section-count" data-total="{len(evs)}">{len(evs)}</span>'
        if collapsible:
            return (
                f'<details class="section-past">'
                f'<summary>{label}（{count_span}件）</summary>'
                f'{cards}'
                f'</details>'
            )
        return (
            f'<div class="section">'
            f'<h3 class="section-title">{label}（{count_span}件）</h3>'
            f'{cards}'
            f'</div>'
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

    updated_str = updated_at.replace("T", " ").replace("+09:00", " JST") if updated_at else "—"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>公演スケジュール</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Hiragino Sans', 'Noto Sans JP', sans-serif; background: #f0f0f0; color: #333; }}
    header {{ background: #1a1a2e; color: #fff; padding: 16px 20px; }}
    header h1 {{ font-size: 18px; font-weight: bold; }}
    header p {{ font-size: 12px; color: #aaa; margin-top: 4px; }}
    .container {{ max-width: 900px; margin: 0 auto; padding: 16px; }}

    /* タブ */
    .tabs {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }}
    .tab-btn {{ padding: 6px 16px; border: 1px solid #ccc; background: #fff; border-radius: 20px; cursor: pointer; font-size: 14px; transition: all .15s; }}
    .tab-btn.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}

    /* フィルターバー */
    .filter-bar {{ background: #fff; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    .filter-bar label {{ font-size: 12px; color: #888; white-space: nowrap; }}
    .filter-bar select,
    .filter-bar input[type="date"] {{ border: 1px solid #ddd; border-radius: 4px; padding: 4px 8px; font-size: 13px; background: #fafafa; color: #333; }}
    .filter-bar select {{ min-width: 160px; max-width: 260px; }}
    .filter-reset {{ margin-left: auto; padding: 4px 12px; font-size: 12px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; color: #666; }}
    .filter-reset:hover {{ background: #f0f0f0; }}
    .filter-count {{ font-size: 12px; color: #999; white-space: nowrap; }}

    /* セクション */
    .section {{ margin-bottom: 20px; }}
    .section-title {{ font-size: 14px; font-weight: bold; color: #555; margin-bottom: 10px; padding-left: 10px; border-left: 3px solid #1a1a2e; }}
    .section-past {{ margin-bottom: 20px; }}
    .section-past summary {{ font-size: 14px; color: #888; cursor: pointer; padding: 8px 0; margin-bottom: 6px; }}

    /* イベントカード */
    .event-card {{ background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08); transition: opacity .15s; }}
    .event-card.past {{ opacity: .55; }}
    .event-card.hidden {{ display: none; }}
    .card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
    .card-title {{ font-size: 15px; font-weight: bold; line-height: 1.4; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold; flex-shrink: 0; }}
    .badge-new {{ background: #27ae60; color: #fff; }}
    .badge-updated {{ background: #2980b9; color: #fff; }}

    /* カード本体: 左=情報、右=フライヤー */
    .card-body {{ display: flex; gap: 16px; align-items: flex-start; }}
    .card-left {{ flex: 1; min-width: 0; }}
    .card-info {{ font-size: 13px; }}
    .info-row {{ display: flex; gap: 8px; margin-bottom: 5px; line-height: 1.5; }}
    .info-label {{ color: #888; min-width: 48px; white-space: nowrap; flex-shrink: 0; }}
    .members-text {{ white-space: pre-line; }}
    .card-btns {{ margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
    .btn {{ display: inline-block; padding: 7px 16px; border-radius: 4px; font-size: 13px; text-decoration: none; font-weight: bold; }}
    .btn-ticket {{ background: #e74c3c; color: #fff; }}
    .btn-online {{ background: #8e44ad; color: #fff; }}

    /* フライヤー */
    .flyer {{ flex-shrink: 0; }}
    .flyer-img {{ width: 140px; border-radius: 6px; object-fit: cover; cursor: zoom-in; display: block; transition: opacity .15s; }}
    .flyer-img:hover {{ opacity: .85; }}

    .empty {{ color: #aaa; font-size: 14px; text-align: center; padding: 32px; }}

    /* ライトボックス */
    #lightbox {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.82); z-index: 1000; align-items: center; justify-content: center; cursor: zoom-out; }}
    #lightbox.open {{ display: flex; }}
    #lightbox img {{ max-width: 90vw; max-height: 90vh; border-radius: 6px; object-fit: contain; box-shadow: 0 4px 32px rgba(0,0,0,.5); }}

    @media (max-width: 560px) {{
      .card-body {{ flex-direction: column-reverse; }}
      .flyer-img {{ width: 100%; max-width: 200px; }}
      .filter-bar {{ gap: 8px; }}
      .filter-bar select {{ min-width: 0; width: 100%; }}
    }}
  </style>
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

    <!-- フィルターバー（全タブ共通） -->
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

  <!-- ライトボックス -->
  <div id="lightbox" onclick="closeLightbox()">
    <img id="lightboxImg" src="" alt="フライヤー拡大">
  </div>

  <script>
    // ---- タブ切り替え ----
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.querySelector('[data-panel="' + btn.dataset.tab + '"]').classList.add('active');
        resetFilters();
        buildVenueOptions();
        applyFilters();
      }});
    }});

    // ---- ライトボックス ----
    function openLightbox(src) {{
      document.getElementById('lightboxImg').src = src;
      document.getElementById('lightbox').classList.add('open');
    }}
    function closeLightbox() {{
      document.getElementById('lightbox').classList.remove('open');
    }}
    document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeLightbox(); }});

    // ---- フィルター ----
    function activePanel() {{
      return document.querySelector('.tab-panel.active');
    }}

    function allCardsInPanel(panel) {{
      return Array.from(panel.querySelectorAll('.event-card'));
    }}

    function buildVenueOptions() {{
      const panel = activePanel();
      const venues = new Set();
      allCardsInPanel(panel).forEach(c => {{
        const v = c.dataset.venue;
        if (v) venues.add(v);
      }});
      const sel = document.getElementById('filterVenue');
      const current = sel.value;
      sel.innerHTML = '<option value="">すべて</option>';
      [...venues].sort().forEach(v => {{
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        if (v === current) opt.selected = true;
        sel.appendChild(opt);
      }});
    }}

    function applyFilters() {{
      const venue = document.getElementById('filterVenue').value;
      const from  = document.getElementById('filterDateFrom').value;
      const to    = document.getElementById('filterDateTo').value;
      const panel = activePanel();
      const cards = allCardsInPanel(panel);
      let visible = 0;
      cards.forEach(c => {{
        const cv = c.dataset.venue || '';
        const cd = c.dataset.date  || '';
        const ok = (!venue || cv === venue)
                && (!from  || cd >= from)
                && (!to    || cd <= to);
        c.classList.toggle('hidden', !ok);
        if (ok) visible++;
      }});
      // 件数表示を更新
      document.getElementById('filterCount').textContent =
        (venue || from || to) ? `${{visible}} 件表示中` : '';
      // section-title のカウントも更新
      panel.querySelectorAll('.section-title, .section-past summary').forEach(el => {{
        const section = el.closest('.section, .section-past');
        if (!section) return;
        const total = section.querySelectorAll('.event-card').length;
        const shown = section.querySelectorAll('.event-card:not(.hidden)').length;
        const countEl = el.querySelector('.section-count');
        if (countEl) countEl.textContent = (venue || from || to) ? `${{shown}}/${{countEl.dataset.total}}` : countEl.dataset.total;
      }});
    }}

    function resetFilters() {{
      document.getElementById('filterVenue').value = '';
      document.getElementById('filterDateFrom').value = '';
      document.getElementById('filterDateTo').value = '';
    }}

    document.getElementById('filterVenue').addEventListener('change', applyFilters);
    document.getElementById('filterDateFrom').addEventListener('change', applyFilters);
    document.getElementById('filterDateTo').addEventListener('change', applyFilters);
    document.getElementById('filterReset').addEventListener('click', () => {{
      resetFilters();
      applyFilters();
    }});

    // 初期化
    buildVenueOptions();
  </script>
</body>
</html>"""

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"build 完了: 今後 {len(all_future)} 件、過去 {len(all_past)} 件 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

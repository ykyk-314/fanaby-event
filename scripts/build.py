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

    times = []
    if ev.get("open_time"):
        times.append(f"開場 {ev['open_time']}")
    if ev.get("start_time"):
        times.append(f"開演 {ev['start_time']}")
    if ev.get("end_time"):
        times.append(f"終演 {ev['end_time']}")
    time_str = " | ".join(times)

    venue = escape_html(ev.get("venue") or ev.get("place") or "")
    members = escape_html("、".join(ev.get("members", [])))
    price_str = escape_html(format_price(ev.get("price")))

    ticket_btns = ""
    if ev.get("ticket_url"):
        url = escape_html(ev["ticket_url"])
        ticket_btns += f'<a href="{url}" target="_blank" class="btn btn-ticket">チケット購入</a>'
    if ev.get("online_url"):
        url = escape_html(ev["online_url"])
        ticket_btns += f'<a href="{url}" target="_blank" class="btn btn-online">配信チケット</a>'

    flyer = ""
    if ev.get("image_url"):
        url = escape_html(ev["image_url"])
        flyer = f'<div class="flyer"><img src="{url}" alt="フライヤー" loading="lazy"></div>'

    past_class = "event-card past" if ev.get("date", "") < date.today().isoformat() else "event-card"

    return f"""
    <div class="{past_class}" data-talent="{ev.get('talent_id','')}">
      <div class="card-header">
        {badge}
        <span class="card-title">{title}</span>
      </div>
      <div class="card-body">
        <div class="card-info">
          <div class="info-row"><span class="info-label">日時</span><span>{date_str}{' ' + time_str if time_str else ''}</span></div>
          {'<div class="info-row"><span class="info-label">会場</span><span>' + venue + '</span></div>' if venue else ''}
          {'<div class="info-row"><span class="info-label">出演者</span><span>' + members + '</span></div>' if members else ''}
          {'<div class="info-row"><span class="info-label">料金</span><span>' + price_str + '</span></div>' if price_str else ''}
        </div>
        {flyer}
      </div>
      {'<div class="card-btns">' + ticket_btns + '</div>' if ticket_btns else ''}
    </div>"""


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    events: list[dict] = data.get("events", [])
    updated_at: str = data.get("updated_at") or ""
    talents = config["talents"]
    today = date.today().isoformat()

    # 芸人ごとに今後・過去に分類
    talent_sections = []
    all_future = [e for e in events if e.get("date", "") >= today]
    all_past = [e for e in events if e.get("date", "") < today]

    for t in talents:
        tid = t["id"]
        future = [e for e in all_future if e.get("talent_id") == tid]
        past = [e for e in all_past if e.get("talent_id") == tid]
        talent_sections.append({
            "id": tid,
            "name": t["name"],
            "future": future,
            "past": past,
        })

    # タブHTML生成
    tab_buttons = '<button class="tab-btn active" data-tab="all">全員</button>'
    for t in talent_sections:
        tab_buttons += f'<button class="tab-btn" data-tab="{t["id"]}">{escape_html(t["name"])}</button>'

    # コンテンツHTML生成
    def section_html(label: str, evs: list[dict], collapsible: bool = False) -> str:
        if not evs:
            return ""
        cards = "".join(render_event_card(e) for e in evs)
        if collapsible:
            return f"""
        <details class="section-past">
          <summary>{label}（{len(evs)}件）</summary>
          {cards}
        </details>"""
        return f"""
        <div class="section">
          <h3 class="section-title">{label}（{len(evs)}件）</h3>
          {cards}
        </div>"""

    panels_html = ""

    # 全員パネル
    panels_html += '<div class="tab-panel active" data-panel="all">'
    panels_html += section_html("今後の公演", all_future)
    panels_html += section_html("過去の公演", all_past, collapsible=True)
    if not all_future and not all_past:
        panels_html += '<p class="empty">公演情報がありません</p>'
    panels_html += "</div>"

    # 芸人別パネル
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
    body {{ font-family: 'Hiragino Sans', 'Noto Sans JP', sans-serif; background: #f5f5f5; color: #333; }}
    header {{ background: #1a1a2e; color: #fff; padding: 16px 20px; }}
    header h1 {{ font-size: 18px; font-weight: bold; }}
    header p {{ font-size: 12px; color: #aaa; margin-top: 4px; }}
    .container {{ max-width: 800px; margin: 0 auto; padding: 16px; }}
    .tabs {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }}
    .tab-btn {{ padding: 6px 16px; border: 1px solid #ccc; background: #fff; border-radius: 20px; cursor: pointer; font-size: 14px; transition: all .15s; }}
    .tab-btn.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .section {{ margin-bottom: 24px; }}
    .section-title {{ font-size: 14px; font-weight: bold; color: #666; margin-bottom: 10px; padding-left: 10px; border-left: 3px solid #1a1a2e; }}
    .section-past summary {{ font-size: 14px; color: #888; cursor: pointer; padding: 8px 0; margin-bottom: 8px; }}
    .event-card {{ background: #fff; border-radius: 8px; padding: 14px; margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .event-card.past {{ opacity: .6; }}
    .card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
    .card-title {{ font-size: 15px; font-weight: bold; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold; }}
    .badge-new {{ background: #27ae60; color: #fff; }}
    .badge-updated {{ background: #2980b9; color: #fff; }}
    .card-body {{ display: flex; gap: 12px; align-items: flex-start; }}
    .card-info {{ flex: 1; font-size: 13px; }}
    .info-row {{ display: flex; gap: 8px; margin-bottom: 4px; }}
    .info-label {{ color: #888; min-width: 50px; white-space: nowrap; }}
    .flyer img {{ width: 100px; border-radius: 4px; object-fit: cover; }}
    .card-btns {{ margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }}
    .btn {{ display: inline-block; padding: 6px 14px; border-radius: 4px; font-size: 13px; text-decoration: none; font-weight: bold; }}
    .btn-ticket {{ background: #e74c3c; color: #fff; }}
    .btn-online {{ background: #8e44ad; color: #fff; }}
    .empty {{ color: #aaa; font-size: 14px; text-align: center; padding: 32px; }}
    @media (max-width: 500px) {{
      .card-body {{ flex-direction: column; }}
      .flyer img {{ width: 80px; }}
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
    {panels_html}
  </div>
  <script>
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.querySelector('[data-panel="' + btn.dataset.tab + '"]').classList.add('active');
      }});
    }});
  </script>
</body>
</html>"""

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    total = len(all_future) + len(all_past)
    print(f"build 完了: 今後 {len(all_future)} 件、過去 {len(all_past)} 件 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

"""
events.json を読み込み、docs/schedule.html（スケジュールカードのHTMLフラグメント）を生成するスクリプト。
docs/index.html はヘッダー・芸人タブ・フィルターバーを含む静的ファイルで、このスクリプトは触れない。
CSS/JS は docs/assets/ に静的ファイルとして置いており、このスクリプトは触れない。
"""

import json
from datetime import date
from pathlib import Path
from urllib.parse import quote

BASE_DIR        = Path(__file__).parent.parent
EVENTS_PATH     = BASE_DIR / "data" / "events.json"
DEADLINES_PATH  = BASE_DIR / "data" / "ticket_deadlines.json"
DOCS_DIR        = BASE_DIR / "docs"

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


def safe_url(url: str | None) -> str | None:
    """http(s):// で始まる URL のみ通過させる。javascript: 等を無効化。"""
    if not url:
        return None
    if url.startswith("https://") or url.startswith("http://"):
        return url
    return None


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


def ticket_badge_class(status_text: str) -> str:
    """ステータステキストからCSSクラスを返す"""
    if "中" in status_text:   # 先着発売中 / 抽選受付中
        return "tbadge-active"
    if "前" in status_text:   # 先着発売前
        return "tbadge-upcoming"
    return "tbadge-ended"     # 抽選受付終了 / その他


def render_ticket_deadlines(tickets: list) -> str:
    """チケット受付情報の HTML を生成する"""
    if not tickets:
        return ""
    rows = ""
    for t in tickets:
        cls = ticket_badge_class(t.get("status_text", ""))
        rows += (
            f'<div class="ticket-row">'
            f'<span class="tbadge {cls}">{escape_html(t.get("status_text", ""))}</span>'
            f'<span class="tname">{escape_html(t.get("name", ""))}</span>'
            f'<span class="tperiod">{escape_html(t.get("start", ""))} 〜 {escape_html(t.get("end", ""))}</span>'
            f'</div>'
        )
    return f'<div class="ticket-deadlines">{rows}</div>'


def render_badge(status: str) -> str:
    if status == "new":
        return '<span class="badge badge-new">NEW</span>'
    if status == "updated":
        return '<span class="badge badge-updated">UPDATED</span>'
    return ""


def make_gcal_url(ev: dict) -> str | None:
    """公演情報から Google Calendar 予定追加 URL を生成する。"""
    date_str = ev.get("date", "")
    if not date_str:
        return None

    open_time  = ev.get("open_time")  or ""
    start_time = ev.get("start_time") or ""
    end_time   = ev.get("end_time")   or ""

    start_base = open_time or start_time
    if not start_base:
        return None

    date_compact = date_str.replace("-", "")
    start_dt = f"{date_compact}T{start_base.replace(':', '')}00"

    if end_time:
        end_dt = f"{date_compact}T{end_time.replace(':', '')}00"
    else:
        base_for_end = start_time or open_time
        h, m = map(int, base_for_end.split(":"))
        h = (h + 1) % 24
        end_dt = f"{date_compact}T{h:02d}{m:02d}00"

    times = []
    if open_time:
        times.append(f"開場 {open_time}")
    if start_time:
        times.append(f"開演 {start_time}")
    if end_time:
        times.append(f"終演 {end_time}")
    details_parts = [" | ".join(times)] if times else []
    members = ev.get("members") or ""
    if members:
        details_parts.append(members)
    details_text = "\n".join(details_parts)

    params = [
        ("action",   "TEMPLATE"),
        ("text",     ev.get("title", "")),
        ("dates",    f"{start_dt}/{end_dt}"),
        ("ctz",      "Asia/Tokyo"),
        ("location", ev.get("venue") or ""),
        ("details",  details_text),
    ]
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params)
    return f"https://calendar.google.com/calendar/render?{query}"


def render_event_card(ev: dict, tickets: list | None = None) -> str:
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

    # サマリ表示用: 開演優先、無ければ開場時刻のみ
    summary_time = ev.get("start_time") or ev.get("open_time") or ""

    venue_raw      = ev.get("venue") or ""
    prefecture_raw = ev.get("prefecture") or ""
    venue_display  = escape_html(venue_raw)
    if prefecture_raw:
        venue_display += f' / {escape_html(prefecture_raw)}'
    members   = escape_html(ev.get("members") or "")
    price_str = escape_html(format_price(ev.get("price")))

    ticket_btns = ""
    if safe_url(ev.get("ticket_url")):
        ticket_btns += (
            f'<a href="{escape_html(ev["ticket_url"])}" '
            f'target="_blank" class="btn btn-ticket">チケット購入</a>'
        )
    if safe_url(ev.get("online_url")):
        ticket_btns += (
            f'<a href="{escape_html(ev["online_url"])}" '
            f'target="_blank" class="btn btn-online">配信チケット</a>'
        )
    gcal_url = make_gcal_url(ev)
    gcal_btn = (
        f'<a href="{escape_html(gcal_url)}" target="_blank" rel="noopener"'
        f' class="btn btn-gcal" title="Googleカレンダーに追加">&#x1F4C5;</a>'
    ) if gcal_url else ""

    # フライヤー: ローカル画像優先、なければ外部URL。サマリにはサムネイルのみ置き、
    # 拡大表示（モーダル内フライヤー・ライトボックス）は script.js 側でこの src を使い回す
    img_src = ev.get("local_image") or ev.get("image_url") or ""
    flyer_thumb = ""
    if img_src:
        flyer_thumb = (
            f'<div class="flyer-thumb-wrap">'
            f'<img src="{escape_html(img_src)}" alt="フライヤー" loading="lazy" class="flyer-thumb">'
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
    if venue_display:
        info_rows += (
            f'<div class="info-row">'
            f'<span class="info-label">会場</span><span>{venue_display}</span>'
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
    if tickets:
        info_rows += (
            f'<div class="info-row ticket-info-row">'
            f'<span class="info-label">受付</span>'
            f'{render_ticket_deadlines(tickets)}'
            f'</div>'
        )

    notice_raw = ev.get("notice") or ""
    notice_html = ""
    if notice_raw:
        notice_html = (
            f'<details class="notice-details">'
            f'<summary class="notice-summary">お知らせ</summary>'
            f'<p class="notice-text">{escape_html(notice_raw)}</p>'
            f'</details>'
        )

    ev_id = escape_html(ev.get("id", ""))
    status_select = (
        f'<div class="viewing-wrap" data-event-id="{ev_id}" data-viewing-status="">'
        f'<select class="viewing-select" data-event-id="{ev_id}">'
        f'<option value="">＋ 記録する</option>'
        f'<option value="want">行きたい</option>'
        f'<option value="lottery_applied">先行申込済み</option>'
        f'<option value="lottery_lost">落選</option>'
        f'<option value="purchased">購入済み</option>'
        f'<option value="attended">行った</option>'
        f'</select>'
        f'</div>'
    )
    remind_btn = (
        f'<button class="remind-btn" data-event-id="{ev_id}" data-remind=""'
        f' title="チケットリマインドをONにする">&#x1F514;</button>'
    )
    exclude_btn = (
        f'<button class="exclude-btn" data-event-id="{ev_id}"'
        f' title="この公演を除外する">除外</button>'
    )
    btns_html = f'<div class="card-btns">{ticket_btns}{gcal_btn}{status_select}{remind_btn}{exclude_btn}</div>'
    memo_html = (
        f'<div class="memo-wrap">'
        f'<textarea class="memo-input" data-event-id="{ev_id}"'
        f' placeholder="メモ（ネタ・感想など）" rows="2"></textarea>'
        f'</div>'
    )

    talents = ev.get("talents") or {}
    talent_ids_str = " ".join(sorted(talents.keys()))

    summary_datetime = date_str + (f" {summary_time}" if summary_time else "")
    summary_members = (
        f'<span class="members-text">{members}</span>' if members else ""
    )

    card_summary = (
        f'<div class="card-summary">'
        f'<div class="card-summary-text">'
        f'<div class="card-header">{badge}<span class="card-title">{title}</span>'
        f'<span class="status-label" hidden></span></div>'
        f'<div class="summary-meta">'
        f'<span class="summary-datetime">{summary_datetime}</span>'
        f'{summary_members}'
        f'</div>'
        f'</div>'
        f'{flyer_thumb}'
        f'</div>'
    )
    card_detail = (
        f'<div class="card-detail" hidden>'
        f'<div class="card-info">{info_rows}</div>'
        f'{notice_html}{btns_html}{memo_html}'
        f'</div>'
    )

    return (
        f'<div class="{past_class}" '
        f'data-excluded="false" '
        f'data-talent="{escape_html(talent_ids_str)}" '
        f'data-venue="{escape_html(venue_raw)}" '
        f'data-prefecture="{escape_html(prefecture_raw)}" '
        f'data-date="{escape_html(ev_date)}" '
        f'data-event-id="{ev_id}" '
        f'data-title="{escape_html(ev.get("title", ""))}" '
        f'data-members="{escape_html(ev.get("members") or "")}" '
        f'data-viewing-status="">'
        f'{card_summary}'
        f'{card_detail}'
        f'</div>'
    )



def main():
    data   = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    events: list[dict] = data.get("events", [])
    updated_at: str    = data.get("updated_at") or ""
    today   = date.today().isoformat()

    # ticket_deadlines.json を読み込み（存在しない場合は空）
    ticket_map: dict[str, list] = {}
    if DEADLINES_PATH.exists():
        _dl_content = DEADLINES_PATH.read_text(encoding="utf-8").strip()
        if _dl_content:
            deadlines = json.loads(_dl_content)
        else:
            deadlines = {}
        ticket_map = {
            eid: ev["tickets"]
            for eid, ev in deadlines.get("events", {}).items()
            if ev.get("tickets")
        }

    all_future = [e for e in events if e.get("date", "") >= today]
    all_past   = [e for e in events if e.get("date", "") < today]

    # 全カードを単一DOMに配置（タブ切り替えはJSのフィルタで行う）
    future_cards = "".join(render_event_card(e, ticket_map.get(e["id"])) for e in all_future)
    past_cards   = "".join(render_event_card(e, ticket_map.get(e["id"])) for e in all_past)

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

    # docs/index.html（静的ファイル）が fetch して差し込むスケジュール部分のみを出力
    meta_html = f'<div id="scheduleMeta" data-updated="{escape_html(updated_str)}" hidden></div>'
    fragment = meta_html + content_html

    (DOCS_DIR / "schedule.html").write_text(fragment, encoding="utf-8")

    print(
        f"build 完了: 今後 {len(all_future)} 件、過去 {len(all_past)} 件\n"
        f"  → {DOCS_DIR / 'schedule.html'}"
    )


if __name__ == "__main__":
    main()

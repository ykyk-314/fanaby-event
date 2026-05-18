/* 履歴ビューワー
 * - postMessage で collector.js からデータを受信
 * - LocalStorage に永続保存
 * - フィルタ UI でリアルタイム絞り込み
 */

const STORAGE_KEY = 'fanaby_mypage_history';
const FANY_ORIGIN = 'https://ticket.fany.lol';
const VALID_STATUSES = ['paid', 'won', 'unticketed', 'lost', 'other'];

const STATUS_LABEL = {
  paid:       '入金済',
  won:        '当選',
  unticketed: '未発券',
  lost:       '落選',
  other:      '',
};

const STATUS_COLOR = {
  paid:       '#27ae60',
  won:        '#3498db',
  unticketed: '#e67e22',
  lost:       '#95a5a6',
  other:      '#7f8c8d',
};

// 会場 select の優先表示順（部分一致）
const PREFERRED_VENUES = [
  'ルミネtheよしもと',
  '渋谷よしもと漫才劇場',
  '神保町よしもと漫才劇場',
  '大宮ラクーンよしもと漫才劇場',
  'よしもと幕張イオンモール劇場',
];

// ---- ストレージ ----

function loadData() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (_) { return null; }
}

function saveData(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

// ---- バリデーション（postMessage 受信時） ----

function validateEntries(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((e) => e && typeof e === 'object')
    .map((e) => ({
      id:               String(e.id || ''),
      title:            String(e.title || ''),
      performance_date: String(e.performance_date || ''),
      open_time:        String(e.open_time || ''),
      start_time:       String(e.start_time || ''),
      venue:            String(e.venue || ''),
      reserved_at:      String(e.reserved_at || ''),
      status:           VALID_STATUSES.includes(e.status) ? e.status : 'other',
      status_text:      String(e.status_text || ''),
      seat_type:        String(e.seat_type || ''),
      quantity:         Number.isFinite(+e.quantity) ? Math.max(1, +e.quantity) : 1,
      price:            Number.isFinite(+e.price) ? Math.max(0, +e.price) : 0,
      detail_url:
        typeof e.detail_url === 'string' &&
        e.detail_url.startsWith('https://ticket.fany.lol/history/detail/')
          ? e.detail_url
          : '',
    }));
}

// ---- フィルタ状態 ----

const filters = {
  keyword:  '',
  venue:    '',
  dateFrom: '',
  dateTo:   '',
  showLost: false,  // 落選を表示するか
  showPast: false,  // 過去公演を表示するか
};

// ---- アプリ状態 ----

let appData = null; // { schema_version, scraped_at, entries[] }

// ---- ユーティリティ ----

function getToday() {
  const d = new Date();
  return d.getFullYear() + '-'
    + String(d.getMonth() + 1).padStart(2, '0') + '-'
    + String(d.getDate()).padStart(2, '0');
}

// ---- フィルタ適用 + 公演日昇順ソート ----

function applyFilters(entries) {
  const today = getToday();

  return entries
    .filter((e) => {
      // 落選フィルタ
      if (e.status === 'lost' && !filters.showLost) return false;

      // 過去公演フィルタ（performance_date が空の場合は表示）
      if (!filters.showPast && e.performance_date && e.performance_date < today) return false;

      // 公演日 from/to
      if (filters.dateFrom && e.performance_date < filters.dateFrom) return false;
      if (filters.dateTo   && e.performance_date > filters.dateTo)   return false;

      // 会場
      if (filters.venue && e.venue !== filters.venue) return false;

      // キーワード（スペース区切り AND）
      if (filters.keyword) {
        const target = (e.title + ' ' + e.venue + ' ' + e.seat_type).toLowerCase();
        const words = filters.keyword.toLowerCase().split(/\s+/).filter(Boolean);
        if (!words.every((w) => target.includes(w))) return false;
      }

      return true;
    })
    .sort((a, b) => {
      // 公演日昇順。日付不明は末尾
      if (!a.performance_date) return 1;
      if (!b.performance_date) return -1;
      return a.performance_date < b.performance_date ? -1 : a.performance_date > b.performance_date ? 1 : 0;
    });
}

// ---- DOM 生成 ----

function formatDate(dateStr) {
  if (!dateStr) return '';
  const [y, m, d] = dateStr.split('-');
  if (!y) return dateStr;
  const days = ['日', '月', '火', '水', '木', '金', '土'];
  const dow = new Date(+y, +m - 1, +d).getDay();
  return y + '/' + m + '/' + d + '(' + days[dow] + ')';
}

function formatPrice(price) {
  return price > 0 ? '¥' + price.toLocaleString() : '';
}

function createCard(entry) {
  const card = document.createElement('div');
  card.className = 'card status-' + entry.status;

  // ステータスバッジ（status_text が空なら非表示）
  const label = STATUS_LABEL[entry.status] || entry.status_text;
  if (label) {
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.style.background = STATUS_COLOR[entry.status] || '#7f8c8d';
    badge.textContent = String(label);
    card.appendChild(badge);
  }

  // 公演日 + 時刻
  const dateRow = document.createElement('div');
  dateRow.className = 'card-date';
  const dateSpan = document.createElement('span');
  dateSpan.className = 'card-date-main';
  dateSpan.textContent = String(formatDate(entry.performance_date));
  dateRow.appendChild(dateSpan);
  if (entry.start_time) {
    const timeSpan = document.createElement('span');
    timeSpan.className = 'card-time';
    timeSpan.textContent = String(
      (entry.open_time ? '開場 ' + entry.open_time + '  ' : '') + '開演 ' + entry.start_time
    );
    dateRow.appendChild(timeSpan);
  }
  card.appendChild(dateRow);

  // タイトル
  const title = document.createElement('div');
  title.className = 'card-title';
  title.textContent = String(entry.title);
  card.appendChild(title);

  // 会場
  const venue = document.createElement('div');
  venue.className = 'card-venue';
  venue.textContent = String(entry.venue);
  card.appendChild(venue);

  // 詳細情報行
  const meta = document.createElement('div');
  meta.className = 'card-meta';

  const parts = [];
  if (entry.seat_type) parts.push(entry.seat_type);
  if (entry.quantity > 0) parts.push(entry.quantity + '枚');
  if (entry.price > 0) parts.push(formatPrice(entry.price));

  const metaText = document.createElement('span');
  metaText.textContent = String(parts.join('  '));
  meta.appendChild(metaText);

  if (entry.detail_url) {
    const link = document.createElement('a');
    link.className = 'card-link';
    link.href = entry.detail_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = '詳細';
    meta.appendChild(link);
  }
  card.appendChild(meta);

  // 予約日時（小さく）
  if (entry.reserved_at) {
    const reserved = document.createElement('div');
    reserved.className = 'card-reserved';
    reserved.textContent = String('予約: ' + entry.reserved_at);
    card.appendChild(reserved);
  }

  return card;
}

// ---- 会場 <select> を再構築（優先会場を先頭に） ----

function venueOrder(venue) {
  const idx = PREFERRED_VENUES.findIndex((p) => venue.includes(p));
  return idx >= 0 ? idx : PREFERRED_VENUES.length;
}

function rebuildVenueOptions() {
  const select = document.getElementById('filter-venue');
  const prev = select.value;
  while (select.options.length > 1) select.remove(1);

  if (!appData) return;

  const venues = [...new Set(appData.entries.map((e) => e.venue).filter(Boolean))]
    .sort((a, b) => {
      const oa = venueOrder(a), ob = venueOrder(b);
      if (oa !== ob) return oa - ob;
      return a.localeCompare(b, 'ja');
    });

  for (const v of venues) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    select.appendChild(opt);
  }
  if (venues.includes(prev)) select.value = prev;
}

// ---- レンダリング ----

function render() {
  const container = document.getElementById('cards');
  const countEl   = document.getElementById('result-count');
  const emptyEl   = document.getElementById('empty-state');
  const scrapedEl = document.getElementById('scraped-at');

  while (container.firstChild) container.removeChild(container.firstChild);

  if (!appData || !appData.entries.length) {
    emptyEl.hidden = false;
    countEl.textContent = '';
    scrapedEl.textContent = '';
    return;
  }

  emptyEl.hidden = true;

  if (appData.scraped_at) {
    const d = new Date(appData.scraped_at);
    scrapedEl.textContent = 'データ取得: ' + d.toLocaleString('ja-JP');
  }

  const filtered = applyFilters(appData.entries);
  countEl.textContent = filtered.length + '件';

  for (const entry of filtered) {
    container.appendChild(createCard(entry));
  }
}

// ---- イベントリスナー ----

function setupFilters() {
  document.getElementById('filter-keyword').addEventListener('input', (e) => {
    filters.keyword = e.target.value;
    render();
  });

  document.getElementById('filter-venue').addEventListener('change', (e) => {
    filters.venue = e.target.value;
    render();
  });

  document.getElementById('filter-date-from').addEventListener('change', (e) => {
    filters.dateFrom = e.target.value;
    render();
  });

  document.getElementById('filter-date-to').addEventListener('change', (e) => {
    filters.dateTo = e.target.value;
    render();
  });

  document.getElementById('filter-show-lost').addEventListener('change', (e) => {
    filters.showLost = e.target.checked;
    render();
  });

  document.getElementById('filter-show-past').addEventListener('change', (e) => {
    filters.showPast = e.target.checked;
    render();
  });

  document.getElementById('btn-clear').addEventListener('click', () => {
    document.getElementById('filter-keyword').value = '';
    document.getElementById('filter-venue').value = '';
    document.getElementById('filter-date-from').value = '';
    document.getElementById('filter-date-to').value = '';
    document.getElementById('filter-show-lost').checked = false;
    document.getElementById('filter-show-past').checked = false;
    filters.keyword  = '';
    filters.venue    = '';
    filters.dateFrom = '';
    filters.dateTo   = '';
    filters.showLost = false;
    filters.showPast = false;
    render();
  });
}

// ---- postMessage 受信 ----

function setupMessageListener() {
  window.addEventListener('message', (event) => {
    if (event.origin !== FANY_ORIGIN) return;
    if (!event.data || event.data.type !== 'fanaby-history') return;

    const entries = validateEntries(event.data.payload);
    const data = {
      schema_version: 1,
      scraped_at: String(event.data.scrapedAt || ''),
      entries,
    };

    appData = data;
    saveData(data);
    rebuildVenueOptions();
    render();

    const banner = document.getElementById('received-banner');
    if (banner) {
      banner.textContent = entries.length + '件のデータを受信しました。';
      banner.hidden = false;
      setTimeout(() => { banner.hidden = true; }, 4000);
    }
  });
}

// ---- 初期化 ----

document.addEventListener('DOMContentLoaded', () => {
  appData = loadData();
  setupFilters();
  setupMessageListener();
  rebuildVenueOptions();
  render();
});

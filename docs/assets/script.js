const YOSHIMOTO_VENUES = [
  'ルミネtheよしもと',
  '渋谷よしもと漫才劇場',
  '神保町よしもと漫才劇場',
  'YOSHIMOTO ROPPONGI THEATER',
  'よしもと幕張イオンモール劇場',
  '大宮ラクーンよしもと劇場',
  'よしもと漫才劇場',
  '森ノ宮よしもと漫才劇場',
  'よしもと道頓堀シアター',
  'よしもと福岡 大和証券劇場',
];

// ---- タブ切り替え ----
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector('[data-panel="' + btn.dataset.tab + '"]').classList.add('active');
    resetFilters();
    buildVenueOptions();
    applyFilters();
  });
});

// ---- ライトボックス ----
function openLightbox(src) {
  document.getElementById('lightboxImg').src = src;
  document.getElementById('lightbox').classList.add('open');
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('open');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

// ---- フィルター ----
function activePanel() {
  return document.querySelector('.tab-panel.active');
}

function allCardsInPanel(panel) {
  return Array.from(panel.querySelectorAll('.event-card'));
}

function buildVenueOptions() {
  const panel = activePanel();
  const present = new Set();
  allCardsInPanel(panel).forEach(c => { if (c.dataset.venue) present.add(c.dataset.venue); });

  const sel = document.getElementById('filterVenue');
  const current = sel.value;
  sel.innerHTML = '<option value="">すべて</option>';

  function makeOpt(v) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    if (v === current) opt.selected = true;
    return opt;
  }

  const yoshimotoPresent = YOSHIMOTO_VENUES.filter(v => present.has(v));
  if (yoshimotoPresent.length) {
    const grp = document.createElement('optgroup');
    grp.label = 'よしもと';
    yoshimotoPresent.forEach(v => grp.appendChild(makeOpt(v)));
    sel.appendChild(grp);
  }

  const others = [...present].filter(v => !YOSHIMOTO_VENUES.includes(v)).sort();
  if (others.length) {
    const grp = document.createElement('optgroup');
    grp.label = 'その他劇場';
    others.forEach(v => grp.appendChild(makeOpt(v)));
    sel.appendChild(grp);
  }
}

function applyFilters() {
  const venue  = document.getElementById('filterVenue').value;
  const from   = document.getElementById('filterDateFrom').value;
  const to     = document.getElementById('filterDateTo').value;
  const status = document.getElementById('filterStatus').value;
  const panel  = activePanel();
  const cards  = allCardsInPanel(panel);
  let visible = 0;
  cards.forEach(c => {
    const cardStatus = c.dataset.status || '';
    const statusOk = !status
      || (status === 'none' ? cardStatus === '' : cardStatus === status);
    const ok = (!venue || c.dataset.venue === venue)
            && (!from  || c.dataset.date >= from)
            && (!to    || c.dataset.date <= to)
            && statusOk;
    c.classList.toggle('hidden', !ok);
    if (ok) visible++;
  });
  const isFiltered = venue || from || to || status;
  document.getElementById('filterCount').textContent =
    isFiltered ? `${visible} 件表示中` : '';
  panel.querySelectorAll('.section-title, .section-past summary').forEach(el => {
    const section = el.closest('.section, .section-past');
    if (!section) return;
    const countEl = el.querySelector('.section-count');
    if (!countEl) return;
    const shown = section.querySelectorAll('.event-card:not(.hidden)').length;
    countEl.textContent = isFiltered
      ? `${shown}/${countEl.dataset.total}`
      : countEl.dataset.total;
  });
}

function resetFilters() {
  document.getElementById('filterVenue').value = '';
  document.getElementById('filterDateFrom').value = '';
  document.getElementById('filterDateTo').value = '';
  document.getElementById('filterStatus').value = '';
}

document.getElementById('filterVenue').addEventListener('change', applyFilters);
document.getElementById('filterDateFrom').addEventListener('change', applyFilters);
document.getElementById('filterDateTo').addEventListener('change', applyFilters);
document.getElementById('filterStatus').addEventListener('change', applyFilters);
document.getElementById('filterReset').addEventListener('click', () => {
  resetFilters();
  applyFilters();
});

buildVenueOptions();

// ---- ステータス管理 ----
const STATUSES = {
  want:            { label: '行きたい',     color: '#3498db' },
  lottery_applied: { label: '先行申込済み', color: '#e67e22' },
  lottery_lost:    { label: '落選',         color: '#95a5a6' },
  purchased:       { label: '購入済み',     color: '#27ae60' },
  attended:        { label: '行った',       color: '#2c3e50' },
};

const StatusStorage = {
  _KEY: 'fanaby_statuses',

  _load() {
    try {
      const raw = localStorage.getItem(this._KEY);
      if (!raw) return { schema_version: 1, statuses: {} };
      return JSON.parse(raw);
    } catch {
      return { schema_version: 1, statuses: {} };
    }
  },

  _save(data) {
    data.updated_at = new Date().toISOString();
    localStorage.setItem(this._KEY, JSON.stringify(data));
  },

  getAll() {
    return this._load().statuses;
  },

  get(eventId) {
    return this._load().statuses[eventId] || null;
  },

  set(eventId, status) {
    const data = this._load();
    const now = new Date().toISOString();
    const existing = data.statuses[eventId] || { history: [], memo: '' };
    existing.status = status;
    existing.updated_at = now;
    existing.history.push({ status, at: now });
    data.statuses[eventId] = existing;
    this._save(data);
  },

  remove(eventId) {
    const data = this._load();
    delete data.statuses[eventId];
    this._save(data);
  },

  export() {
    return localStorage.getItem(this._KEY) || '{}';
  },

  import(json) {
    try {
      const parsed = JSON.parse(json);
      if (!parsed.statuses) throw new Error('invalid');
      localStorage.setItem(this._KEY, json);
      return true;
    } catch {
      return false;
    }
  },
};

function applyStatusToCard(card, status) {
  card.dataset.status = status || '';
  const wrap = card.querySelector('.status-wrap');
  const sel  = card.querySelector('.status-select');
  if (wrap) wrap.dataset.status = status || '';
  if (sel)  sel.value = status || '';
}

function initStatusUI() {
  const all = StatusStorage.getAll();
  document.querySelectorAll('.event-card').forEach(card => {
    const id = card.dataset.eventId;
    if (!id) return;
    const rec = all[id];
    applyStatusToCard(card, rec ? rec.status : '');
  });
}

document.addEventListener('change', e => {
  const sel = e.target.closest('.status-select');
  if (!sel) return;
  const eventId   = sel.dataset.eventId;
  const newStatus = sel.value;
  if (!eventId) return;
  if (newStatus) {
    StatusStorage.set(eventId, newStatus);
  } else {
    StatusStorage.remove(eventId);
  }
  const card = sel.closest('.event-card');
  if (card) applyStatusToCard(card, newStatus);
  applyFilters();
});

initStatusUI();

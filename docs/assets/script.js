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

// ---- タブ切り替え（単一DOM + talentフィルタ） ----
let currentTalent = '';

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentTalent = btn.dataset.tab === 'all' ? '' : btn.dataset.tab;
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
function allCards() {
  return Array.from(document.querySelectorAll('.event-card'));
}

function buildVenueOptions() {
  const present = new Set();
  allCards().forEach(c => {
    if (currentTalent && c.dataset.talent !== currentTalent) return;
    if (c.dataset.venue) present.add(c.dataset.venue);
  });

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
  const venue    = document.getElementById('filterVenue').value;
  const from     = document.getElementById('filterDateFrom').value;
  const to       = document.getElementById('filterDateTo').value;
  const status   = document.getElementById('filterViewingStatus').value;
  const keyword  = document.getElementById('filterKeyword').value.trim().toLowerCase();
  const keywords = keyword ? keyword.split(/\s+/) : [];
  const cards    = allCards();
  let visible    = 0;

  cards.forEach(c => {
    const cardStatus = c.dataset.viewingStatus || '';
    const statusOk = !status
      || (status === 'none' ? cardStatus === '' : cardStatus === status);
    const keywordOk = keywords.length === 0 || (() => {
      const target = ((c.dataset.title || '') + ' ' + (c.dataset.members || '')).toLowerCase();
      return keywords.every(kw => target.includes(kw));
    })();
    const ok = (!currentTalent || c.dataset.talent === currentTalent)
            && (!venue  || c.dataset.venue === venue)
            && (!from   || c.dataset.date  >= from)
            && (!to     || c.dataset.date  <= to)
            && statusOk
            && keywordOk;
    c.classList.toggle('hidden', !ok);
    if (ok) visible++;
  });

  const isFiltered = currentTalent || venue || from || to || status || keyword;
  document.getElementById('filterCount').textContent =
    isFiltered ? `${visible} 件表示中` : '';

  // セクション見出しの件数を更新
  document.querySelectorAll('.section, .section-past').forEach(section => {
    const countEl = section.querySelector('.section-count');
    if (!countEl) return;
    countEl.textContent = section.querySelectorAll('.event-card:not(.hidden)').length;
  });
}

function resetFilters() {
  document.getElementById('filterVenue').value = '';
  document.getElementById('filterDateFrom').value = '';
  document.getElementById('filterDateTo').value = '';
  document.getElementById('filterViewingStatus').value = '';
  document.getElementById('filterKeyword').value = '';
}

document.getElementById('filterKeyword').addEventListener('input', applyFilters);
document.getElementById('filterVenue').addEventListener('change', applyFilters);
document.getElementById('filterDateFrom').addEventListener('change', applyFilters);
document.getElementById('filterDateTo').addEventListener('change', applyFilters);
document.getElementById('filterViewingStatus').addEventListener('change', applyFilters);
document.getElementById('filterReset').addEventListener('click', () => {
  resetFilters();
  applyFilters();
});

buildVenueOptions();

// ---- 観覧ステータス ----
const VIEWING_STATUSES = {
  want:            { label: '行きたい',     color: '#3498db' },
  lottery_applied: { label: '先行申込済み', color: '#e67e22' },
  lottery_lost:    { label: '落選',         color: '#95a5a6' },
  purchased:       { label: '購入済み',     color: '#27ae60' },
  attended:        { label: '行った',       color: '#2c3e50' },
};

const VALID_VIEWING_STATUSES = new Set(Object.keys(VIEWING_STATUSES));
const EVENT_ID_RE = /^[0-9a-f]{8}$/;

const ViewingStorage = {
  _KEY: 'fanaby_viewing_statuses',
  _PENDING_KEY: 'fanaby_pending_sync',
  _API: '/api/viewing-statuses',
  _cache: null,

  // --- localStorage ヘルパー ---
  _loadLocal() {
    try {
      const raw = localStorage.getItem(this._KEY);
      if (!raw) return { schema_version: 1, statuses: {} };
      return JSON.parse(raw);
    } catch {
      return { schema_version: 1, statuses: {} };
    }
  },

  _saveLocal(data) {
    data.updated_at = new Date().toISOString();
    localStorage.setItem(this._KEY, JSON.stringify(data));
    this._cache = data;
  },

  // APIレスポンスのスキーマを検証し、安全なデータのみ返す
  _validateRemote(data) {
    if (!data || typeof data !== 'object') return null;
    if (typeof data.statuses !== 'object' || data.statuses === null || Array.isArray(data.statuses)) return null;
    const sanitized = {};
    for (const [id, entry] of Object.entries(data.statuses)) {
      if (!EVENT_ID_RE.test(id)) continue;
      if (!entry || !VALID_VIEWING_STATUSES.has(entry.status)) continue;
      sanitized[id] = {
        status:     entry.status,
        updated_at: typeof entry.updated_at === 'string' ? entry.updated_at : '',
        memo:       typeof entry.memo === 'string' ? entry.memo : '',
        history:    Array.isArray(entry.history) ? entry.history.filter(
          h => h && VALID_VIEWING_STATUSES.has(h.status) && typeof h.at === 'string'
        ) : [],
      };
    }
    return { schema_version: 1, statuses: sanitized };
  },

  // --- リモート API ヘルパー ---
  async _fetchRemote() {
    try {
      const res = await fetch(this._API);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await res.json();
      return this._validateRemote(raw);
    } catch (e) {
      console.warn('ViewingStorage: remote fetch failed, using localStorage', e);
      return null;
    }
  },

  async _patchRemote(eventId, payload) {
    try {
      const res = await fetch(`${this._API}/${eventId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      localStorage.removeItem(this._PENDING_KEY);
    } catch (e) {
      console.warn('ViewingStorage: remote patch failed', e);
      localStorage.setItem(this._PENDING_KEY, 'true');
    }
  },

  async _deleteRemote(eventId) {
    try {
      const res = await fetch(`${this._API}/${eventId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      localStorage.removeItem(this._PENDING_KEY);
    } catch (e) {
      console.warn('ViewingStorage: remote delete failed', e);
      localStorage.setItem(this._PENDING_KEY, 'true');
    }
  },

  async _putRemote(data) {
    try {
      const res = await fetch(this._API, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      localStorage.removeItem(this._PENDING_KEY);
    } catch (e) {
      console.warn('ViewingStorage: remote put failed', e);
      localStorage.setItem(this._PENDING_KEY, 'true');
    }
  },

  // --- マージ: イベントごとに updated_at が新しい方を採用 ---
  _merge(local, remote) {
    const merged = { ...remote.statuses };
    for (const [id, localEntry] of Object.entries(local.statuses)) {
      const remoteEntry = merged[id];
      if (!remoteEntry || (localEntry.updated_at || '') > (remoteEntry.updated_at || '')) {
        merged[id] = localEntry;
      }
    }
    return { schema_version: 1, statuses: merged };
  },

  // --- 初期化: APIから取得し localStorage と同期 ---
  async init() {
    const local = this._loadLocal();
    this._cache = local;

    const remote = await this._fetchRemote();
    const hasLocalData = Object.keys(local.statuses).length > 0;
    const hasRemoteData = remote && Object.keys(remote.statuses || {}).length > 0;

    if (hasRemoteData) {
      if (hasLocalData) {
        // マージ: イベントごとに updated_at が新しい方を採用し、リモートに反映
        const merged = this._merge(local, remote);
        this._saveLocal(merged);
        await this._putRemote(merged);
      } else {
        // 新端末: リモートをローカルに複製
        this._saveLocal(remote);
      }
    } else if (hasLocalData) {
      // 初回移行: ローカルデータをリモートにアップロード
      await this._putRemote(local);
    }

    return this._cache.statuses;
  },

  // --- 公開 API（既存の呼び出し元と互換） ---
  getAll() {
    return (this._cache || this._loadLocal()).statuses;
  },

  get(eventId) {
    return this.getAll()[eventId] || null;
  },

  set(eventId, status) {
    const data = this._cache || this._loadLocal();
    const now = new Date().toISOString();
    const existing = data.statuses[eventId] || { history: [], memo: '' };
    existing.status = status;
    existing.updated_at = now;
    existing.history = existing.history || [];
    existing.history.push({ status, at: now });
    data.statuses[eventId] = existing;
    this._saveLocal(data);
    this._patchRemote(eventId, { status, memo: existing.memo });
  },

  remove(eventId) {
    const data = this._cache || this._loadLocal();
    delete data.statuses[eventId];
    this._saveLocal(data);
    this._deleteRemote(eventId);
  },

  export() {
    return localStorage.getItem(this._KEY) || '{}';
  },

  import(json) {
    try {
      const parsed = JSON.parse(json);
      if (!parsed.statuses) throw new Error('invalid');
      this._saveLocal(parsed);
      this._putRemote(parsed);
      return true;
    } catch {
      return false;
    }
  },

  getMemo(eventId) {
    const rec = this.get(eventId);
    return rec ? (rec.memo || '') : '';
  },

  setMemo(eventId, text) {
    const data = this._cache || this._loadLocal();
    const existing = data.statuses[eventId]
      || { history: [], status: '', memo: '' };
    existing.memo = text;
    existing.updated_at = new Date().toISOString();
    data.statuses[eventId] = existing;
    this._saveLocal(data);
    this._patchRemote(eventId, { status: existing.status, memo: text });
  },
};

function applyStatusToCard(card, status) {
  // ホワイトリストにない値はクリア（不正データのDOM反映を防止）
  const safeStatus = VALID_VIEWING_STATUSES.has(status) ? status : '';
  card.dataset.viewingStatus = safeStatus;
  const wrap = card.querySelector('.viewing-wrap');
  const sel  = card.querySelector('.viewing-select');
  if (wrap) wrap.dataset.viewingStatus = safeStatus;
  if (sel)  sel.value = safeStatus;
}

function initStatusUI() {
  const all = ViewingStorage.getAll();
  document.querySelectorAll('.event-card').forEach(card => {
    const id = card.dataset.eventId;
    if (!id) return;
    const rec = all[id];
    applyStatusToCard(card, rec ? rec.status : '');
  });
}

document.addEventListener('change', e => {
  const sel = e.target.closest('.viewing-select');
  if (!sel) return;
  const eventId   = sel.dataset.eventId;
  const newStatus = sel.value;
  if (!eventId) return;
  if (newStatus) {
    ViewingStorage.set(eventId, newStatus);
  } else {
    ViewingStorage.remove(eventId);
  }
  // 同一イベントIDを持つ全タブのカードを一括更新
  document.querySelectorAll(`.event-card[data-event-id="${eventId}"]`).forEach(card => {
    applyStatusToCard(card, newStatus);
  });
  applyFilters();
});

async function initUserUI() {
  try {
    const res = await fetch('/api/me');
    if (!res.ok) return;
    const { email, initial } = await res.json();
    const el = document.getElementById('userAvatar');
    if (!el) return;
    el.textContent = initial; // textContent のみ（XSS防止）
    el.title = email;
    el.style.display = '';
  } catch { /* オフライン・Access未設定時は表示しない */ }
}

function initMemoUI() {
  document.querySelectorAll('.memo-input').forEach(textarea => {
    const id = textarea.dataset.eventId;
    if (!id) return;
    textarea.value = ViewingStorage.getMemo(id);
    let timer;
    textarea.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        ViewingStorage.setMemo(id, textarea.value);
      }, 1000);
    });
  });
}

(async () => {
  // 初期化完了まで操作を無効化（APIフェッチ中の競合防止）
  document.querySelectorAll('.viewing-select').forEach(sel => { sel.disabled = true; });
  await Promise.all([ViewingStorage.init(), initUserUI()]);
  initStatusUI();
  initMemoUI();
  document.querySelectorAll('.viewing-select').forEach(sel => { sel.disabled = false; });
})();

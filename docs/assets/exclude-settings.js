'use strict';

const EK_LS_KEY = 'fanaby_exclude_keywords';

// LocalStorage と /api/user-exclude-keywords を透過同期するストレージ
const ExcludeKeywordStorage = {
  _cache: null,

  _defaults() {
    return { schema_version: 1, keywords: [], updated_at: null };
  },

  _loadLocal() {
    try {
      const raw = localStorage.getItem(EK_LS_KEY);
      if (!raw) return this._defaults();
      const d = JSON.parse(raw);
      if (!Array.isArray(d.keywords)) return this._defaults();
      return d;
    } catch {
      return this._defaults();
    }
  },

  _saveLocal(data) {
    try { localStorage.setItem(EK_LS_KEY, JSON.stringify(data)); } catch {}
  },

  async _fetchRemote() {
    const res = await fetch('/api/user-exclude-keywords');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    if (!Array.isArray(d.keywords)) throw new Error('invalid remote data');
    return d;
  },

  async _putRemote(data) {
    const res = await fetch('/api/user-exclude-keywords', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keywords: data.keywords }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
  },

  async init() {
    const local = this._loadLocal();
    try {
      const remote = await this._fetchRemote();
      const useRemote = !local.updated_at ||
        (remote.updated_at && remote.updated_at > local.updated_at);
      this._cache = useRemote ? remote : local;
      this._saveLocal(this._cache);
    } catch {
      this._cache = local;
    }
    return this._cache;
  },

  getKeywords() {
    return (this._cache ?? this._loadLocal()).keywords;
  },

  async setKeywords(keywords) {
    const normalized = [...new Set(keywords.map(k => k.trim()).filter(k => k.length > 0))];
    const data = {
      schema_version: 1,
      keywords: normalized,
      updated_at: new Date().toISOString(),
    };
    this._cache = data;
    this._saveLocal(data);
    await this._putRemote(data);
  },

  async addKeyword(kw) {
    const keywords = this.getKeywords();
    if (!keywords.includes(kw)) {
      await this.setKeywords([...keywords, kw]);
    }
  },

  async removeKeyword(kw) {
    await this.setKeywords(this.getKeywords().filter(k => k !== kw));
  },
};

const SE_LS_KEY = 'fanaby_standing_exclude';
const STANDING_VENUES = [
  '渋谷よしもと漫才劇場',
  '神保町よしもと漫才劇場',
  'ルミネtheよしもと',
  'YOSHIMOTO ROPPONGI THEATER',
  '大宮ラクーンよしもと劇場',
  'よしもと幕張イオンモール劇場',
  'よしもと漫才劇場',
  '森ノ宮よしもと漫才劇場',
  'よしもと福岡 大和証券劇場',
  'よしもと道頓堀シアター',
  '沼津ラクーンよしもと劇場',
  'なんばグランド花月',
];

// LocalStorage と /api/user-standing-exclude を透過同期するストレージ
const StandingExcludeStorage = {
  _cache: null,

  _defaults() {
    return { schema_version: 1, mode: 'all', venues: [], updated_at: null };
  },

  _loadLocal() {
    try {
      const raw = localStorage.getItem(SE_LS_KEY);
      if (!raw) return this._defaults();
      const d = JSON.parse(raw);
      if (!d.mode) return this._defaults();
      return d;
    } catch {
      return this._defaults();
    }
  },

  _saveLocal(data) {
    try { localStorage.setItem(SE_LS_KEY, JSON.stringify(data)); } catch {}
  },

  async _fetchRemote() {
    const res = await fetch('/api/user-standing-exclude');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    if (!d.mode) throw new Error('invalid remote data');
    return d;
  },

  async _putRemote(data) {
    const res = await fetch('/api/user-standing-exclude', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: data.mode, venues: data.venues }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
  },

  async init() {
    const local = this._loadLocal();
    try {
      const remote = await this._fetchRemote();
      const useRemote = !local.updated_at ||
        (remote.updated_at && remote.updated_at > local.updated_at);
      this._cache = useRemote ? remote : local;
      this._saveLocal(this._cache);
    } catch {
      this._cache = local;
    }
    return this._cache;
  },

  get() {
    return this._cache ?? this._loadLocal();
  },

  async set(mode, venues) {
    const data = {
      schema_version: 1,
      mode,
      venues: mode === 'venues' ? [...new Set(venues)] : [],
      updated_at: new Date().toISOString(),
    };
    this._cache = data;
    this._saveLocal(data);
    await this._putRemote(data);
  },
};

// ======= 描画 =======

function renderStandingExclude() {
  const container = document.getElementById('standingExcludeControls');
  container.innerHTML = '';

  const current = StandingExcludeStorage.get();

  const modes = [
    { value: 'off', label: '除外しない' },
    { value: 'all', label: '一括除外する' },
    { value: 'venues', label: '指定劇場を除外する' },
  ];

  modes.forEach(m => {
    const row = document.createElement('label');
    row.className = 'standing-mode-row';

    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'standingMode';
    radio.value = m.value;
    radio.checked = current.mode === m.value;
    radio.onchange = () => handleStandingModeChange(m.value);
    row.appendChild(radio);

    const text = document.createTextNode(m.label);
    row.appendChild(text);

    container.appendChild(row);
  });

  if (current.mode === 'venues') {
    const venueList = document.createElement('div');
    venueList.className = 'standing-venue-list';

    STANDING_VENUES.forEach(venue => {
      const row = document.createElement('label');
      row.className = 'standing-venue-row';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = current.venues.includes(venue);
      checkbox.onchange = () => handleStandingVenueToggle(venue, checkbox.checked);
      row.appendChild(checkbox);

      row.appendChild(document.createTextNode(venue));

      venueList.appendChild(row);
    });

    container.appendChild(venueList);
  }
}

function renderExcludeKeywords() {
  const container = document.getElementById('excludeKeywordList');
  container.innerHTML = '';

  const keywords = ExcludeKeywordStorage.getKeywords();

  if (keywords.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'empty-msg';
    msg.textContent = '除外キーワードはありません。';
    container.appendChild(msg);
    return;
  }

  keywords.forEach(kw => {
    const row = document.createElement('div');
    row.className = 'keyword-row';

    const textWrap = document.createElement('div');
    textWrap.className = 'keyword-text';
    textWrap.textContent = kw;
    row.appendChild(textWrap);

    const btn = document.createElement('button');
    btn.className = 'btn-unfollow';
    btn.textContent = '削除';
    btn.onclick = () => handleRemoveKeyword(kw, btn);
    row.appendChild(btn);

    container.appendChild(row);
  });
}

function render() {
  renderStandingExclude();
  renderExcludeKeywords();
}

// ======= イベントハンドラ =======

async function handleStandingModeChange(mode) {
  const current = StandingExcludeStorage.get();
  try {
    await StandingExcludeStorage.set(mode, current.venues);
    renderStandingExclude();
  } catch (e) {
    showMsg('standingMsg', 'error', '設定の保存に失敗しました: ' + e.message);
    renderStandingExclude();
  }
}

async function handleStandingVenueToggle(venue, checked) {
  const current = StandingExcludeStorage.get();
  const venues = checked
    ? [...current.venues, venue]
    : current.venues.filter(v => v !== venue);
  try {
    await StandingExcludeStorage.set('venues', venues);
  } catch (e) {
    showMsg('standingMsg', 'error', '設定の保存に失敗しました: ' + e.message);
    renderStandingExclude();
  }
}

async function handleAddKeyword() {
  const input = document.getElementById('addKeyword');
  const btn = document.getElementById('addKeywordBtn');
  const kw = input.value.trim();
  if (!kw) {
    showMsg('keywordMsg', 'error', 'キーワードを入力してください。');
    return;
  }

  btn.disabled = true;
  try {
    await ExcludeKeywordStorage.addKeyword(kw);
    input.value = '';
    render();
  } catch (e) {
    showMsg('keywordMsg', 'error', '追加に失敗しました: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function handleRemoveKeyword(kw, btn) {
  btn.disabled = true;
  try {
    await ExcludeKeywordStorage.removeKeyword(kw);
    render();
  } catch (e) {
    btn.disabled = false;
    showMsg('keywordMsg', 'error', '削除に失敗しました: ' + e.message);
  }
}

function showMsg(id, type, text) {
  const el = document.getElementById(id);
  el.className = 'status-msg ' + type;
  el.textContent = text;
}

// ======= ユーザーアバター =======

async function initUserUI() {
  try {
    const res = await fetch('/api/me');
    if (!res.ok) return;
    const { email, initial } = await res.json();
    const avatar = document.getElementById('userAvatar');
    if (avatar && initial) {
      avatar.textContent = initial;
      avatar.title = email;
      avatar.style.display = 'flex';
    }
  } catch {}
}

// ======= 初期化 =======

(async () => {
  await Promise.all([
    initUserUI(),
    ExcludeKeywordStorage.init(),
    StandingExcludeStorage.init(),
  ]);

  render();
})();

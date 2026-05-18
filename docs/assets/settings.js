'use strict';

const LS_KEY = 'fanaby_follow_talents';

// LocalStorage と /api/user-talents を透過同期するストレージ
const FollowStorage = {
  _cache: null,

  _defaults() {
    return { schema_version: 1, talent_ids: [], updated_at: null };
  },

  _loadLocal() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) return this._defaults();
      const d = JSON.parse(raw);
      if (!Array.isArray(d.talent_ids)) return this._defaults();
      return d;
    } catch {
      return this._defaults();
    }
  },

  _saveLocal(data) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(data)); } catch {}
  },

  async _fetchRemote() {
    const res = await fetch('/api/user-talents');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    if (!Array.isArray(d.talent_ids)) throw new Error('invalid remote data');
    return d;
  },

  async _putRemote(data) {
    const res = await fetch('/api/user-talents', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ talent_ids: data.talent_ids }),
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
      // updated_at が新しい方を採用
      const useRemote = !local.updated_at ||
        (remote.updated_at && remote.updated_at > local.updated_at);
      this._cache = useRemote ? remote : local;
      this._saveLocal(this._cache);
    } catch {
      this._cache = local;
    }
    return this._cache;
  },

  getIds() {
    return (this._cache ?? this._loadLocal()).talent_ids;
  },

  async setIds(ids) {
    const unique = [...new Set(ids.map(String))];
    const data = {
      schema_version: 1,
      talent_ids: unique,
      updated_at: new Date().toISOString(),
    };
    this._cache = data;
    this._saveLocal(data);
    await this._putRemote(data);
  },

  async addId(id) {
    const ids = this.getIds();
    if (!ids.includes(String(id))) {
      await this.setIds([...ids, String(id)]);
    }
  },

  async removeId(id) {
    await this.setIds(this.getIds().filter(x => x !== String(id)));
  },
};

// グローバル芸人マスタ
let masterTalents = [];

// ======= 描画 =======

function makePlaceholder(name) {
  const div = document.createElement('div');
  div.className = 'talent-avatar-placeholder';
  div.textContent = name ? name.charAt(0) : '?';
  return div;
}

function makeAvatar(talent) {
  if (talent.image_url) {
    const img = document.createElement('img');
    img.className = 'talent-avatar';
    img.src = talent.image_url;
    img.alt = '';
    img.onerror = function() {
      this.replaceWith(makePlaceholder(talent.name));
    };
    return img;
  }
  return makePlaceholder(talent.name);
}

function renderFollowedList(followIds) {
  const container = document.getElementById('followedList');
  container.innerHTML = '';

  const followed = masterTalents.filter(t => followIds.includes(t.id));

  if (followed.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'empty-msg';
    msg.textContent = 'フォロー中の芸人はいません。下の一覧から追加してください。';
    container.appendChild(msg);
    return;
  }

  followed.forEach(talent => {
    const row = document.createElement('div');
    row.className = 'talent-row';

    row.appendChild(makeAvatar(talent));

    const nameWrap = document.createElement('div');
    nameWrap.className = 'talent-name';
    const nameText = document.createTextNode(talent.name || `ID: ${talent.id}`);
    nameWrap.appendChild(nameText);
    if (!talent.name) {
      const pending = document.createElement('span');
      pending.className = 'talent-name-pending';
      pending.textContent = ' (名前は次回更新で反映)';
      nameWrap.appendChild(pending);
    }
    row.appendChild(nameWrap);

    const btn = document.createElement('button');
    btn.className = 'btn-unfollow';
    btn.textContent = '解除';
    btn.dataset.id = talent.id;
    btn.onclick = () => handleUnfollow(talent.id, btn);
    row.appendChild(btn);

    container.appendChild(row);
  });
}

function renderMasterList(followIds) {
  const container = document.getElementById('masterList');
  container.innerHTML = '';

  const notFollowed = masterTalents.filter(t => !followIds.includes(t.id));

  if (masterTalents.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'empty-msg';
    msg.textContent = 'まだ芸人が登録されていません。下のフォームから追加してください。';
    container.appendChild(msg);
    return;
  }

  if (notFollowed.length === 0) {
    const msg = document.createElement('p');
    msg.className = 'empty-msg';
    msg.textContent = '登録されている全芸人をフォロー中です。';
    container.appendChild(msg);
    return;
  }

  notFollowed.forEach(talent => {
    const row = document.createElement('div');
    row.className = 'talent-row';

    row.appendChild(makeAvatar(talent));

    const nameWrap = document.createElement('div');
    nameWrap.className = 'talent-name';
    const nameText = document.createTextNode(talent.name || `ID: ${talent.id}`);
    nameWrap.appendChild(nameText);
    if (!talent.name) {
      const pending = document.createElement('span');
      pending.className = 'talent-name-pending';
      pending.textContent = ' (名前は次回更新で反映)';
      nameWrap.appendChild(pending);
    }
    row.appendChild(nameWrap);

    const btn = document.createElement('button');
    btn.className = 'btn-follow';
    btn.textContent = '追加';
    btn.dataset.id = talent.id;
    btn.onclick = () => handleFollow(talent.id, btn);
    row.appendChild(btn);

    container.appendChild(row);
  });
}

function render() {
  const followIds = FollowStorage.getIds();
  renderFollowedList(followIds);
  renderMasterList(followIds);
}

// ======= イベントハンドラ =======

async function handleFollow(talentId, btn) {
  btn.disabled = true;
  try {
    await FollowStorage.addId(talentId);
    render();
  } catch (e) {
    btn.disabled = false;
    showMsg('addMsg', 'error', 'フォローの追加に失敗しました: ' + e.message);
  }
}

async function handleUnfollow(talentId, btn) {
  btn.disabled = true;
  try {
    await FollowStorage.removeId(talentId);
    render();
  } catch (e) {
    btn.disabled = false;
    showMsg('addMsg', 'error', 'フォロー解除に失敗しました: ' + e.message);
  }
}

async function handleAddToMaster() {
  const input = document.getElementById('addUrl');
  const btn = document.getElementById('addBtn');
  const url = input.value.trim();
  if (!url) {
    showMsg('addMsg', 'error', 'URL を入力してください。');
    return;
  }

  btn.disabled = true;
  showMsg('addMsg', 'info', '登録中...');

  try {
    const res = await fetch('/api/talents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 409) {
        // 既にマスタに存在 → フォローだけ追加
        const existingId = data.id;
        await FollowStorage.addId(existingId);
        const existing = masterTalents.find(t => t.id === existingId);
        const name = existing?.name || existingId;
        showMsg('addMsg', 'success', `${name} は既に登録済みです。フォローに追加しました。`);
        input.value = '';
        render();
        return;
      }
      throw new Error(data.error || `HTTP ${res.status}`);
    }

    // マスタに追加成功 → masterTalents を更新 → フォローも追加
    masterTalents.push(data.talent);
    await FollowStorage.addId(data.talent.id);

    const displayName = data.talent.name || `ID: ${data.talent.id}`;
    showMsg('addMsg', 'success', `${displayName} を登録しました。芸人名と画像は次回の定期更新で反映されます。`);
    input.value = '';
    render();
  } catch (e) {
    showMsg('addMsg', 'error', '登録に失敗しました: ' + e.message);
  } finally {
    btn.disabled = false;
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
    FollowStorage.init(),
  ]);

  try {
    const res = await fetch('/api/talents');
    if (res.ok) {
      const data = await res.json();
      masterTalents = Array.isArray(data.talents) ? data.talents : [];
    }
  } catch {}

  render();
})();

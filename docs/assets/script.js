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
  const venue = document.getElementById('filterVenue').value;
  const from  = document.getElementById('filterDateFrom').value;
  const to    = document.getElementById('filterDateTo').value;
  const panel = activePanel();
  const cards = allCardsInPanel(panel);
  let visible = 0;
  cards.forEach(c => {
    const ok = (!venue || c.dataset.venue === venue)
            && (!from  || c.dataset.date >= from)
            && (!to    || c.dataset.date <= to);
    c.classList.toggle('hidden', !ok);
    if (ok) visible++;
  });
  document.getElementById('filterCount').textContent =
    (venue || from || to) ? `${visible} 件表示中` : '';
  panel.querySelectorAll('.section-title, .section-past summary').forEach(el => {
    const section = el.closest('.section, .section-past');
    if (!section) return;
    const countEl = el.querySelector('.section-count');
    if (!countEl) return;
    const shown = section.querySelectorAll('.event-card:not(.hidden)').length;
    const isFiltered = venue || from || to;
    countEl.textContent = isFiltered
      ? `${shown}/${countEl.dataset.total}`
      : countEl.dataset.total;
  });
}

function resetFilters() {
  document.getElementById('filterVenue').value = '';
  document.getElementById('filterDateFrom').value = '';
  document.getElementById('filterDateTo').value = '';
}

document.getElementById('filterVenue').addEventListener('change', applyFilters);
document.getElementById('filterDateFrom').addEventListener('change', applyFilters);
document.getElementById('filterDateTo').addEventListener('change', applyFilters);
document.getElementById('filterReset').addEventListener('click', () => {
  resetFilters();
  applyFilters();
});

buildVenueOptions();

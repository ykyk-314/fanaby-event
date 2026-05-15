/* FANY 履歴コレクター
 * ticket.fany.lol 上で実行する（ブックマークレット経由またはスクリプト注入）
 * same-origin fetch で全ページを取得し、postMessage でビューワーへ送信する
 */
(async function fanaby_collect() {
  if (location.hostname !== 'ticket.fany.lol') {
    alert('ticket.fany.lol で実行してください。');
    return;
  }

  const VIEWER = 'https://mypage-viewer.pages.dev';
  const MAX_PAGES = 19;
  const DELAY_MS = 400;

  const vw = window.open(VIEWER, '_mypage_viewer');
  const entries = [];
  const origTitle = document.title;

  function parseDoc(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const result = [];

    const mainRows = doc.querySelectorAll('tr.g-table_borderless');
    for (const mainRow of mainRows) {
      const q = (label) => mainRow.querySelector('td[data-label="' + label + '"]');

      const titleTd  = q('イベント名');
      const orderTd  = q('申込番号');
      const reservedTd = q('予約日時');
      if (!titleTd) continue;

      const detailRow = mainRow.nextElementSibling;
      if (!detailRow || !detailRow.classList.contains('g-table_spanned')) continue;

      const dq = (label) => detailRow.querySelector('td[data-label="' + label + '"]');
      const statusTd = dq('状況');
      const dateTd   = dq('公演日');
      const venueTd  = dq('会場名');
      const seatTd   = dq('席種');
      const amountTd = dq('数量');
      const priceTd  = dq('金額');
      const linkEl   = detailRow.querySelector('a.g-link-key');

      // 予約日時: <br> を空白に置換してから取得
      let reservedAt = '';
      if (reservedTd) {
        const clone = reservedTd.cloneNode(true);
        clone.querySelectorAll('br').forEach((br) => br.replaceWith(' '));
        reservedAt = clone.textContent.trim().replace(/\s+/g, ' ');
      }

      // 公演日セル: "YYYY/MM/DD(曜) タイトル 開場 HH:MM 開演 HH:MM"
      const dateText = dateTd ? dateTd.textContent : '';
      const dateMatch  = dateText.match(/(\d{4})\/(\d{2})\/(\d{2})/);
      const openMatch  = dateText.match(/開場\s*(\d{2}:\d{2})/);
      const startMatch = dateText.match(/開演\s*(\d{2}:\d{2})/);

      // ステータス判定
      let status = 'other';
      let statusText = '';
      if (statusTd) {
        if (statusTd.querySelector('.g-tag-ng')) {
          status = 'lost';
          statusText = '落選';
        } else if (statusTd.textContent.includes('未発券')) {
          status = 'unticketed';
          statusText = '未発券';
        } else if (statusTd.textContent.includes('入金済')) {
          status = 'paid';
          statusText = '入金済';
        } else if (statusTd.querySelector('.g-tag-ok')) {
          status = 'won';
          statusText = '当選';
        } else {
          statusText = statusTd.textContent.trim().replace(/\s+/g, ' ');
        }
      }

      // 詳細 URL: ticket.fany.lol/history/detail/ のみ許可
      const rawHref = linkEl ? linkEl.href : '';
      const detailUrl = rawHref.startsWith('https://ticket.fany.lol/history/detail/')
        ? rawHref
        : '';

      result.push({
        id: orderTd ? orderTd.textContent.trim() : '',
        title: titleTd.textContent.trim(),
        performance_date: dateMatch ? dateMatch[1] + '-' + dateMatch[2] + '-' + dateMatch[3] : '',
        open_time:  openMatch  ? openMatch[1]  : '',
        start_time: startMatch ? startMatch[1] : '',
        venue:     venueTd  ? venueTd.textContent.trim()  : '',
        reserved_at: reservedAt,
        status,
        status_text: statusText,
        seat_type: seatTd  ? seatTd.textContent.trim()   : '',
        quantity:  amountTd ? parseInt((amountTd.textContent.match(/\d+/) || ['1'])[0], 10) : 1,
        price:     priceTd  ? parseInt(priceTd.textContent.replace(/[^\d]/g, '') || '0', 10) : 0,
        detail_url: detailUrl,
      });
    }
    return result;
  }

  try {
    for (let page = 1; page <= MAX_PAGES; page++) {
      document.title = '取得中 ' + page + '/' + MAX_PAGES + '...';
      const res = await fetch('/history?ticket_page=' + page, { credentials: 'include' });
      if (!res.ok) {
        const msg = res.status === 401
          ? '再ログインしてから実行してください。'
          : 'HTTP ' + res.status;
        throw new Error(msg);
      }
      const pageEntries = parseDoc(await res.text());
      if (pageEntries.length === 0) break;
      entries.push(...pageEntries);
      await new Promise((r) => setTimeout(r, DELAY_MS));
    }
  } catch (e) {
    document.title = origTitle;
    alert('取得エラー: ' + e.message);
    return;
  }

  document.title = origTitle;

  if (entries.length === 0) {
    alert('履歴が見つかりませんでした。');
    return;
  }

  const msg = {
    type: 'fanaby-history',
    payload: entries,
    scrapedAt: new Date().toISOString(),
  };

  // ビューワーが読み込まれるのを待ってから送信（フェッチに数秒かかるため概ね不要だが念のため）
  const send = () => {
    try { vw.postMessage(msg, VIEWER); } catch (_) {}
  };
  if (vw && vw.document && vw.document.readyState === 'complete') {
    send();
  } else {
    setTimeout(send, 2500);
  }

  alert(entries.length + '件の履歴を取得しました。\nビューワーを確認してください。');
})();

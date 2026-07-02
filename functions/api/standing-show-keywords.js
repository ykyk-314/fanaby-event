/**
 * GET /api/standing-show-keywords — 定常公演キーワードの劇場別カタログ（共有・CF Access）
 * merge.py が KV `standing-show-keywords` に初期投入する。ユーザー個別の差分はない。
 */

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function onRequestGet({ env }) {
  try {
    const raw = await env.FANABY_VIEWING_STATUSES.get('standing-show-keywords', 'json');
    const venues = raw && typeof raw.venues === 'object' && raw.venues !== null ? raw.venues : {};
    return json({ venues });
  } catch (e) {
    console.error('GET /api/standing-show-keywords error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

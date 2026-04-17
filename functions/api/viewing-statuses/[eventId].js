/**
 * PATCH /api/viewing-statuses/:eventId  — 単一イベントの観覧ステータス・メモを更新
 * DELETE /api/viewing-statuses/:eventId — 単一イベントの観覧ステータスを削除
 *
 * ユーザー識別: Cloudflare Access が付与する CF-Access-Authenticated-User-Email を使用。
 * KVキー: `status:{sha256(email)}`（メールアドレスを平文でKVに保存しない）
 */

const EMPTY_DATA = { schema_version: 1, statuses: {} };

const VALID_VIEWING_STATUSES = new Set([
  'want',
  'lottery_applied',
  'lottery_lost',
  'purchased',
  'attended',
]);

const EVENT_ID_RE = /^[0-9a-f]{8}$/;
const MEMO_MAX_LEN = 1000;
const HISTORY_MAX_LEN = 100;

async function getUserKey(request) {
  const email = request.headers.get('CF-Access-Authenticated-User-Email') || '';
  if (!email) return null;
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email));
  const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
  return `status:${hex}`;
}

async function loadData(env, kvKey) {
  const data = await env.FANABY_VIEWING_STATUSES.get(kvKey, 'json');
  return data || { ...EMPTY_DATA, statuses: {} };
}

async function saveData(env, kvKey, data) {
  data.updated_at = new Date().toISOString();
  await env.FANABY_VIEWING_STATUSES.put(kvKey, JSON.stringify(data));
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function onRequestPatch({ request, params, env }) {
  const kvKey = await getUserKey(request);
  if (!kvKey) return jsonResponse({ error: 'Unauthorized' }, 401);

  const eventId = params.eventId;
  if (!EVENT_ID_RE.test(eventId)) return jsonResponse({ error: 'invalid eventId' }, 400);

  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: 'invalid JSON' }, 400);
  }

  if (!body) return jsonResponse({ error: 'request body required' }, 400);

  // status と memo の両方が未指定はエラー
  if (body.status === undefined && body.memo === undefined) {
    return jsonResponse({ error: 'status or memo required' }, 400);
  }
  // status が指定されている場合はホワイトリスト検証（空文字はステータスなしとして許容）
  if (body.status !== undefined && body.status !== '' && !VALID_VIEWING_STATUSES.has(body.status)) {
    return jsonResponse({ error: 'invalid status value' }, 400);
  }
  if (body.memo !== undefined) {
    if (typeof body.memo !== 'string') return jsonResponse({ error: 'memo must be a string' }, 400);
    if (body.memo.length > MEMO_MAX_LEN) return jsonResponse({ error: `memo exceeds ${MEMO_MAX_LEN} chars` }, 400);
  }

  try {
    const data = await loadData(env, kvKey);
    const now = new Date().toISOString();
    const existing = data.statuses[eventId] || { history: [], memo: '', status: '' };

    if (body.status !== undefined) {
      existing.status = body.status;
      if (body.status) {
        existing.history = existing.history || [];
        existing.history.push({ status: body.status, at: now });
        if (existing.history.length > HISTORY_MAX_LEN) {
          existing.history = existing.history.slice(-HISTORY_MAX_LEN);
        }
      }
    }
    if (body.memo !== undefined) existing.memo = body.memo;
    existing.updated_at = now;

    data.statuses[eventId] = existing;
    await saveData(env, kvKey, data);

    return jsonResponse({ ok: true, updated_at: now });
  } catch (e) {
    console.error('PATCH /api/viewing-statuses/:eventId error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

export async function onRequestDelete({ request, params, env }) {
  const kvKey = await getUserKey(request);
  if (!kvKey) return jsonResponse({ error: 'Unauthorized' }, 401);

  const eventId = params.eventId;
  if (!EVENT_ID_RE.test(eventId)) return jsonResponse({ error: 'invalid eventId' }, 400);

  try {
    const data = await loadData(env, kvKey);
    delete data.statuses[eventId];
    await saveData(env, kvKey, data);
    return jsonResponse({ ok: true });
  } catch (e) {
    console.error('DELETE /api/viewing-statuses/:eventId error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

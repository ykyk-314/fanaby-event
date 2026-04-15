/**
 * PATCH /api/viewing-statuses/:eventId  — 単一イベントの観覧ステータスを更新
 * DELETE /api/viewing-statuses/:eventId — 単一イベントの観覧ステータスを削除
 */

const KV_KEY = 'user_viewing_statuses';
const EMPTY_DATA = { schema_version: 1, statuses: {} };

// フロントエンドの VIEWING_STATUSES と同期させること
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

async function loadData(env) {
  const data = await env.FANABY_VIEWING_STATUSES.get(KV_KEY, 'json');
  return data || { ...EMPTY_DATA, statuses: {} };
}

async function saveData(env, data) {
  data.updated_at = new Date().toISOString();
  await env.FANABY_VIEWING_STATUSES.put(KV_KEY, JSON.stringify(data));
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function onRequestPatch(context) {
  const eventId = context.params.eventId;

  if (!EVENT_ID_RE.test(eventId)) {
    return jsonResponse({ error: 'invalid eventId' }, 400);
  }

  let body;
  try {
    body = await context.request.json();
  } catch {
    return jsonResponse({ error: 'invalid JSON' }, 400);
  }

  if (!body || !body.status) {
    return jsonResponse({ error: 'status required' }, 400);
  }
  if (!VALID_VIEWING_STATUSES.has(body.status)) {
    return jsonResponse({ error: 'invalid status value' }, 400);
  }
  if (body.memo !== undefined) {
    if (typeof body.memo !== 'string') {
      return jsonResponse({ error: 'memo must be a string' }, 400);
    }
    if (body.memo.length > MEMO_MAX_LEN) {
      return jsonResponse({ error: `memo exceeds ${MEMO_MAX_LEN} chars` }, 400);
    }
  }

  try {
    const data = await loadData(context.env);
    const now = new Date().toISOString();
    const existing = data.statuses[eventId] || { history: [], memo: '' };

    existing.status = body.status;
    existing.updated_at = now;
    existing.history = existing.history || [];
    existing.history.push({ status: body.status, at: now });

    // 履歴が上限を超えたら古いものを削除
    if (existing.history.length > HISTORY_MAX_LEN) {
      existing.history = existing.history.slice(-HISTORY_MAX_LEN);
    }

    if (body.memo !== undefined) existing.memo = body.memo;

    data.statuses[eventId] = existing;
    await saveData(context.env, data);

    return jsonResponse({ ok: true, updated_at: now });
  } catch (e) {
    console.error('PATCH /api/viewing-statuses/:eventId error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

export async function onRequestDelete(context) {
  const eventId = context.params.eventId;

  if (!EVENT_ID_RE.test(eventId)) {
    return jsonResponse({ error: 'invalid eventId' }, 400);
  }

  try {
    const data = await loadData(context.env);
    delete data.statuses[eventId];
    await saveData(context.env, data);

    return jsonResponse({ ok: true });
  } catch (e) {
    console.error('DELETE /api/viewing-statuses/:eventId error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

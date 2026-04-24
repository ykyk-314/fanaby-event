/**
 * GET    /api/excluded-events — 除外イベントIDリスト取得
 * POST   /api/excluded-events — 除外イベントID追加 (body: { eventId })
 * DELETE /api/excluded-events — 除外イベントID解除 (body: { eventId })
 *
 * 認証:
 *   GET:         Bearer {REMIND_API_SECRET} または CF-Access 認証済み
 *   POST/DELETE: CF-Access 認証済み（ヘッダーまたは Cookie）
 *
 * /api/excluded-events は fanaby-event-api (bypass) アプリ配下のため
 * CF-Access-Authenticated-User-Email ヘッダーが付与されない。
 * bypass パスでもブラウザはログイン済みなら CF_Authorization Cookie を送信するため
 * Cookie の存在で認証済みを判定する。
 */

const KV_KEY = 'excluded_events';
const EVENT_ID_RE = /^[0-9a-f]{8}$/;

function isBearerAuthorized(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const secret = env.REMIND_API_SECRET || '';
  return secret && auth === `Bearer ${secret}`;
}

function isCfAccessAuthorized(request) {
  if (request.headers.get('CF-Access-Authenticated-User-Email')) return true;
  const cookie = request.headers.get('Cookie') || '';
  return /\bCF_Authorization=[A-Za-z0-9._-]+/.test(cookie);
}

async function getExcludedIds(env) {
  const raw = await env.FANABY_VIEWING_STATUSES.get(KV_KEY, 'json');
  return raw?.ids ?? [];
}

async function saveExcludedIds(env, ids) {
  await env.FANABY_VIEWING_STATUSES.put(KV_KEY, JSON.stringify({
    ids,
    updated_at: new Date().toISOString(),
  }));
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function onRequest({ request, env }) {
  const method = request.method;

  if (method === 'GET') {
    if (!isBearerAuthorized(request, env) && !isCfAccessAuthorized(request)) {
      return json({ error: 'Unauthorized' }, 401);
    }
    try {
      const ids = await getExcludedIds(env);
      return json({ ids });
    } catch (e) {
      console.error('GET /api/excluded-events error:', e);
      return json({ error: 'internal error' }, 500);
    }
  }

  if (method === 'POST' || method === 'DELETE') {
    if (!isCfAccessAuthorized(request)) {
      return json({ error: 'Unauthorized' }, 401);
    }
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: 'invalid JSON' }, 400);
    }
    const { eventId } = body;
    if (!eventId || !EVENT_ID_RE.test(eventId)) {
      return json({ error: 'invalid eventId' }, 400);
    }
    try {
      const ids = await getExcludedIds(env);
      const updated = method === 'POST'
        ? (ids.includes(eventId) ? ids : [...ids, eventId])
        : ids.filter(id => id !== eventId);
      await saveExcludedIds(env, updated);
      return json({ ids: updated });
    } catch (e) {
      console.error(`${method} /api/excluded-events error:`, e);
      return json({ error: 'internal error' }, 500);
    }
  }

  return json({ error: 'Method Not Allowed' }, 405);
}

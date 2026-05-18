/**
 * PATCH  /api/talents/:id — name/image_url 補完（Bearer・スクリプト用）
 * DELETE /api/talents/:id — マスタから物理削除（CF Access + admin のみ）
 */

const KV_KEY = 'talents';
const TALENT_ID_RE = /^\d+$/;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function getCallerEmail(request) {
  return (request.headers.get('CF-Access-Authenticated-User-Email') || '').toLowerCase();
}

function getAdminEmails(env) {
  return (env.ADMIN_EMAILS || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
}

function isAdmin(request, env) {
  const email = getCallerEmail(request);
  return !!email && getAdminEmails(env).includes(email);
}

function isBearerAuthorized(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const secret = env.REMIND_API_SECRET || '';
  return secret && auth === `Bearer ${secret}`;
}

async function getMaster(env) {
  const raw = await env.FANABY_VIEWING_STATUSES.get(KV_KEY, 'json');
  return raw ?? { schema_version: 1, talents: [], updated_at: null };
}

export async function onRequestPatch({ request, params, env }) {
  if (!isBearerAuthorized(request, env)) return json({ error: 'Unauthorized' }, 401);

  const { talentId } = params;
  if (!TALENT_ID_RE.test(talentId)) return json({ error: 'invalid talentId' }, 400);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'invalid JSON' }, 400); }

  if (body.name === undefined && body.image_url === undefined && body.local_image === undefined) {
    return json({ error: 'nothing to update' }, 400);
  }

  try {
    const master = await getMaster(env);
    const idx = master.talents.findIndex(t => t.id === talentId);
    if (idx === -1) return json({ error: 'talent not found' }, 404);

    if (body.name !== undefined) master.talents[idx].name = body.name || null;
    if (body.image_url !== undefined) master.talents[idx].image_url = body.image_url || null;
    if (body.local_image !== undefined) master.talents[idx].local_image = body.local_image || null;
    master.updated_at = new Date().toISOString();
    await env.FANABY_VIEWING_STATUSES.put(KV_KEY, JSON.stringify(master));
    return json({ ok: true });
  } catch (e) {
    console.error('PATCH /api/talents/:id error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

export async function onRequestDelete({ request, params, env }) {
  if (!isAdmin(request, env)) return json({ error: 'Forbidden' }, 403);

  const { talentId } = params;
  if (!TALENT_ID_RE.test(talentId)) return json({ error: 'invalid talentId' }, 400);

  try {
    const master = await getMaster(env);
    const before = master.talents.length;
    master.talents = master.talents.filter(t => t.id !== talentId);
    if (master.talents.length === before) return json({ error: 'talent not found' }, 404);

    master.updated_at = new Date().toISOString();
    await env.FANABY_VIEWING_STATUSES.put(KV_KEY, JSON.stringify(master));
    return json({ ok: true });
  } catch (e) {
    console.error('DELETE /api/talents/:id error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

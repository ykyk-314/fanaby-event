/**
 * GET /api/user-talents — 自分のフォロー芸人一覧（CF Access）
 * PUT /api/user-talents — フォロー全置換（CF Access）body: { talent_ids: [...] }
 */

import { sha256hex, getCallerEmail } from '../_lib/auth.js';

const KV_PREFIX = 'user-talents:';
const TALENT_ID_RE = /^\d+$/;
const MAX_FOLLOWS = 50;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function getUserKey(email) {
  return KV_PREFIX + await sha256hex(email);
}

async function getUserTalents(env, email) {
  const key = await getUserKey(email);
  const raw = await env.FANABY_VIEWING_STATUSES.get(key, 'json');
  return raw ?? { schema_version: 1, talent_ids: [], updated_at: null };
}

export async function onRequestGet({ request, env }) {
  const email = getCallerEmail(request);
  if (!email) return json({ error: 'Unauthorized' }, 401);
  try {
    return json(await getUserTalents(env, email));
  } catch (e) {
    console.error('GET /api/user-talents error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

export async function onRequestPut({ request, env }) {
  const email = getCallerEmail(request);
  if (!email) return json({ error: 'Unauthorized' }, 401);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'invalid JSON' }, 400); }

  if (!Array.isArray(body.talent_ids)) return json({ error: 'talent_ids must be array' }, 400);
  if (body.talent_ids.length > MAX_FOLLOWS) return json({ error: `max ${MAX_FOLLOWS} follows` }, 400);
  if (!body.talent_ids.every(id => TALENT_ID_RE.test(String(id)))) {
    return json({ error: 'invalid talent_id in array' }, 400);
  }

  const uniqueIds = [...new Set(body.talent_ids.map(String))];

  try {
    const key = await getUserKey(email);
    const data = {
      schema_version: 1,
      talent_ids: uniqueIds,
      updated_at: new Date().toISOString(),
    };
    await env.FANABY_VIEWING_STATUSES.put(key, JSON.stringify(data));
    return json({ ok: true, updated_at: data.updated_at });
  } catch (e) {
    console.error('PUT /api/user-talents error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

/**
 * GET /api/user-exclude-keywords — 自分の除外キーワード一覧（任意のタイトル部分一致・CF Access）
 *   未設定時は空リストを返す
 * PUT /api/user-exclude-keywords — 全置換（CF Access）body: { keywords: [...] }
 */

import { sha256hex, getCallerEmail } from '../_lib/auth.js';

const KV_PREFIX = 'user-exclude-keywords:';
const MAX_KEYWORDS = 100;
const MAX_KW_LEN = 100;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function getUserKey(email) {
  return KV_PREFIX + await sha256hex(email);
}

export async function onRequestGet({ request, env }) {
  const email = getCallerEmail(request);
  if (!email) return json({ error: 'Unauthorized' }, 401);
  try {
    const key = await getUserKey(email);
    const raw = await env.FANABY_VIEWING_STATUSES.get(key, 'json');
    if (raw && Array.isArray(raw.keywords)) return json(raw);

    return json({ schema_version: 1, keywords: [], updated_at: null, is_default: true });
  } catch (e) {
    console.error('GET /api/user-exclude-keywords error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

export async function onRequestPut({ request, env }) {
  const email = getCallerEmail(request);
  if (!email) return json({ error: 'Unauthorized' }, 401);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'invalid JSON' }, 400); }

  if (!Array.isArray(body.keywords)) return json({ error: 'keywords must be array' }, 400);
  if (body.keywords.length > MAX_KEYWORDS) return json({ error: `max ${MAX_KEYWORDS} keywords` }, 400);
  if (!body.keywords.every(k => typeof k === 'string')) {
    return json({ error: 'keywords must be strings' }, 400);
  }

  const normalized = body.keywords.map(k => k.trim()).filter(k => k.length > 0);
  if (normalized.some(k => k.length > MAX_KW_LEN)) {
    return json({ error: `keyword too long (max ${MAX_KW_LEN} chars)` }, 400);
  }
  const uniqueKeywords = [...new Set(normalized)];

  try {
    const key = await getUserKey(email);
    const data = {
      schema_version: 1,
      keywords: uniqueKeywords,
      updated_at: new Date().toISOString(),
    };
    await env.FANABY_VIEWING_STATUSES.put(key, JSON.stringify(data));
    return json({ ok: true, updated_at: data.updated_at });
  } catch (e) {
    console.error('PUT /api/user-exclude-keywords error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

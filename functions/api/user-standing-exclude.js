/**
 * GET /api/user-standing-exclude — 定常公演の除外設定（CF Access）
 *   未設定時はデフォルト { mode: "all", venues: [] } を返す
 * PUT /api/user-standing-exclude — 設定を保存（CF Access）body: { mode, venues }
 *   mode: "off" | "all" | "venues"
 */

import { sha256hex, getCallerEmail } from '../_lib/auth.js';

const KV_PREFIX = 'user-standing-exclude:';
const VALID_MODES = ['off', 'all', 'venues'];
const VALID_VENUES = [
  '渋谷よしもと漫才劇場',
  '神保町よしもと漫才劇場',
  'ルミネtheよしもと',
  'YOSHIMOTO ROPPONGI THEATER',
  '大宮ラクーンよしもと劇場',
  'よしもと幕張イオンモール劇場',
  'よしもと漫才劇場',
  '森ノ宮よしもと漫才劇場',
  'よしもと福岡 大和証券劇場',
  'よしもと道頓堀シアター',
  '沼津ラクーンよしもと劇場',
  'なんばグランド花月',
];

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
    if (raw && VALID_MODES.includes(raw.mode)) return json(raw);

    return json({ schema_version: 1, mode: 'all', venues: [], updated_at: null, is_default: true });
  } catch (e) {
    console.error('GET /api/user-standing-exclude error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

export async function onRequestPut({ request, env }) {
  const email = getCallerEmail(request);
  if (!email) return json({ error: 'Unauthorized' }, 401);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'invalid JSON' }, 400); }

  if (!VALID_MODES.includes(body.mode)) {
    return json({ error: `mode must be one of ${VALID_MODES.join(', ')}` }, 400);
  }
  if (body.venues !== undefined && !Array.isArray(body.venues)) {
    return json({ error: 'venues must be array' }, 400);
  }

  const venues = body.mode === 'venues'
    ? [...new Set((body.venues || []).filter(v => VALID_VENUES.includes(v)))]
    : [];

  try {
    const key = await getUserKey(email);
    const data = {
      schema_version: 1,
      mode: body.mode,
      venues,
      updated_at: new Date().toISOString(),
    };
    await env.FANABY_VIEWING_STATUSES.put(key, JSON.stringify(data));
    return json({ ok: true, updated_at: data.updated_at });
  } catch (e) {
    console.error('PUT /api/user-standing-exclude error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

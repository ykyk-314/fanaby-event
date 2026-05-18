/**
 * GET  /api/talents — マスタ一覧取得（Bearer または CF Access）
 * POST /api/talents — 新規芸人追加（CF Access）body: { url, id?, name? }
 * PUT  /api/talents — マスタ全体更新（Bearer・スクリプト用）
 */

import { getCallerEmail } from '../../_lib/auth.js';

const KV_KEY = 'talents';
const TALENT_ID_RE = /^\d+$/;
const MAX_TALENTS = 200;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
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

function extractTalentId(input) {
  const urlMatch = String(input).match(/[?&]id=(\d+)/);
  if (urlMatch) return urlMatch[1];
  const trimmed = String(input).trim();
  if (TALENT_ID_RE.test(trimmed)) return trimmed;
  return null;
}

export async function onRequestGet({ request, env }) {
  if (!isBearerAuthorized(request, env) && !getCallerEmail(request)) {
    return json({ error: 'Unauthorized' }, 401);
  }
  try {
    return json(await getMaster(env));
  } catch (e) {
    console.error('GET /api/talents error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

export async function onRequestPost({ request, env }) {
  const email = getCallerEmail(request);
  if (!email) return json({ error: 'Unauthorized' }, 401);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'invalid JSON' }, 400); }

  const rawInput = body.url || body.id || '';
  const talentId = extractTalentId(rawInput);
  if (!talentId) return json({ error: 'invalid url or id' }, 400);

  try {
    const master = await getMaster(env);
    if (master.talents.length >= MAX_TALENTS) {
      return json({ error: 'talent master is full' }, 400);
    }
    if (master.talents.some(t => t.id === talentId)) {
      return json({ error: 'talent already exists', id: talentId }, 409);
    }
    const entry = {
      id: talentId,
      name: body.name || null,
      image_url: null,
      profile_url: body.url || `https://profile.yoshimoto.co.jp/talent/detail?id=${talentId}`,
      added_at: new Date().toISOString(),
      added_by: email,
    };
    master.talents.push(entry);
    master.updated_at = new Date().toISOString();
    await env.FANABY_VIEWING_STATUSES.put(KV_KEY, JSON.stringify(master));

    // KV 保存成功後に即時スクレイプをトリガー（失敗しても KV はロールバックしない）
    const scrape_triggered = await triggerScrape(env, talentId);

    return json({ ok: true, talent: entry, scrape_triggered });
  } catch (e) {
    console.error('POST /api/talents error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

async function triggerScrape(env, talentId) {
  const ghRepo  = env.GH_REPO || '';
  const ghToken = env.GH_DISPATCH_TOKEN || '';
  if (!ghRepo || !ghToken) return false;
  try {
    const res = await fetch(`https://api.github.com/repos/${ghRepo}/dispatches`, {
      method: 'POST',
      headers: {
        'Authorization':        `Bearer ${ghToken}`,
        'Accept':               'application/vnd.github+json',
        'Content-Type':         'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent':           'fanaby-event',
      },
      body: JSON.stringify({ event_type: 'talent-added', client_payload: { talent_id: talentId } }),
    });
    if (!res.ok) {
      console.error('talent-added dispatch failed:', res.status, await res.text());
      return false;
    }
    return true;
  } catch (e) {
    console.error('talent-added dispatch error:', e);
    return false;
  }
}

export async function onRequestPut({ request, env }) {
  if (!isBearerAuthorized(request, env)) return json({ error: 'Unauthorized' }, 401);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'invalid JSON' }, 400); }

  if (!Array.isArray(body.talents)) return json({ error: 'talents must be array' }, 400);

  try {
    const master = {
      schema_version: 1,
      talents: body.talents,
      updated_at: new Date().toISOString(),
    };
    await env.FANABY_VIEWING_STATUSES.put(KV_KEY, JSON.stringify(master));
    return json({ ok: true, updated_at: master.updated_at });
  } catch (e) {
    console.error('PUT /api/talents error:', e);
    return json({ error: 'internal error' }, 500);
  }
}

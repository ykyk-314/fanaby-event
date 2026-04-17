/**
 * GET /api/viewing-statuses  — ユーザーの全観覧ステータスを取得
 * PUT /api/viewing-statuses  — 全ステータスを一括置換（移行・インポート用）
 *
 * ユーザー識別: Cloudflare Access が付与する CF-Access-Authenticated-User-Email を使用。
 * KVキー: `status:{sha256(email)}`（メールアドレスを平文でKVに保存しない）
 */

const EMPTY_DATA = { schema_version: 1, statuses: {} };
const PUT_SIZE_LIMIT = 1024 * 1024; // 1MB

async function getUserKey(request) {
  const email = request.headers.get('CF-Access-Authenticated-User-Email') || '';
  if (!email) return null;
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email));
  const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
  return `status:${hex}`;
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function onRequestGet({ request, env }) {
  const kvKey = await getUserKey(request);
  if (!kvKey) return jsonResponse({ error: 'Unauthorized' }, 401);

  try {
    const data = await env.FANABY_VIEWING_STATUSES.get(kvKey, 'json');
    return jsonResponse(data || EMPTY_DATA);
  } catch (e) {
    console.error('GET /api/viewing-statuses error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

export async function onRequestPut({ request, env }) {
  const kvKey = await getUserKey(request);
  if (!kvKey) return jsonResponse({ error: 'Unauthorized' }, 401);

  const contentLength = parseInt(request.headers.get('content-length') || '0', 10);
  if (contentLength > PUT_SIZE_LIMIT) return jsonResponse({ error: 'payload too large' }, 413);

  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: 'invalid JSON' }, 400);
  }

  if (!body || body.statuses === null || Array.isArray(body.statuses) || typeof body.statuses !== 'object') {
    return jsonResponse({ error: 'invalid schema' }, 400);
  }

  body.schema_version = body.schema_version || 1;
  body.updated_at = new Date().toISOString();

  try {
    await env.FANABY_VIEWING_STATUSES.put(kvKey, JSON.stringify(body));
    return jsonResponse({ ok: true });
  } catch (e) {
    console.error('PUT /api/viewing-statuses error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

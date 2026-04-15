/**
 * GET /api/viewing-statuses  — 全観覧ステータスを取得
 * PUT /api/viewing-statuses  — 全ステータスを一括置換（移行・インポート用）
 */

const KV_KEY = 'user_viewing_statuses';
const EMPTY_DATA = { schema_version: 1, statuses: {} };

// PUT ペイロードの上限（25MiB のうち安全マージン: 1MB）
const PUT_SIZE_LIMIT = 1024 * 1024;

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function onRequestGet(context) {
  try {
    const data = await context.env.FANABY_VIEWING_STATUSES.get(KV_KEY, 'json');
    return jsonResponse(data || EMPTY_DATA);
  } catch (e) {
    console.error('GET /api/viewing-statuses error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

export async function onRequestPut(context) {
  // ペイロードサイズチェック
  const contentLength = parseInt(context.request.headers.get('content-length') || '0', 10);
  if (contentLength > PUT_SIZE_LIMIT) {
    return jsonResponse({ error: 'payload too large' }, 413);
  }

  let body;
  try {
    body = await context.request.json();
  } catch {
    return jsonResponse({ error: 'invalid JSON' }, 400);
  }

  // statuses が null や配列でないことも確認
  if (
    !body ||
    body.statuses === null ||
    Array.isArray(body.statuses) ||
    typeof body.statuses !== 'object'
  ) {
    return jsonResponse({ error: 'invalid schema' }, 400);
  }

  body.schema_version = body.schema_version || 1;
  body.updated_at = new Date().toISOString();

  try {
    await context.env.FANABY_VIEWING_STATUSES.put(KV_KEY, JSON.stringify(body));
    return jsonResponse({ ok: true });
  } catch (e) {
    console.error('PUT /api/viewing-statuses error:', e);
    return jsonResponse({ error: 'internal error' }, 500);
  }
}

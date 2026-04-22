/**
 * GET /api/me — 認証済みユーザーの情報を返す
 * Cloudflare Access が付与する CF-Access-Authenticated-User-Email ヘッダーを使用する。
 * 初回アクセス時および email 変更時に user:{SHA256(email)} をKVに保存する。
 */

async function getUserHash(email) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function onRequestGet({ request, env }) {
  const email = request.headers.get('CF-Access-Authenticated-User-Email') || '';
  if (!email) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // user:{hash} KV にメールアドレスを保存（既存と一致する場合はスキップ）
  try {
    const hash = await getUserHash(email);
    const key = `user:${hash}`;
    const existing = await env.FANABY_VIEWING_STATUSES.get(key, 'json');
    if (!existing || existing.email !== email) {
      await env.FANABY_VIEWING_STATUSES.put(key, JSON.stringify({
        email,
        updated_at: new Date().toISOString(),
      }));
    }
  } catch (e) {
    console.error('user profile save failed:', e);
    // 保存失敗時もレスポンスは続行
  }

  return new Response(
    JSON.stringify({ email, initial: email[0].toUpperCase() }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  );
}

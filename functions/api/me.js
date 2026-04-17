/**
 * GET /api/me — 認証済みユーザーの情報を返す
 * Cloudflare Access が付与する CF-Access-Authenticated-User-Email ヘッダーを使用する。
 */

export async function onRequestGet({ request }) {
  const email = request.headers.get('CF-Access-Authenticated-User-Email') || '';
  if (!email) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  return new Response(
    JSON.stringify({ email, initial: email[0].toUpperCase() }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  );
}

/**
 * GET /api/remind-list
 *
 * GitHub Actions の scrape_ticket.py が呼び出す内部 API。
 * KV を走査して remind:true のイベントIDリストを返す。
 *
 * 認証: Authorization: Bearer {REMIND_API_SECRET}
 * （Cloudflare Pages 環境変数 REMIND_API_SECRET と照合）
 */

export async function onRequestGet({ request, env }) {
  const auth   = request.headers.get('Authorization') || '';
  const secret = env.REMIND_API_SECRET || '';

  if (!secret || auth !== `Bearer ${secret}`) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const result   = [];
    let cursor     = undefined;

    // KV.list() でページネーションしながら全ユーザーを走査
    do {
      const listed = await env.FANABY_VIEWING_STATUSES.list({
        prefix: 'status:',
        cursor,
      });

      for (const key of listed.keys) {
        const data = await env.FANABY_VIEWING_STATUSES.get(key.name, 'json');
        if (!data?.statuses) continue;

        // status:{hash} からハッシュを取り出し user:{hash} でメールアドレスを解決
        const hash = key.name.slice('status:'.length);
        let email = null;
        try {
          const profile = await env.FANABY_VIEWING_STATUSES.get(`user:${hash}`, 'json');
          email = profile?.email ?? null;
        } catch {
          // email 解決失敗は許容（remind.py 側でスキップされる）
        }

        for (const [eventId, entry] of Object.entries(data.statuses)) {
          if (entry.remind === true) {
            result.push({ eventId, email });
          }
        }
      }

      cursor = listed.list_complete ? undefined : listed.cursor;
    } while (cursor);

    // 重複排除（同一ユーザーが複数デバイスで同一公演に remind:true をつけた場合）
    const unique = [...new Map(result.map(r => [`${r.eventId}:${r.email ?? ''}`, r])).values()];

    return new Response(JSON.stringify(unique), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (e) {
    console.error('GET /api/remind-list error:', e);
    return new Response(JSON.stringify({ error: 'internal error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

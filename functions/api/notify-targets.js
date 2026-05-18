/**
 * GET /api/notify-targets
 *
 * notify.py が呼び出す内部 API。
 * KV を走査して全ユーザーの {email, talent_ids} リストを返す。
 *
 * 認証: Authorization: Bearer {REMIND_API_SECRET}
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
    const targets = [];
    let cursor    = undefined;

    // user:{hash} キーを走査してメールアドレスを収集
    do {
      const listed = await env.FANABY_VIEWING_STATUSES.list({ prefix: 'user:', cursor });

      for (const key of listed.keys) {
        const hash    = key.name.slice('user:'.length);
        const profile = await env.FANABY_VIEWING_STATUSES.get(key.name, 'json');
        if (!profile?.email) continue;

        const followData = await env.FANABY_VIEWING_STATUSES.get(`user-talents:${hash}`, 'json');
        const talent_ids = Array.isArray(followData?.talent_ids) ? followData.talent_ids : [];

        targets.push({ email: profile.email, talent_ids });
      }

      cursor = listed.list_complete ? undefined : listed.cursor;
    } while (cursor);

    return new Response(JSON.stringify({ targets }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (e) {
    console.error('GET /api/notify-targets error:', e);
    return new Response(JSON.stringify({ error: 'internal error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

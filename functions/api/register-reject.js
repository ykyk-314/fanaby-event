/**
 * GET /api/register-reject?token=xxx — 登録申請を拒否する
 *
 * Cloudflare Access 認証済み（bypass 対象外）。
 * ADMIN_EMAILS に一致するユーザーのみ実行可能。
 * CF Access Group への変更は行わず KV ステータスのみ更新する。
 */

import { isAdmin } from '../_lib/auth.js';

function htmlResponse(title, message, isError = false) {
  const color = isError ? '#e74c3c' : '#e67e22';
  return new Response(`<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title} - fanaby-event</title>
  <style>
    body { font-family: 'Hiragino Sans', 'Noto Sans JP', sans-serif; background: #f0f0f0; margin: 0; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
    .card { background: #fff; border-radius: 8px; padding: 40px 32px; max-width: 480px; width: 90%; box-shadow: 0 2px 8px rgba(0,0,0,.1); text-align: center; }
    h1 { color: ${color}; font-size: 20px; margin-bottom: 16px; }
    p { color: #555; font-size: 14px; line-height: 1.6; }
    a { color: #3498db; text-decoration: none; }
  </style>
</head>
<body>
  <div class="card">
    <h1>${title}</h1>
    <p>${message}</p>
    <p style="margin-top:24px"><a href="/">← サイトトップへ</a></p>
  </div>
</body>
</html>`, { status: isError ? 400 : 200, headers: { 'Content-Type': 'text/html; charset=UTF-8' } });
}

export async function onRequestGet({ request, env }) {
  if (!isAdmin(request, env)) {
    return htmlResponse('権限がありません', 'この操作は管理者のみ実行できます。', true);
  }

  const url = new URL(request.url);
  const token = url.searchParams.get('token') || '';
  if (!token) return htmlResponse('不正なリクエスト', 'トークンが指定されていません。', true);

  const reqKey = `register-req:${token}`;
  let req;
  try {
    req = await env.FANABY_VIEWING_STATUSES.get(reqKey, 'json');
  } catch (e) {
    console.error('register-reject KV get error:', e);
    return htmlResponse('エラー', '申請データの取得に失敗しました。', true);
  }
  if (!req) return htmlResponse('リンク期限切れ', 'このリンクは無効または期限切れです（有効期間: 24時間）。', true);

  if (req.status === 'approved') {
    return htmlResponse('承認済み', 'この申請はすでに承認されています。拒否はできません。', true);
  }
  if (req.status === 'rejected') {
    return htmlResponse('拒否済み', 'この申請はすでに拒否されています。');
  }

  const rejectedAt = new Date().toISOString();
  try {
    await env.FANABY_VIEWING_STATUSES.put(reqKey, JSON.stringify({ ...req, status: 'rejected', rejected_at: rejectedAt }), { expirationTtl: 86400 });
  } catch (e) {
    console.error('register-reject KV update error:', e);
    return htmlResponse('エラー', 'ステータスの更新に失敗しました。', true);
  }

  return htmlResponse('拒否完了', `${req.email} の登録申請を拒否しました。`);
}

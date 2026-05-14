/**
 * GET /api/register-approve?token=xxx — 登録申請を承認する
 *
 * Cloudflare Access 認証済み（bypass 対象外）。
 * ADMIN_EMAILS に一致するユーザーのみ実行可能。
 * 承認後、Cloudflare Access Group にメールアドレスを追加する。
 */

import { sha256hex, isAdmin } from '../_lib/auth.js';

const TTL_APPROVED = 60 * 60 * 24 * 30; // 30日

function htmlResponse(title, message, isError = false) {
  const color = isError ? '#e74c3c' : '#27ae60';
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

async function addEmailToAccessGroup(env, email) {
  const base = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/access/groups/${env.CF_ACCESS_GROUP_ID}`;
  const headers = {
    'Authorization': `Bearer ${env.CF_API_TOKEN}`,
    'Content-Type': 'application/json',
  };

  // 現在のグループ設定を取得
  const getRes = await fetch(base, { headers });
  if (!getRes.ok) {
    const txt = await getRes.text();
    throw new Error(`CF API GET group failed: ${getRes.status} ${txt}`);
  }
  const getJson = await getRes.json();
  const group = getJson.result;

  // すでに追加済みか確認（冪等）
  const include = group.include || [];
  const alreadyAdded = include.some(rule => rule.email?.email?.toLowerCase() === email.toLowerCase());
  if (!alreadyAdded) {
    include.push({ email: { email } });
  }

  // グループを更新
  const putRes = await fetch(base, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ name: group.name, include, exclude: group.exclude || [], require: group.require || [] }),
  });
  if (!putRes.ok) {
    const txt = await putRes.text();
    throw new Error(`CF API PUT group failed: ${putRes.status} ${txt}`);
  }
}

export async function onRequestGet({ request, env }) {
  // 管理者チェック
  if (!isAdmin(request, env)) {
    return htmlResponse('権限がありません', 'この操作は管理者のみ実行できます。', true);
  }

  const url = new URL(request.url);
  const token = url.searchParams.get('token') || '';
  if (!token) return htmlResponse('不正なリクエスト', 'トークンが指定されていません。', true);

  // KV から申請データ取得
  const reqKey = `register-req:${token}`;
  let req;
  try {
    req = await env.FANABY_VIEWING_STATUSES.get(reqKey, 'json');
  } catch (e) {
    console.error('register-approve KV get error:', e);
    return htmlResponse('エラー', '申請データの取得に失敗しました。', true);
  }
  if (!req) return htmlResponse('リンク期限切れ', 'このリンクは無効または期限切れです（有効期間: 24時間）。', true);

  // 冪等: すでに承認済み
  if (req.status === 'approved') {
    return htmlResponse('承認済み', `${req.email} はすでに承認済みです。`);
  }
  if (req.status === 'rejected') {
    return htmlResponse('拒否済み', 'この申請はすでに拒否されています。', true);
  }

  const { email } = req;

  // Cloudflare Access Group にメール追加
  try {
    await addEmailToAccessGroup(env, email);
  } catch (e) {
    console.error('register-approve CF API error:', e);
    return htmlResponse('CF API エラー', `Access Group への追加に失敗しました。再度リンクをクリックしてください。<br>詳細: ${e.message}`, true);
  }

  // KV を承認済みに更新（TTL 30日）
  const emailHash = await sha256hex(email);
  const approvedAt = new Date().toISOString();
  try {
    await Promise.all([
      env.FANABY_VIEWING_STATUSES.put(reqKey, JSON.stringify({ ...req, status: 'approved', approved_at: approvedAt }), { expirationTtl: TTL_APPROVED }),
      env.FANABY_VIEWING_STATUSES.put(`register-email:${emailHash}`, JSON.stringify({ token, status: 'approved', created_at: req.created_at, approved_at: approvedAt }), { expirationTtl: TTL_APPROVED }),
    ]);
  } catch (e) {
    console.error('register-approve KV update error:', e);
    // CF API 追加は成功しているので、KV 更新失敗は警告に留める
  }

  return htmlResponse('承認完了', `${email} を登録しました。次回ログイン時に OTP コードが届くようになります。`);
}

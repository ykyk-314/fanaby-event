/**
 * POST /api/register-request — 新規登録申請受付
 *
 * このエンドポイントは Cloudflare Access の bypass 対象（公開）。
 * Turnstile 検証 → IP レート制限 → 重複申請チェック → KV 保存 → GitHub dispatch
 */

import { sha256hex } from '../_lib/auth.js';

const RATE_LIMIT = 5;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function verifyTurnstile(token, ip, secretKey) {
  const res = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ secret: secretKey, response: token, remoteip: ip }),
  });
  const data = await res.json();
  return data.success === true;
}

async function checkRateLimit(env, ip) {
  const key = `ratelimit:register:${ip}`;
  const raw = await env.FANABY_VIEWING_STATUSES.get(key, 'json');
  const count = (raw?.count ?? 0) + 1;
  await env.FANABY_VIEWING_STATUSES.put(key, JSON.stringify({ count, first_at: raw?.first_at ?? new Date().toISOString() }), { expirationTtl: 3600 });
  return count > RATE_LIMIT;
}

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'invalid JSON' }, 400);
  }

  const email = (body.email || '').trim().toLowerCase();
  if (!EMAIL_RE.test(email)) {
    return json({ error: 'メールアドレスの形式が正しくありません' }, 400);
  }

  // Turnstile 検証（TURNSTILE_SECRET_KEY 未設定時はスキップ）
  if (env.TURNSTILE_SECRET_KEY) {
    const turnstileToken = body['cf-turnstile-response'] || '';
    if (!turnstileToken) return json({ error: 'Turnstile 認証が必要です' }, 400);
    const ip = request.headers.get('CF-Connecting-IP') || '';
    const ok = await verifyTurnstile(turnstileToken, ip, env.TURNSTILE_SECRET_KEY);
    if (!ok) return json({ error: 'Turnstile 認証に失敗しました' }, 400);
  }

  // IP レート制限
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const rateLimited = await checkRateLimit(env, ip);
  if (rateLimited) return json({ error: 'しばらく時間をおいてから再試行してください' }, 429);

  // 重複申請チェック
  const emailHash = await sha256hex(email);
  const emailKey = `register-email:${emailHash}`;
  const existing = await env.FANABY_VIEWING_STATUSES.get(emailKey, 'json');
  if (existing) {
    if (existing.status === 'approved') {
      return json({ error: 'このメールアドレスはすでに登録済みです' }, 409);
    }
    // pending / rejected → 受付済みとして 200 で返す（再申請を静かに受け流す）
    return json({ ok: true, message: '申請は受け付け済みです。管理者の承認をお待ちください。' });
  }

  // トークン生成・KV 保存
  const token = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  const reqKey = `register-req:${token}`;
  const reqVal = { email, created_at: createdAt, status: 'pending' };
  const emailVal = { token, status: 'pending', created_at: createdAt };

  try {
    await Promise.all([
      env.FANABY_VIEWING_STATUSES.put(reqKey, JSON.stringify(reqVal), { expirationTtl: 86400 }),
      env.FANABY_VIEWING_STATUSES.put(emailKey, JSON.stringify(emailVal), { expirationTtl: 86400 }),
    ]);
  } catch (e) {
    console.error('register-request KV put error:', e);
    return json({ error: '申請処理中にエラーが発生しました' }, 500);
  }

  // GitHub repository_dispatch で通知ワークフローを起動
  const ghRepo = env.GH_REPO || '';
  const ghToken = env.GH_DISPATCH_TOKEN || '';
  if (ghRepo && ghToken) {
    try {
      const dispatchRes = await fetch(`https://api.github.com/repos/${ghRepo}/dispatches`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${ghToken}`,
          'Accept': 'application/vnd.github+json',
          'Content-Type': 'application/json',
          'X-GitHub-Api-Version': '2022-11-28',
        },
        body: JSON.stringify({ event_type: 'register-request', client_payload: { token, email } }),
      });
      if (!dispatchRes.ok) {
        const errText = await dispatchRes.text();
        console.error('GitHub dispatch failed:', dispatchRes.status, errText);
        throw new Error(`dispatch status ${dispatchRes.status}: ${errText}`);
      }
    } catch (e) {
      console.error('register-request dispatch error:', e);
      // KV をロールバックしてエラーを返す
      await Promise.allSettled([
        env.FANABY_VIEWING_STATUSES.delete(reqKey),
        env.FANABY_VIEWING_STATUSES.delete(emailKey),
      ]);
      return json({ error: `[DEBUG] dispatch失敗: ${e.message}` }, 500);
    }
  } else {
    console.warn('GH_REPO or GH_DISPATCH_TOKEN not set, skipping dispatch');
  }

  return json({ ok: true, message: '申請を受け付けました。管理者の承認をお待ちください。' });
}

export async function onRequestGet() {
  return new Response('Method Not Allowed', { status: 405 });
}

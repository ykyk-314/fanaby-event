export async function sha256hex(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export function getAdminEmails(env) {
  return (env.ADMIN_EMAILS || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
}

export function getCallerEmail(request) {
  return (request.headers.get('CF-Access-Authenticated-User-Email') || '').toLowerCase();
}

export function isAdmin(request, env) {
  const email = getCallerEmail(request);
  if (!email) return false;
  return getAdminEmails(env).includes(email);
}

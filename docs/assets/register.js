(function () {
  const form = document.getElementById('register-form');
  const submitBtn = document.getElementById('submit-btn');
  const resultEl = document.getElementById('result');

  if (!form) return;

  function showResult(message, isError) {
    resultEl.textContent = message;
    resultEl.className = isError ? 'error' : 'success';
    resultEl.style.display = 'block';
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();

    const email = (document.getElementById('email').value || '').trim();
    if (!email) {
      showResult('メールアドレスを入力してください。', true);
      return;
    }

    // Turnstile トークンを取得（widget が未ロードの場合は空文字）
    const turnstileInput = form.querySelector('[name="cf-turnstile-response"]');
    const turnstileToken = turnstileInput ? turnstileInput.value : '';

    submitBtn.disabled = true;
    submitBtn.textContent = '送信中…';
    resultEl.style.display = 'none';

    try {
      const res = await fetch('/api/register-request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, 'cf-turnstile-response': turnstileToken }),
      });

      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        showResult(data.message || '申請を受け付けました。管理者の承認をお待ちください。', false);
        form.reset();
        // Turnstile をリセット
        if (window.turnstile) window.turnstile.reset();
      } else {
        showResult(data.error || 'エラーが発生しました。しばらく後に再試行してください。', true);
        if (window.turnstile) window.turnstile.reset();
      }
    } catch {
      showResult('通信エラーが発生しました。インターネット接続を確認して再試行してください。', true);
      if (window.turnstile) window.turnstile.reset();
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = '申請する';
    }
  });
})();

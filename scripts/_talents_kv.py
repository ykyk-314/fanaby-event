"""
芸人マスタを Cloudflare KV（/api/talents）から取得・更新するヘルパー。
REMIND_API_URL / REMIND_API_SECRET 環境変数を利用する。
各スクリプトから `sys.path` 追加後にインポートして使用する。
"""

import json
import os
import urllib.error
import urllib.request


def _api_headers(api_secret: str) -> dict:
    """Bearer 認証 + CF Access サービストークンヘッダーを構築する。"""
    headers = {"Authorization": f"Bearer {api_secret}"}
    client_id = os.environ.get("CF_ACCESS_CLIENT_ID", "")
    client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")
    if client_id:
        headers["CF-Access-Client-Id"] = client_id
    if client_secret:
        headers["CF-Access-Client-Secret"] = client_secret
    return headers


def fetch_talents_master(config_talents: list[dict]) -> list[dict]:
    """
    GET /api/talents で KV の芸人マスタを取得する。
    環境変数未設定・空マスタ・取得失敗時は config_talents にフォールバック。
    """
    api_url = os.environ.get("REMIND_API_URL", "").rstrip("/")
    api_secret = os.environ.get("REMIND_API_SECRET", "")
    if not api_url or not api_secret:
        print("  REMIND_API_URL/REMIND_API_SECRET 未設定 — config.json の芸人を使用")
        return config_talents
    url = f"{api_url}/api/talents"
    headers = _api_headers(api_secret)
    print(f"  GET {url}")
    print(f"  送信ヘッダー: CF-Access-Client-Id={'あり' if headers.get('CF-Access-Client-Id') else 'なし'}, Authorization=Bearer ***")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            ct = resp.headers.get("Content-Type", "unknown")
            print(f"  レスポンス: HTTP {resp.status}, Content-Type: {ct}")
            data = json.loads(body)
        talents = data.get("talents", [])
        if talents:
            print(f"  KV から芸人マスタ取得: {len(talents)} 件")
            return talents
        print("  KV 芸人マスタが空 — config.json の芸人を使用")
        return config_talents
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:600]
        ct = e.headers.get("Content-Type", "unknown")
        ray = e.headers.get("cf-ray", "none")
        mitigated = e.headers.get("cf-mitigated", "none")
        print(f"  警告: KV 芸人マスタ取得失敗: HTTP {e.code}")
        print(f"    Content-Type: {ct}")
        print(f"    cf-ray: {ray}")
        print(f"    cf-mitigated: {mitigated}")
        print(f"    ボディ(先頭600文字): {body}")
        print("    → config.json の芸人を使用")
        return config_talents
    except Exception as e:
        print(f"  警告: KV 芸人マスタ取得失敗: {e} — config.json の芸人を使用")
        return config_talents


def patch_talent(
    talent_id: str,
    *,
    name: str | None = None,
    image_url: str | None = None,
    local_image: str | None = None,
) -> bool:
    """
    PATCH /api/talents/:id で KV の name/image_url/local_image を更新する。
    """
    api_url = os.environ.get("REMIND_API_URL", "").rstrip("/")
    api_secret = os.environ.get("REMIND_API_SECRET", "")
    if not api_url or not api_secret:
        return False
    body: dict = {}
    if name is not None:
        body["name"] = name
    if image_url is not None:
        body["image_url"] = image_url
    if local_image is not None:
        body["local_image"] = local_image
    if not body:
        return False
    try:
        payload = json.dumps(body).encode("utf-8")
        headers = _api_headers(api_secret)
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{api_url}/api/talents/{talent_id}",
            data=payload,
            headers=headers,
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        mitigated = e.headers.get("cf-mitigated", "none")
        print(f"  警告: KV 芸人更新失敗 ({talent_id}): HTTP {e.code}, cf-mitigated: {mitigated}, ボディ: {body}")
        return False
    except Exception as e:
        print(f"  警告: KV 芸人更新失敗 ({talent_id}): {e}")
        return False

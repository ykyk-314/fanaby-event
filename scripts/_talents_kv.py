"""
芸人マスタを Cloudflare KV から取得・更新するヘルパー。

優先: CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID で KV REST API を直接利用（CF Access バイパス）
フォールバック: REMIND_API_URL + REMIND_API_SECRET で /api/talents エンドポイント経由
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime as _dt

_KV_NAMESPACE_ID = "5b93698258b54a379d7b05c2dafe9739"


def _kv_values_url(cf_account_id: str, key: str = "talents") -> str:
    return (
        f"https://api.cloudflare.com/client/v4/accounts/{cf_account_id}"
        f"/storage/kv/namespaces/{_KV_NAMESPACE_ID}/values/{key}"
    )


def _fetch_from_kv_api(cf_api_token: str, cf_account_id: str) -> "list[dict] | None":
    """Cloudflare KV REST API から talents を直接取得。失敗時は None。"""
    url = _kv_values_url(cf_account_id)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {cf_api_token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("talents", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"  警告: KV REST API 直接読み取り失敗: HTTP {e.code}, body: {body}")
        return None
    except Exception as e:
        print(f"  警告: KV REST API 直接読み取り失敗: {e}")
        return None


def _patch_via_kv_api(cf_api_token: str, cf_account_id: str, talent_id: str, updates: dict) -> bool:
    """Cloudflare KV REST API で talents マスタを直接 read-modify-write する。"""
    url = _kv_values_url(cf_account_id)
    auth_header = {"Authorization": f"Bearer {cf_api_token}"}
    try:
        req = urllib.request.Request(url, headers=auth_header)
        with urllib.request.urlopen(req, timeout=15) as resp:
            master = json.loads(resp.read().decode("utf-8"))
        idx = next(
            (i for i, t in enumerate(master.get("talents", [])) if t.get("id") == talent_id),
            -1,
        )
        if idx == -1:
            print(f"  警告: KV REST API 更新: talent {talent_id} が見つからない")
            return False
        master["talents"][idx].update(updates)
        master["updated_at"] = _dt.utcnow().isoformat() + "Z"
        payload = json.dumps(master, ensure_ascii=False).encode("utf-8")
        put_req = urllib.request.Request(
            url, data=payload,
            headers={**auth_header, "Content-Type": "text/plain"},
            method="PUT",
        )
        with urllib.request.urlopen(put_req, timeout=15) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"  警告: KV REST API 直接更新失敗 ({talent_id}): HTTP {e.code}, body: {body}")
        return False
    except Exception as e:
        print(f"  警告: KV REST API 直接更新失敗 ({talent_id}): {e}")
        return False


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
    芸人マスタを取得する。
    1. Cloudflare KV REST API 直接アクセス（CF Access バイパス）
    2. /api/talents エンドポイント経由（フォールバック）
    3. config.json の talents（最終フォールバック）
    """
    # --- 優先: KV REST API 直接アクセス ---
    cf_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    cf_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if cf_api_token and cf_account_id:
        print("  Cloudflare KV REST API から芸人マスタを直接取得")
        talents = _fetch_from_kv_api(cf_api_token, cf_account_id)
        if talents is not None:
            if talents:
                print(f"  KV から芸人マスタ取得: {len(talents)} 件")
                return talents
            print("  KV 芸人マスタが空 — config.json の芸人を使用")
            return config_talents
        print("  KV REST API 失敗 — /api/talents エンドポイントにフォールバック")

    # --- フォールバック: /api/talents エンドポイント経由 ---
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
    name: "str | None" = None,
    image_url: "str | None" = None,
    local_image: "str | None" = None,
) -> bool:
    """
    芸人マスタの name/image_url/local_image を更新する。
    1. Cloudflare KV REST API 直接 read-modify-write
    2. /api/talents/:id PATCH エンドポイント（フォールバック）
    """
    body: dict = {}
    if name is not None:
        body["name"] = name
    if image_url is not None:
        body["image_url"] = image_url
    if local_image is not None:
        body["local_image"] = local_image
    if not body:
        return False

    # --- 優先: KV REST API 直接アクセス ---
    cf_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    cf_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if cf_api_token and cf_account_id:
        return _patch_via_kv_api(cf_api_token, cf_account_id, talent_id, body)

    # --- フォールバック: /api/talents/:id PATCH エンドポイント ---
    api_url = os.environ.get("REMIND_API_URL", "").rstrip("/")
    api_secret = os.environ.get("REMIND_API_SECRET", "")
    if not api_url or not api_secret:
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
        body_str = e.read().decode("utf-8", errors="replace")[:300]
        mitigated = e.headers.get("cf-mitigated", "none")
        print(f"  警告: KV 芸人更新失敗 ({talent_id}): HTTP {e.code}, cf-mitigated: {mitigated}, ボディ: {body_str}")
        return False
    except Exception as e:
        print(f"  警告: KV 芸人更新失敗 ({talent_id}): {e}")
        return False

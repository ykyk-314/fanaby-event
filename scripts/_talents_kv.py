"""
Cloudflare KV ヘルパー。

優先: CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID で KV REST API を直接利用（CF Access バイパス）
フォールバック: REMIND_API_URL + REMIND_API_SECRET で Workers API エンドポイント経由
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime as _dt

_KV_NAMESPACE_ID = "5b93698258b54a379d7b05c2dafe9739"


# ---------------------------------------------------------------------------
# KV REST API 低レベルヘルパー
# ---------------------------------------------------------------------------

def _kv_base(cf_account_id: str) -> str:
    return (
        f"https://api.cloudflare.com/client/v4/accounts/{cf_account_id}"
        f"/storage/kv/namespaces/{_KV_NAMESPACE_ID}"
    )


def _kv_values_url(cf_account_id: str, key: str) -> str:
    return f"{_kv_base(cf_account_id)}/values/{urllib.parse.quote(key, safe='')}"


def _get_kv_json(cf_api_token: str, cf_account_id: str, key: str) -> "dict | None":
    """KV から単一キーの値（JSON）を取得する。キー不在または失敗時は None。"""
    url = _kv_values_url(cf_account_id, key)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {cf_api_token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  警告: KV 値取得失敗 ({key}): HTTP {e.code}")
        return None
    except Exception as e:
        print(f"  警告: KV 値取得失敗 ({key}): {e}")
        return None


def _put_kv_json(cf_api_token: str, cf_account_id: str, key: str, value: dict) -> bool:
    """KV にオブジェクトを JSON 文字列として書き込む。"""
    url = _kv_values_url(cf_account_id, key)
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Authorization": f"Bearer {cf_api_token}", "Content-Type": "text/plain"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"  警告: KV 書き込み失敗 ({key}): HTTP {e.code}, body: {body}")
        return False
    except Exception as e:
        print(f"  警告: KV 書き込み失敗 ({key}): {e}")
        return False


def _list_kv_keys(cf_api_token: str, cf_account_id: str, prefix: str = "") -> "list[str] | None":
    """KV の全キー名を取得する（prefix フィルタ付き、ページネーション対応）。"""
    base_url = f"{_kv_base(cf_account_id)}/keys?limit=1000"
    if prefix:
        base_url += f"&prefix={urllib.parse.quote(prefix, safe='')}"
    auth_header = {"Authorization": f"Bearer {cf_api_token}"}
    keys: list = []
    cursor: "str | None" = None
    while True:
        url = base_url + (f"&cursor={urllib.parse.quote(cursor, safe='')}" if cursor else "")
        try:
            req = urllib.request.Request(url, headers=auth_header)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  警告: KV キー一覧取得失敗: {e}")
            return None
        for item in data.get("result", []):
            keys.append(item["name"])
        cursor = data.get("result_info", {}).get("cursor") or None
        if not cursor:
            break
    return keys


# ---------------------------------------------------------------------------
# Workers API エンドポイント用ヘルパー（フォールバック）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 芸人マスタ取得
# ---------------------------------------------------------------------------

def fetch_talents_master(config_talents: list) -> list:
    """
    芸人マスタを取得する。
    1. Cloudflare KV REST API 直接アクセス（CF Access バイパス）
    2. /api/talents エンドポイント経由（フォールバック）
    3. config.json の talents（最終フォールバック）
    """
    cf_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    cf_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if cf_api_token and cf_account_id:
        print("  Cloudflare KV REST API から芸人マスタを直接取得")
        master = _get_kv_json(cf_api_token, cf_account_id, "talents")
        if master is not None:
            talents = master.get("talents", [])
            if talents:
                print(f"  KV から芸人マスタ取得: {len(talents)} 件")
                return talents
            print("  KV 芸人マスタが空 — config.json の芸人を使用")
            return config_talents
        print("  KV REST API 失敗 — /api/talents エンドポイントにフォールバック")

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


# ---------------------------------------------------------------------------
# 芸人マスタ更新
# ---------------------------------------------------------------------------

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
    updates: dict = {}
    if name is not None:
        updates["name"] = name
    if image_url is not None:
        updates["image_url"] = image_url
    if local_image is not None:
        updates["local_image"] = local_image
    if not updates:
        return False

    cf_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    cf_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if cf_api_token and cf_account_id:
        master = _get_kv_json(cf_api_token, cf_account_id, "talents")
        if master is None:
            print(f"  警告: KV REST API: talents マスタ取得失敗")
            return False
        idx = next(
            (i for i, t in enumerate(master.get("talents", [])) if t.get("id") == talent_id),
            -1,
        )
        if idx == -1:
            print(f"  警告: KV REST API 更新: talent {talent_id} が見つからない")
            return False
        master["talents"][idx].update(updates)
        master["updated_at"] = _dt.utcnow().isoformat() + "Z"
        return _put_kv_json(cf_api_token, cf_account_id, "talents", master)

    api_url = os.environ.get("REMIND_API_URL", "").rstrip("/")
    api_secret = os.environ.get("REMIND_API_SECRET", "")
    if not api_url or not api_secret:
        return False
    try:
        payload = json.dumps(updates).encode("utf-8")
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


# ---------------------------------------------------------------------------
# 通知対象ユーザー一覧取得
# ---------------------------------------------------------------------------

def fetch_notify_targets_kv() -> "list[dict] | None":
    """
    Cloudflare KV REST API からユーザー別フォロー一覧を直接取得する。
    /api/notify-targets と同等の処理。CF Access を経由しない。
    """
    cf_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    cf_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not cf_api_token or not cf_account_id:
        return None

    user_keys = _list_kv_keys(cf_api_token, cf_account_id, prefix="user:")
    if user_keys is None:
        return None

    targets: list = []
    for key in user_keys:
        hash_ = key[len("user:"):]
        profile = _get_kv_json(cf_api_token, cf_account_id, key)
        if not profile or not profile.get("email"):
            continue
        follow_data = _get_kv_json(cf_api_token, cf_account_id, f"user-talents:{hash_}")
        talent_ids = follow_data.get("talent_ids", []) if follow_data else []
        targets.append({"email": profile["email"], "talent_ids": talent_ids})

    print(f"  KV から通知対象取得: {len(targets)} ユーザー")
    return targets

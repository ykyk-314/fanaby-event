"""
芸人マスタを Cloudflare KV（/api/talents）から取得・更新するヘルパー。
REMIND_API_URL / REMIND_API_SECRET 環境変数を利用する。
各スクリプトから `sys.path` 追加後にインポートして使用する。
"""

import json
import os
import urllib.request


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
    try:
        req = urllib.request.Request(
            f"{api_url}/api/talents",
            headers={"Authorization": f"Bearer {api_secret}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        talents = data.get("talents", [])
        if talents:
            print(f"  KV から芸人マスタ取得: {len(talents)} 件")
            return talents
        print("  KV 芸人マスタが空 — config.json の芸人を使用")
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
        req = urllib.request.Request(
            f"{api_url}/api/talents/{talent_id}",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_secret}",
                "Content-Type": "application/json",
            },
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"  警告: KV 芸人更新失敗 ({talent_id}): {e}")
        return False

"""카카오톡 '나에게 보내기'.
- 출입증(access token, 6시간)은 매번 재발급권(refresh token, 2달)으로 새로 받는다.
- 재발급권 만료가 1달 안으로 다가오면 카카오가 새 재발급권을 준다.
  GH_PAT 시크릿이 있으면 금고(KAKAO_REFRESH_TOKEN)를 자동으로 바꿔 넣고, 없으면 카톡으로 갱신하라고 알린다.
"""
import hashlib
import json
import os
import subprocess
from datetime import date, datetime

import requests

from . import config

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
TEXT_LIMIT = 200  # 텍스트 템플릿 최대 글자 수


def refresh_access_token(state: dict) -> tuple[str, list]:
    """출입증을 새로 받는다. 반환: (access_token, 사용자에게 알릴 경고 목록)"""
    refresh = config.secret("KAKAO_REFRESH_TOKEN")
    data = {
        "grant_type": "refresh_token",
        "client_id": config.secret("KAKAO_REST_API_KEY"),
        "refresh_token": refresh,
    }
    client_secret = config.secret("KAKAO_CLIENT_SECRET", required=False)
    if client_secret:
        data["client_secret"] = client_secret
    r = requests.post(TOKEN_URL, data=data, timeout=20)
    if r.status_code != 200:
        raise SystemExit(f"[오류] 카카오 출입증 재발급 실패 HTTP {r.status_code}: {r.json().get('error_description', r.text[:200])}\n"
                         "→ 재발급권이 만료됐을 수 있습니다. scripts/kakao_get_token.py 로 새로 받아 금고에 넣으세요.")
    tok = r.json()
    warnings = []

    # 재발급권 나이 추적: 원문 대신 짧은 해시만 저장 (되돌릴 수 없음)
    fp = hashlib.sha256(refresh.encode()).hexdigest()[:8]
    info = state.get("kakao_refresh", {})
    if info.get("fp") != fp:
        info = {"fp": fp, "first_seen": datetime.now(config.KST).date().isoformat()}
    state["kakao_refresh"] = info

    new_refresh = tok.get("refresh_token")
    if new_refresh and new_refresh != refresh:
        days = tok.get("refresh_token_expires_in", 0) // 86400
        if _save_secret("KAKAO_REFRESH_TOKEN", new_refresh):
            print(f"[카카오] 새 재발급권을 금고에 자동 저장 (유효 {days}일)")
            state["kakao_refresh"] = {"fp": hashlib.sha256(new_refresh.encode()).hexdigest()[:8],
                                      "first_seen": datetime.now(config.KST).date().isoformat()}
        else:
            warnings.append("🔑 카카오 재발급권이 곧 만료돼요. 이번 주 안에 kakao_get_token.py로 새로 받아 금고에 넣어 주세요.")
    else:
        age = (datetime.now(config.KST).date() - date.fromisoformat(info["first_seen"])).days
        if age >= 50:
            warnings.append(f"🔑 카카오 재발급권 사용 {age}일째 (2달 만료). 곧 갱신이 필요해요.")
    return tok["access_token"], warnings


def _save_secret(name: str, value: str) -> bool:
    """GH_PAT(시크릿 쓰기 권한 토큰)가 있을 때만 금고 값을 교체. 값은 표준입력으로 넘겨 로그에 남지 않게."""
    pat, repo = os.getenv("GH_PAT", "").strip(), os.getenv("GITHUB_REPOSITORY", "")
    if not pat or not repo:
        return False
    try:
        subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value.encode(),
                       env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True, timeout=60)
        return True
    except Exception as e:
        print(f"[경고] 금고 자동 저장 실패: {type(e).__name__}")
        return False


def fit(text: str) -> str:
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"


def send_text(access_token: str, text: str, url: str, button: str | None = None):
    template = {
        "object_type": "text",
        "text": fit(text),
        "link": {"web_url": url, "mobile_web_url": url},
    }
    if button:
        template["button_title"] = button[:14]
    r = requests.post(SEND_URL, headers={"Authorization": f"Bearer {access_token}"},
                      data={"template_object": json.dumps(template, ensure_ascii=False)}, timeout=20)
    if r.status_code != 200 or r.json().get("result_code") != 0:
        raise RuntimeError(f"카톡 전송 실패 HTTP {r.status_code}: {r.text[:200]}")

"""열쇠 점검: 키를 '가려서' 보여주고, 살아 있는지 / 권한 / 오늘 사용량을 확인한다.
GitHub Actions 의 '열쇠 점검' 워크플로에서 실행된다. 키 원문은 절대 출력하지 않는다.
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot import config, storage  # noqa: E402


def line(t=""):
    print(t)


def check_gemini():
    line("■ Gemini API")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    line(f"  키: {config.mask(key)}")
    if not key:
        line("  ✗ GEMINI_API_KEY 시크릿 없음"); return
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=20)
    if r.status_code != 200:
        line(f"  ✗ 키 확인 실패 HTTP {r.status_code}: {r.json().get('error', {}).get('message', '')[:150]}"); return
    names = {m["name"].split("/")[-1] for m in r.json().get("models", [])}
    line(f"  ✓ 키 정상. 사용 가능한 모델 {len(names)}개")
    from bot import gemini
    line(f"  봇이 자동으로 고를 모델: {gemini.pick_models(sorted(names))}")
    state = storage.load_state()
    u = state.get("gemini_usage", {})
    line(f"  오늘 봇 호출 수: {u.get('calls', 0)} / 봇 자체 상한 {config.GEMINI_MAX_CALLS_PER_DAY} (기록일 {u.get('date', '-')})")
    line("  ※ 구글은 API로 남은 한도를 알려주지 않습니다. 정확한 무료 한도(분당/하루 요청 수)는")
    line("    https://aistudio.google.com 에서 [API 키] → 프로젝트의 사용량/Rate limit 화면에서 확인하세요.")
    line("    봇은 하루 2회(평가 1 + 요약 1) 정도만 씁니다.")


def check_kakao():
    line("\n■ 카카오")
    rest = os.getenv("KAKAO_REST_API_KEY", "").strip()
    sec = os.getenv("KAKAO_CLIENT_SECRET", "").strip()
    ref = os.getenv("KAKAO_REFRESH_TOKEN", "").strip()
    line(f"  REST API 키   : {config.mask(rest)}")
    line(f"  Client Secret : {config.mask(sec)}")
    line(f"  재발급권      : {config.mask(ref)}")
    if not (rest and ref):
        line("  ✗ 필수 시크릿 없음"); return
    data = {"grant_type": "refresh_token", "client_id": rest, "refresh_token": ref}
    if sec:
        data["client_secret"] = sec
    r = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=20)
    if r.status_code != 200:
        line(f"  ✗ 재발급권 사용 불가: {r.json().get('error_description', r.text[:150])}"); return
    tok = r.json()
    at = tok["access_token"]
    line(f"  ✓ 출입증 발급 OK — {tok.get('expires_in', 0)//3600}시간 유효")
    if tok.get("refresh_token"):
        line(f"  ! 새 재발급권이 발급됨(만료 1달 이내였음) — 유효 {tok.get('refresh_token_expires_in', 0)//86400}일."
             " 매일 봇 실행 때 GH_PAT가 있으면 자동 저장, 없으면 kakao_get_token.py로 갱신하세요.")
    h = {"Authorization": f"Bearer {at}"}
    info = requests.get("https://kapi.kakao.com/v1/user/access_token_info", headers=h, timeout=20).json()
    line(f"  앱 ID: {info.get('app_id')}  /  남은 시간: {info.get('expires_in', 0)//60}분")
    sc = requests.get("https://kapi.kakao.com/v2/user/scopes", headers=h, timeout=20)
    if sc.status_code == 200:
        for s in sc.json().get("scopes", []):
            if s.get("id") == "talk_message":
                line(f"  {'✓' if s.get('agreed') else '✗'} 권한 talk_message(카톡 메시지 전송) 동의={s.get('agreed')}")
    state = storage.load_state()
    kr = state.get("kakao_refresh", {})
    if kr:
        line(f"  현재 재발급권 처음 사용일: {kr.get('first_seen')} (2달 후 만료)")


def check_github():
    line("\n■ GitHub")
    line(f"  GH_PAT(재발급권 자동 갱신용, 선택): {config.mask(os.getenv('GH_PAT', '').strip())}")


if __name__ == "__main__":
    check_gemini()
    check_kakao()
    check_github()

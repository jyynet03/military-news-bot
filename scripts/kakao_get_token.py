"""[내 컴퓨터에서 직접 실행] 카카오 재발급권(refresh token)을 받아 GitHub 금고에 넣는다.

재발급권은 2달, 출입증은 6시간. 2달마다(또는 봇이 카톡으로 알려줄 때) 이 스크립트를 다시 실행하면 된다.

    python scripts/kakao_get_token.py

준비: 카카오 개발자 콘솔에서
  1) 카카오 로그인 활성화 + Redirect URI 등록 (예: https://localhost:3000/oauth)
  2) 동의항목에서 '카카오톡 메시지 전송(talk_message)' 사용 설정
"""
import getpass
import shutil
import subprocess
import sys
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs

import requests


def mask(v: str) -> str:
    return f"{v[:4]}…{v[-4:]} ({len(v)}자)" if len(v) > 8 else "****"


def main():
    print("== 카카오 재발급권 받기 ==\n입력하는 키는 화면에 보이지 않습니다.\n")
    rest_key = getpass.getpass("REST API 키: ").strip()
    secret = getpass.getpass("Client Secret (사용 안 하면 그냥 Enter): ").strip()
    redirect = input("Redirect URI [https://localhost:3000/oauth]: ").strip() or "https://localhost:3000/oauth"

    url = "https://kauth.kakao.com/oauth/authorize?" + urlencode({
        "client_id": rest_key, "redirect_uri": redirect, "response_type": "code", "scope": "talk_message"})
    print("\n브라우저에서 로그인 + 동의 후, 이동된 주소창의 전체 주소를 복사해 붙여 넣으세요.")
    print("(페이지가 '연결할 수 없음'이어도 정상입니다. 주소창만 복사)\n")
    webbrowser.open(url)
    pasted = input("이동된 주소 또는 code 값: ").strip()
    code = parse_qs(urlparse(pasted).query).get("code", [pasted])[0]

    data = {"grant_type": "authorization_code", "client_id": rest_key, "redirect_uri": redirect, "code": code}
    if secret:
        data["client_secret"] = secret
    r = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=20)
    if r.status_code != 200:
        sys.exit(f"실패: {r.text}")
    tok = r.json()
    refresh = tok["refresh_token"]
    print(f"\n✓ 재발급권 {mask(refresh)} — 유효 {tok.get('refresh_token_expires_in', 0)//86400}일")
    print(f"✓ 권한(scope): {tok.get('scope')}")

    if shutil.which("gh"):
        repo = input("\nGitHub 저장소 (예: myname/military-news-bot, 건너뛰려면 Enter): ").strip()
        if repo:
            for name, value in [("KAKAO_REFRESH_TOKEN", refresh), ("KAKAO_REST_API_KEY", rest_key)] + \
                               ([("KAKAO_CLIENT_SECRET", secret)] if secret else []):
                subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value.encode(), check=True)
                print(f"  금고에 저장: {name}")
            print("완료! 코드나 파일에는 아무 키도 남지 않았습니다.")
            return
    print("\n아래 값을 GitHub > Settings > Secrets and variables > Actions > KAKAO_REFRESH_TOKEN 에 붙여 넣으세요.")
    print("(이 창을 닫으면 사라집니다. 다른 곳에 저장하지 마세요)\n")
    print(refresh)


if __name__ == "__main__":
    main()

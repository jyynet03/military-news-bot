# 🎖️ 장병을 위한 아침 시사 브리핑 봇

매일 아침 **08:50**에 국제 정세·국내 시사 소식을 **카카오톡 1개**로 보냅니다(9시 전에 도착).

```
☀️ 11/12(목) 아침 브리핑

🌏 미중, 관세 휴전 1년 연장
🛡️ 북한, 동해로 미사일 발사
🏛️ 국회, 내년 국방예산 통과
💰 원·달러 환율 1400원 넘어
👥 겨울철 대설 대비 비상근무

📖 오늘의 용어
관세: 수입품에 붙는 세금
            [ 기사 원문 보기 ]
```
버튼을 누르면 **브리핑 페이지**가 열립니다. 기사마다 쉬운 3줄 요약, "왜 중요한지", **원문 링크**가 있습니다.
새 소식이 없는 날에도 "오늘은 새로 알릴 소식이 없어요"가 옵니다.

> 카카오 '나에게 보내기' 텍스트는 **최대 200자**이고 버튼 링크는 하나뿐입니다. 그래서 카톡에는 한 줄 제목만 넣고, 자세한 요약과 기사별 링크는 페이지에 둡니다.

## 어떻게 동작하나

```
GitHub Actions (03:30 / 04:30 / 05:30 / 06:30 / 07:30 KST, 5번 깨움 → 먼저 깬 실행이 08:25까지 대기)
  │
  ├─ 오늘 이미 보냈나? (data/state.json) ── 예 → 종료   ← 하루에 딱 한 번
  │
  ├─ ① 수집: 믿을 수 있는 출처 RSS만 (연합뉴스, BBC 코리아)   bot/news.py
  ├─ ② 코드 1차 거름: 이미 보낸 기사·비슷한 제목·오래된 기사·사진/부고 제거   bot/matcher.py
  ├─ ③ AI 1차(칸 채우기): 분야, 중요도, 군 관련성, 의견/선정성/홍보 여부, 날짜, 주제키   bot/gemini.py
  ├─ ④ 코드 매칭: 규칙으로 탈락시키고 점수 매겨 분야별로 고르게 선택
  ├─ ⑤ AI 2차: 고른 기사만 쉬운 요약 + 날짜를 처음부터 다시 판단
  ├─ ⑥ 날짜 교차 확인: AI 1차 날짜 ↔ AI 2차 날짜 ↔ RSS 발행일 → 안 맞으면 버림
  ├─ ⑦ 카톡 문구(200자) + 브리핑 페이지 생성 → GitHub Pages에 배포   bot/formatter.py
  ├─ ⑧ 08:50까지 기다렸다가 카톡 1개 발송                   bot/kakao.py
  └─ ⑨ 보낸 기사를 data/history.json에 저장 → 저장소에 커밋 (다음 날 중복 방지)
```

**AI는 칸만 채우고, 보낼지는 코드가 정합니다.** 점수 = 2×중요도 + 2×군 관련성 + 3×출처 신뢰도 + 최신성 + 관심 키워드 가산점.
의견·칼럼, 자극적인 기사, 홍보성 기사, 중요도 3 미만, 최근 4일 안에 보낸 사건은 점수와 상관없이 빠집니다.

## 처음 설정 (한 번만)

### 1. GitHub 저장소 만들기
- **Public(공개)** 저장소로 만드세요. 무료 계정은 공개 저장소에서만 GitHub Pages(브리핑 페이지)를 쓸 수 있고, Actions 실행 시간도 무제한입니다.
  공개여도 시크릿(키)은 다른 사람에게 보이지 않습니다. 로그에는 키가 `***`로 가려집니다.
- 이 폴더를 저장소에 올립니다.
- **Settings → Pages → Build and deployment → Source: "GitHub Actions"** 선택 ← *브리핑 페이지*
- **Settings → Actions → General → Workflow permissions → "Read and write permissions"** 선택 후 저장 ← *기억 저장 권한*

### 2. Gemini API 키
1. https://aistudio.google.com → **Get API key** → 키 만들기
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - 이름 `GEMINI_API_KEY` / 값: 키

### 3. 카카오 앱 (https://developers.kakao.com)
1. **내 애플리케이션 → 애플리케이션 추가**
2. **앱 키**에서 **REST API 키** 확인
3. **카카오 로그인 → 활성화 ON**, **Redirect URI**에 `https://localhost:3000/oauth` 등록
4. **동의항목 → 카카오톡 메시지 전송(talk_message)** 사용 설정
5. **플랫폼 → Web → 사이트 도메인**에 아래를 등록 *(등록하지 않으면 버튼 링크가 열리지 않습니다)*
   - `https://<내 GitHub 아이디>.github.io`  ← 버튼이 여는 브리핑 페이지
   - `https://www.yna.co.kr`
   - `https://www.bbc.com`
6. (선택) **보안 → Client Secret** 사용 시 코드 발급 후 활성화

### 4. 카카오 재발급권 받아서 금고에 넣기 (내 컴퓨터에서)
```bash
pip install requests
gh auth login            # GitHub CLI가 있으면 금고에 자동 저장됨
python scripts/kakao_get_token.py
```
→ `KAKAO_REST_API_KEY`, `KAKAO_REFRESH_TOKEN`, (`KAKAO_CLIENT_SECRET`)이 금고에 저장됩니다.

### 5. (선택) 재발급권 자동 갱신 — `GH_PAT`
카카오 재발급권은 **2달** 갑니다. 만료가 1달 안으로 다가오면 카카오가 새 것을 줍니다.
- `GH_PAT`가 **있으면**: 봇이 새 재발급권을 금고에 알아서 바꿔 넣습니다 → 손댈 일 없음
- `GH_PAT`가 **없으면**: 카톡 머리말에 "🔑 재발급권 갱신 필요"가 뜹니다 → 4번을 다시 하면 됩니다

만드는 법: GitHub → Settings → Developer settings → **Fine-grained token** → 이 저장소만 선택 → Permissions에서 **Secrets: Read and write** → 금고에 `GH_PAT`로 저장.

### 6. 시험해 보기
**Actions → 매일 아침 시사 브리핑 → Run workflow** (`force`가 기본으로 켜져 있어 바로 발송)
- `dry_run` 체크 → 카톡을 보내지 않고 로그에 미리보기만 출력
- `force`로 보낸 시험 발송은 "오늘 보냄"으로 치지 않습니다 → 다음 날 아침 예약 발송은 그대로 진행

### 7. 과제 제출 / 확인
1. 오늘: **Run workflow**(workflow_dispatch)로 카톡이 오는지 확인 → 캡처
2. 노트북을 끄고 다음 날 아침: **카카오톡 '나와의 채팅'** + **Actions 탭에서 이벤트가 `schedule`인 실행 기록** 캡처
   - 5번 깨우므로 기록이 여러 개입니다. 처음 출발한 1개가 08:50까지 기다렸다가 보내고(✅, 시간이 깁니다), 나머지는 "오늘 이미 보냄"으로 바로 끝나거나(✅, 1분 미만) 대기 중에 밀려 취소(⊘)됩니다. 정상입니다.
   - '나에게 보내기'는 알림 소리가 나지 않습니다. 직접 채팅방을 열어 확인하세요.

## 금고에 넣는 열쇠

| 시크릿 | 필수 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Gemini API 키 |
| `KAKAO_REST_API_KEY` | ✅ | 카카오 앱 REST API 키 |
| `KAKAO_REFRESH_TOKEN` | ✅ | 카카오 재발급권 (2달) |
| `KAKAO_CLIENT_SECRET` | 선택 | Client Secret을 켰을 때만 |
| `GH_PAT` | 선택 | 재발급권 자동 갱신용 |

코드와 파일에는 키가 하나도 들어 있지 않습니다. 모든 열쇠는 실행할 때 금고에서 꺼내 씁니다.
출입증(access token, 6시간)은 저장하지 않고 매번 새로 받습니다.

## 🔑 키·한도·권한 확인하기
**Actions → 열쇠 점검 → Run workflow** 를 누르면 로그에 다음이 나옵니다.
- 각 키를 **가린 형태**로 표시 (예: `AIza…x9Qk (39자)`)
- Gemini 키가 정상인지, 설정한 모델을 쓸 수 있는지, 오늘 봇이 몇 번 호출했는지
- 카카오 재발급권이 살아 있는지, 출입증 남은 시간, **talk_message 권한 동의 여부**

> 금고에 넣은 값은 GitHub도 다시 보여주지 않습니다(설계상 그렇습니다). 원문은 Google AI Studio / 카카오 개발자 콘솔에서만 볼 수 있습니다.
> Gemini 무료 키의 정확한 남은 한도는 구글이 API로 알려주지 않으므로 **AI Studio의 사용량 화면**에서 확인하세요.

## 무료 한도
- **Gemini**: 하루 2번 호출(평가 1 + 요약 1). 봇 자체 상한은 하루 8번(`GEMINI_MAX_CALLS_PER_DAY`). 분당 한도에 걸리면 20초 쉬고 한 번만 다시 시도하고, 그래도 안 되면 더 가벼운 모델로 넘어갑니다. AI가 완전히 실패한 날은 제목+링크만 보냅니다.
- 모델은 저장소 **Settings → Variables → `GEMINI_MODEL`** 로 바꿀 수 있습니다(기본 `gemini-2.5-flash`).
- **GitHub Actions**: 공개 저장소는 무료·무제한입니다. 하루 약 45분(대부분 08:50까지 기다리는 시간)을 씁니다.

## 바꾸고 싶을 때 — `bot/config.py`
- 발송 시각: `SEND_HOUR`, `SEND_MINUTE` (바꾸면 `.github/workflows/daily-briefing.yml`의 cron도 UTC 기준으로 함께 바꾸세요)
- 기사 수, 분야별 개수: `ARTICLE_COUNT`, `CATEGORY_CAP`
- 뉴스 출처: `FEEDS` (새 도메인은 카카오 플랫폼에도 등록)
- 관심 키워드: `INTEREST_KEYWORDS`

## 알아둘 점
- GitHub 예약 실행은 몇 분~수십 분 늦게 출발할 수 있어서 미리 깨워 둡니다. GitHub 예약은 몇 시간씩 늦을 수 있어(실제로 4시간 40분 지연 확인) 새벽부터 깨웁니다. 그래도 늦으면 12시 전까지는 늦게라도 보내고, 12시가 지나면 보내지 않습니다.
- 공개 저장소는 60일 동안 활동이 없으면 예약 실행이 멈춥니다. Actions 탭에서 가끔 상태를 확인하세요.
- 연합뉴스 RSS에는 "AI 학습 및 활용 금지"라는 문구가 있습니다. 개인용이라도 걱정되면 `FEEDS`에서 연합뉴스를 빼고 다른 출처로 바꾸세요.

## 로컬 테스트
```bash
pip install -r requirements.txt
python -m unittest discover tests          # 매칭·날짜·글자 수 검사
DRY_RUN=1 GEMINI_API_KEY=... python -m bot.main   # 카톡 없이 미리보기
```

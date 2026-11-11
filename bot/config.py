"""설정 모음. 키/토큰은 절대 여기에 적지 않는다 — 전부 환경변수(GitHub Secrets)에서 꺼내 쓴다."""
import os
from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 +9

# ── 언제 보낼까 ─────────────────────────────────────────
SEND_HOUR, SEND_MINUTE = 8, 50   # 08:50 발송 → 9시 전에 도착
LATE_DEADLINE_HOUR = 11          # 이 시각 이후 자동 실행이면 보내지 않음 (수동 실행은 예외)

# ── 몇 개 보낼까 ────────────────────────────────────────
ARTICLE_COUNT = 5
# 분야별 최대 개수 (한쪽으로 쏠리지 않게)
CATEGORY_CAP = {"국제정세": 2, "북한·안보": 2, "국내정치": 1, "경제": 1, "사회": 1, "기타": 0}
MIN_IMPORTANCE = 3               # AI 중요도 1~5 중 이 값 미만은 탈락
MAX_AGE_HOURS = 30               # 이보다 오래된 기사는 후보에서 제외
STAGE1_MAX_CANDIDATES = 45       # AI 1차 평가에 넘길 최대 기사 수
STAGE2_PICK_POOL = 9             # AI 2차(요약+날짜 재확인)에 넘길 기사 수

# ── 기억(중복 방지) ─────────────────────────────────────
HISTORY_KEEP_DAYS = 21           # 보낸 기사 기록 보관 기간
DUP_LOOKBACK_DAYS = 4            # 이 기간 안에 보낸 비슷한 주제는 다시 안 보냄
TITLE_SIMILARITY = 0.72          # 제목 유사도 기준 (0~1)

# ── Gemini 무료 한도 보호 ───────────────────────────────
# 정상이면 하루 2번(1차 평가 1 + 2차 요약 1).
# 상한 8 = 2단계 × 모델 2개 × 시도 2번 (실패·재시도가 최악으로 겹쳐도 이 이상은 안 씀)
GEMINI_MAX_CALLS_PER_DAY = int(os.getenv("GEMINI_MAX_CALLS_PER_DAY", "8"))
GEMINI_MODELS = [m for m in [
    os.getenv("GEMINI_MODEL", "").strip(),   # GitHub Variables 로 바꿀 수 있음
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
] if m]

# ── 믿을 수 있는 뉴스 출처 (화이트리스트) ───────────────
# trust: 출처 신뢰 가중치. domain: 링크가 이 도메인일 때만 통과.
# ※ 카카오 개발자 콘솔 [앱 > 플랫폼 > Web 사이트 도메인]에 각 domain 을 등록해야 링크가 열린다.
FEEDS = [
    {"name": "연합뉴스", "url": "https://www.yna.co.kr/rss/northkorea.xml", "trust": 1.0, "domain": "www.yna.co.kr"},
    {"name": "연합뉴스", "url": "https://www.yna.co.kr/rss/international.xml", "trust": 1.0, "domain": "www.yna.co.kr"},
    {"name": "연합뉴스", "url": "https://www.yna.co.kr/rss/politics.xml", "trust": 1.0, "domain": "www.yna.co.kr"},
    {"name": "연합뉴스", "url": "https://www.yna.co.kr/rss/economy.xml", "trust": 0.9, "domain": "www.yna.co.kr"},
    {"name": "연합뉴스", "url": "https://www.yna.co.kr/rss/society.xml", "trust": 0.85, "domain": "www.yna.co.kr"},
    {"name": "BBC 코리아", "url": "https://feeds.bbci.co.uk/korean/rss.xml", "trust": 0.95, "domain": "www.bbc.com"},
]
HOME_LINK = "https://www.yna.co.kr"  # 머리말 메시지 링크

# 군인에게 특히 중요한 키워드 (코드가 가산점을 준다)
INTEREST_KEYWORDS = [
    "북한", "미사일", "핵", "국방", "합참", "안보", "동맹", "한미", "주한미군", "전쟁", "휴전",
    "우크라이나", "러시아", "중국", "대만", "일본", "나토", "NATO", "유엔", "제재", "외교",
    "정상회담", "병역", "장병", "군", "방산", "사이버", "테러", "중동", "이란", "이스라엘",
]

# ── 경로 / 실행 옵션 ────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SITE_DIR = os.path.join(ROOT, "docs")   # 브리핑 페이지 (GitHub Pages)
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
STATE_PATH = os.path.join(DATA_DIR, "state.json")


def flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


FORCE = flag("FORCE")        # 오늘 이미 보냈어도 / 시간 상관없이 바로 보냄
DRY_RUN = flag("DRY_RUN")    # 카톡 대신 화면에만 출력, 기억도 저장 안 함
NO_WAIT = flag("NO_WAIT")    # 08:50까지 기다리지 않고 바로 보냄


def secret(name: str, required: bool = True) -> str:
    """금고(GitHub Secrets → 환경변수)에서 열쇠를 꺼낸다."""
    value = os.getenv(name, "").strip()
    if required and not value:
        raise SystemExit(f"[오류] 시크릿 {name} 이(가) 없습니다. GitHub > Settings > Secrets 에 등록하세요.")
    return value


def mask(value: str) -> str:
    """키를 남에게 보이지 않게 가린다. 예: AIza…x9Qk (39자)"""
    if not value:
        return "(없음)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]} ({len(value)}자)"

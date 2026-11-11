"""매칭 로직: '나한테 필요한 정보'를 코드가 고른다.
AI 가 채운 칸(중요도, 군 관련성, 신뢰 경고, 날짜, 주제키)을 규칙과 점수로 판정한다.
"""
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from . import config

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _similar(a: str, b: str) -> float:
    strip = lambda s: re.sub(r"[\s\"'“”‘’\[\]()…·,.!?]", "", s)
    return SequenceMatcher(None, strip(a), strip(b)).ratio()


# ── 1단계: AI 호출 전, 코드만으로 거르기 ─────────────────────
def prefilter(items: list, history: list, now: datetime) -> list:
    sent_urls = {h["url"] for h in history}
    recent_titles = [h["title"] for h in history
                     if h["date"] >= (now.date() - timedelta(days=config.DUP_LOOKBACK_DAYS)).isoformat()]
    oldest = now - timedelta(hours=config.MAX_AGE_HOURS)
    out = []
    for a in items:
        if a["url"] in sent_urls:
            continue                                   # 전에 보낸 기사
        if a["published"] and not (oldest <= a["published"] <= now + timedelta(minutes=10)):
            continue                                   # 너무 오래됐거나 미래 날짜
        if len(a["title"]) < 8 or re.search(r"\[(포토|사진|영상|그래픽|부고|인사|게시판|오늘의 운세)", a["title"]):
            continue                                   # 사진·부고·인사 같은 비기사
        if any(_similar(a["title"], t) >= config.TITLE_SIMILARITY for t in recent_titles):
            continue                                   # 최근 보낸 것과 거의 같은 제목
        out.append(a)
    # 같은 배치 안에서 거의 같은 제목은 하나만 (신뢰도 높은 출처 우선)
    out.sort(key=lambda a: (-a["trust"], -(a["published"].timestamp() if a["published"] else 0)))
    uniq = []
    for a in out:
        if not any(_similar(a["title"], u["title"]) >= config.TITLE_SIMILARITY for u in uniq):
            uniq.append(a)
    # 관심 키워드가 있는 기사를 앞으로 → AI 평가 대상 상한 안에 들도록
    uniq.sort(key=lambda a: (-_keyword_bonus(a), -(a["published"].timestamp() if a["published"] else 0)))
    picked = uniq[: config.STAGE1_MAX_CANDIDATES]
    print(f"[1차 거름] {len(items)} → {len(picked)}건")
    return picked


def _keyword_bonus(a: dict) -> float:
    text = a["title"] + " " + a["description"]
    hits = sum(1 for k in config.INTEREST_KEYWORDS if k in text)
    return min(hits * 0.5, 1.5)


# ── 날짜 교차 확인 ────────────────────────────────────────
def _parse(d: str):
    if not d or not _DATE.match(d):
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None


def check_date(ai_date: str, published, today: date):
    """AI가 뽑은 날짜를 RSS 발행일(기계가 준 값)과 대조한다.
    반환: (통과 여부, 이유). 메시지에 표시하는 날짜는 언제나 RSS 발행일을 쓴다."""
    d = _parse(ai_date)
    pub = published.date() if published else None
    if d is None:
        return (pub is not None, "AI 날짜 없음 → 발행일 사용" if pub else "날짜 확인 불가")
    if d > today + timedelta(days=60):
        return (False, f"AI 날짜 {d} 비정상(먼 미래)")
    if pub and d < pub - timedelta(days=3):
        return (False, f"사건일 {d} 이 발행일 {pub} 보다 3일 이상 과거 → 재탕 기사")
    if not pub and abs((d - today).days) > 2:
        return (False, f"발행일 없음 + AI 날짜 {d} 가 오늘과 동떨어짐")
    return (True, "날짜 일치")


def cross_check(first: str, second: str, published, today: date):
    """1차·2차 AI 날짜와 발행일을 교차 확인."""
    ok1, why1 = check_date(first, published, today)
    ok2, why2 = check_date(second, published, today)
    if not (ok1 and ok2):
        return False, why1 if not ok1 else why2
    d1, d2 = _parse(first), _parse(second)
    if d1 and d2 and abs((d1 - d2).days) > 1:
        return False, f"AI 두 번 판단한 날짜가 다름({d1} vs {d2})"
    return True, "교차 확인 통과"


# ── 2단계: AI 평가 결과로 점수 매기고 고르기 ───────────────
def score(a: dict, now: datetime) -> float:
    ai = a["ai"]
    age_h = (now - a["published"]).total_seconds() / 3600 if a["published"] else config.MAX_AGE_HOURS
    recency = max(0.0, 1 - age_h / config.MAX_AGE_HOURS)
    return (2.0 * ai["importance"] + 2.0 * ai["military_relevance"]
            + 3.0 * a["trust"] + 1.0 * recency + _keyword_bonus(a))


def rank(cands: list, ai_rows: dict, history: list, now: datetime) -> list:
    recent_keys = [h.get("topic_key", "") for h in history
                   if h["date"] >= (now.date() - timedelta(days=config.DUP_LOOKBACK_DAYS)).isoformat()]
    passed = []
    for a in cands:
        ai = ai_rows.get(a["id"])
        if not ai:
            continue
        reason = None
        if ai.get("is_opinion") or ai.get("is_sensational") or ai.get("is_ad_or_pr"):
            reason = "의견/선정/홍보성"
        elif int(ai.get("importance", 0)) < config.MIN_IMPORTANCE:
            reason = "중요도 낮음"
        elif ai.get("repeats_recent"):
            reason = "최근 보낸 사건과 같음(AI)"
        elif ai.get("topic_key") and any(k and _similar(ai["topic_key"], k) >= 0.8 for k in recent_keys):
            reason = "최근 보낸 주제키와 같음"
        else:
            ok, why = check_date(ai.get("event_date", ""), a["published"], now.date())
            if not ok:
                reason = why
        if reason:
            print(f"  ✗ {a['title'][:40]} — {reason}")
            continue
        a = dict(a, ai=ai, topic_key=ai.get("topic_key", ""))
        a["score"] = score(a, now)
        passed.append(a)
    passed.sort(key=lambda x: -x["score"])
    return passed


def select(ranked: list, n: int) -> list:
    """분야별 상한을 지키며 점수순으로 n개. 같은 주제키는 하나만."""
    chosen, per_cat, keys = [], {}, []
    for a in ranked:
        cat = a["ai"]["category"]
        if per_cat.get(cat, 0) >= config.CATEGORY_CAP.get(cat, 1):
            continue
        if a["topic_key"] and any(_similar(a["topic_key"], k) >= 0.8 for k in keys):
            continue
        chosen.append(a)
        per_cat[cat] = per_cat.get(cat, 0) + 1
        keys.append(a["topic_key"])
        if len(chosen) >= n:
            break
    return chosen

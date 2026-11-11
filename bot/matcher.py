"""매칭 로직: '나한테 필요한 정보'를 코드가 고른다.
AI 가 채운 칸(중요도, 군 관련성, 신뢰 경고, 날짜, 주제키)을 규칙과 점수로 판정한다.

흐름
  1) prefilter : AI 호출 전 코드만으로 거름 (보낸 기사, 오래된 기사, 의견·사진 꼬리표, 같은 제목)
                 + 피드(분야)별 할당량 → 안보 기사가 후보를 독차지하지 못하게
  2) rank      : AI 칸으로 탈락 규칙 적용 후 점수
  3) select    : 분야별 상한 + 국제/국내 최소 보장 + 같은 사건은 하나만
"""
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from . import config

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KEYWORDS = [re.compile(k) for k in config.INTEREST_KEYWORDS]
_OPINION = re.compile(config.OPINION_TAGS)
_NOISE = re.compile(r"[\s\"'“”‘’\[\]()…·,.!?_\-]|\((종합|[0-9]보|속보|1보|2보|3보)\)")


def _norm(s: str) -> str:
    return _NOISE.sub("", s or "")


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _same_topic(k1: str, k2: str) -> bool:
    """주제키는 '정확히 같을 때만' 같은 사건으로 본다.
    (유사도로 비교하면 '한미_국방장관회담'과 '한미_외교장관회담'처럼 다른 사건을 잘못 합침.
     표현만 다른 같은 사건은 AI의 repeats_recent 칸이 잡는다.)"""
    return bool(k1) and bool(k2) and _norm(k1) == _norm(k2)


def _ts(a):
    return a["published"].timestamp() if a.get("published") else 0


def keyword_bonus(a: dict) -> float:
    text = a["title"] + " " + a.get("description", "")
    hits = sum(1 for k in _KEYWORDS if k.search(text))
    return min(hits * 0.25, 0.75)


_keyword_bonus = keyword_bonus  # 예전 이름 호환


# ── 1단계: AI 호출 전, 코드만으로 거르기 ─────────────────────
def prefilter(items: list, history: list, now: datetime) -> list:
    sent_urls = {h["url"] for h in history}
    since = (now.date() - timedelta(days=config.DUP_LOOKBACK_DAYS)).isoformat()
    recent_titles = [h["title"] for h in history if h["date"] >= since]
    oldest = now - timedelta(hours=config.MAX_AGE_HOURS)
    out = []
    for a in items:
        if a["url"] in sent_urls:
            continue                                   # 전에 보낸 기사
        if a["published"] and not (oldest <= a["published"] <= now + timedelta(minutes=10)):
            continue                                   # 너무 오래됐거나 미래 날짜
        if len(a["title"]) < 8 or _OPINION.search(a["title"]):
            continue                                   # 의견·사진·부고·인사 등
        if any(_similar(a["title"], t) >= config.TITLE_SIMILARITY for t in recent_titles):
            continue                                   # 최근 보낸 것과 거의 같은 제목
        out.append(a)

    # 같은 배치 안에서 거의 같은 제목((종합)·(2보) 같은 갱신판 포함)은 하나만: 최신판 우선
    out.sort(key=lambda a: (-a["trust"], -_ts(a)))
    uniq = []
    for a in out:
        if not any(_similar(a["title"], u["title"]) >= config.TITLE_SIMILARITY for u in uniq):
            uniq.append(a)

    # 피드(분야)별 할당량: 각 피드에서 키워드·최신순으로 quota 개까지
    by_feed = {}
    for a in uniq:
        by_feed.setdefault(a.get("feed", ""), []).append(a)
    picked = []
    for feed_items in by_feed.values():
        # 절반은 관심 키워드 순, 나머지 절반은 최신순 → 키워드 없는 큰 사건(재난 등)도 AI가 볼 수 있게
        quota = feed_items[0].get("quota", 8)
        by_kw = sorted(feed_items, key=lambda a: (-keyword_bonus(a), -_ts(a)))[: (quota + 1) // 2]
        rest = sorted((a for a in feed_items if a not in by_kw), key=lambda a: -_ts(a))
        picked += by_kw + rest[: quota - len(by_kw)]
    picked.sort(key=lambda a: -_ts(a))
    picked = picked[: config.STAGE1_MAX_CANDIDATES]
    print(f"[1차 거름] {len(items)} → {len(picked)}건 (피드 {len(by_feed)}곳에서 고르게)")
    return picked


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
    if ai_date and d is None:
        return (False, f"AI 날짜 형식 오류({ai_date})")
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
    """중요도(국민으로서) 와 군 관련성(군인으로서) 을 같은 무게로.
    키워드는 AI 판단과 겹치므로 동점일 때 순서를 가르는 정도(최대 0.75)만."""
    ai = a["ai"]
    age_h = (now - a["published"]).total_seconds() / 3600 if a["published"] else config.MAX_AGE_HOURS
    recency = max(0.0, 1 - age_h / config.MAX_AGE_HOURS)
    return (2.0 * ai["importance"] + 2.0 * ai["military_relevance"]
            + 3.0 * a["trust"] + 1.0 * recency + keyword_bonus(a))


def _clamp(v, lo=1, hi=5):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def rank(cands: list, ai_rows: dict, history: list, now: datetime) -> list:
    since = (now.date() - timedelta(days=config.DUP_LOOKBACK_DAYS)).isoformat()
    recent_keys = [h.get("topic_key", "") for h in history if h["date"] >= since]
    passed = []
    for a in cands:
        ai = ai_rows.get(a["id"])
        if not ai:
            continue
        ai = dict(ai, importance=_clamp(ai.get("importance")),            # AI가 범위 밖 숫자를 줘도 안전하게
                  military_relevance=_clamp(ai.get("military_relevance")),
                  category=ai.get("category") if ai.get("category") in config.CATEGORY_CAP else "기타")
        reason = None
        if ai.get("is_opinion") or ai.get("is_sensational") or ai.get("is_ad_or_pr"):
            reason = "의견/선정/홍보성"
        elif ai["importance"] < config.MIN_IMPORTANCE:
            reason = "중요도 낮음"
        elif ai.get("repeats_recent"):
            reason = "최근 보낸 사건과 같음(AI)"
        elif any(_same_topic(ai.get("topic_key", ""), k) for k in recent_keys):
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


def _group(cat: str):
    for g, cats in config.GROUPS.items():
        if cat in cats:
            return g
    return None


def select(ranked: list, n: int, caps: dict | None = None) -> list:
    """점수순으로 n개. ① 국제/국내 최소 개수를 먼저 채우고 ② 나머지를 점수순으로.
    분야별 상한을 지키고, 같은 주제키는 하나만."""
    caps = caps or config.CATEGORY_CAP
    chosen, per_cat = [], {}

    def ok(a):
        cat = a["ai"]["category"]
        return (a not in chosen
                and per_cat.get(cat, 0) < caps.get(cat, 1)
                and not any(_same_topic(a["topic_key"], c["topic_key"]) for c in chosen))

    def take(a):
        chosen.append(a)
        per_cat[a["ai"]["category"]] = per_cat.get(a["ai"]["category"], 0) + 1

    for g, need in config.GROUP_MIN.items():          # ① 최소 보장
        got = sum(1 for c in chosen if _group(c["ai"]["category"]) == g)
        for a in ranked:
            if got >= need or len(chosen) >= n:
                break
            if _group(a["ai"]["category"]) == g and ok(a):
                take(a)
                got += 1
    for a in ranked:                                  # ② 나머지 점수순
        if len(chosen) >= n:
            break
        if ok(a):
            take(a)
    chosen.sort(key=lambda x: -x["score"])
    return chosen


def pool_caps() -> dict:
    """AI 2차로 넘길 여유분은 분야 상한을 1씩 늘려서 (날짜 확인에서 떨어질 것 대비)."""
    return {k: v + 1 for k, v in config.CATEGORY_CAP.items()}

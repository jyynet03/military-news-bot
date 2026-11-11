"""Gemini 는 '칸 채우기'만 한다. 보낼지 말지는 matcher.py(코드)가 정한다.

1차(평가): 후보 전체에 대해 분야/중요도/군 관련성/신뢰 경고/날짜/주제키/중복여부 칸을 채움.
2차(작성): 코드가 고른 기사만 쉬운 요약을 쓰고, 날짜를 '처음부터 다시' 뽑음 → 코드가 1차와 교차 확인.
하루 호출 수를 state.json 에 세어서 무료 한도를 넘지 않게 막는다.
"""
import json
import time

import requests

from . import config

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CATEGORIES = ["국제정세", "북한·안보", "국내정치", "경제", "사회", "기타"]


class QuotaGuard:
    """하루 호출 수 상한. 무료 키는 하루 쓸 양이 정해져 있다."""

    def __init__(self, state: dict, today: str):
        self.state = state
        usage = state.get("gemini_usage", {})
        if usage.get("date") != today:
            usage = {"date": today, "calls": 0}
        state["gemini_usage"] = usage
        self.usage = usage

    def take(self):
        if self.usage["calls"] >= config.GEMINI_MAX_CALLS_PER_DAY:
            raise RuntimeError(f"오늘 Gemini 호출 상한({config.GEMINI_MAX_CALLS_PER_DAY}회)에 도달")
        self.usage["calls"] += 1


def _call(prompt: str, schema: dict, guard: QuotaGuard) -> list:
    key = config.secret("GEMINI_API_KEY")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "maxOutputTokens": 16384,
        },
    }
    last_err = None
    for model in config.GEMINI_MODELS:
        for attempt in range(2):
            guard.take()
            try:
                r = requests.post(API.format(model=model), json=body, timeout=120,
                                  headers={"x-goog-api-key": key})  # 키는 URL 이 아니라 헤더로 → 로그에 안 남음
            except requests.RequestException as e:
                last_err = e
                continue
            if r.status_code == 200:
                data = r.json()
                text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
                print(f"[Gemini] {model} 성공 (오늘 {guard.usage['calls']}회째)")
                return json.loads(text)
            last_err = f"{model} HTTP {r.status_code}: {r.text[:200]}"
            print(f"[Gemini] 실패 {last_err}")
            if r.status_code == 429 and attempt == 0:
                time.sleep(20)          # 분당 한도 → 잠깐 쉬고 한 번만 재시도
                continue
            break                        # 404(모델 없음) 등 → 다음 모델로
    raise RuntimeError(f"Gemini 호출 실패: {last_err}")


SYSTEM = """너는 대한민국 장병을 위한 아침 시사 브리핑 편집자다.
독자는 기사를 거의 읽지 않고 난독증이 있는 젊은 군인이다.
원칙:
- 사실만. 추측, 과장, 정치적 편들기 금지. 기사에 없는 내용을 지어내지 마라.
- 의견/칼럼/사설, 자극적·선정적 기사, 광고·홍보성 기사는 정확히 표시하라.
- 날짜는 기사 본문(제목·요약)에 근거해서만 적어라. 모르면 빈 문자열.
"""

STAGE1_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "category": {"type": "STRING", "enum": CATEGORIES},
            "importance": {"type": "INTEGER", "description": "한국인이 오늘 알아야 할 정도 1~5"},
            "military_relevance": {"type": "INTEGER", "description": "대한민국 군인의 안보·국가관 역량에 도움 1~5"},
            "is_opinion": {"type": "BOOLEAN"},
            "is_sensational": {"type": "BOOLEAN"},
            "is_ad_or_pr": {"type": "BOOLEAN"},
            "event_date": {"type": "STRING", "description": "사건이 일어난 날짜 YYYY-MM-DD, 모르면 빈 문자열"},
            "topic_key": {"type": "STRING", "description": "같은 사건이면 같은 값이 되도록 '주체_사건' 형태 2~4단어. 예: 북한_ICBM발사"},
            "repeats_recent": {"type": "BOOLEAN", "description": "최근 보낸 목록과 사실상 같은 사건이면 true"},
        },
        "required": ["id", "category", "importance", "military_relevance", "is_opinion",
                     "is_sensational", "is_ad_or_pr", "event_date", "topic_key", "repeats_recent"],
    },
}

STAGE2_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "easy_title": {"type": "STRING", "description": "쉬운 말 한 줄 제목, 18자 이내. 이것만 읽어도 무슨 일인지 알 수 있게"},
            "easy_points": {"type": "ARRAY", "items": {"type": "STRING"},
                            "description": "핵심 3줄. 각 30자 이내의 짧은 문장. 어려운 한자어 대신 쉬운 말."},
            "why_it_matters": {"type": "STRING", "description": "군인·국민에게 왜 중요한지 한 문장, 35자 이내"},
            "term": {"type": "STRING", "description": "기사 속 어려운 용어 하나(없으면 빈 문자열)"},
            "term_explain": {"type": "STRING", "description": "그 용어 풀이 30자 이내"},
            "event_date_check": {"type": "STRING", "description": "사건 날짜 YYYY-MM-DD를 기사 내용만 보고 다시 판단. 모르면 빈 문자열"},
        },
        "required": ["id", "easy_title", "easy_points", "why_it_matters", "term", "term_explain", "event_date_check"],
    },
}


def _fmt_item(a: dict, desc_limit: int) -> dict:
    return {
        "id": a["id"],
        "source": a["source"],
        "published": a["published"].strftime("%Y-%m-%d %H:%M") if a["published"] else "",
        "title": a["title"],
        "description": a["description"][:desc_limit],
    }


def stage1_classify(cands: list, recent_sent: list, today: str, guard: QuotaGuard) -> dict:
    payload = {
        "today_kst": today,
        "recently_sent": [h["title"] for h in recent_sent][-25:],
        "articles": [_fmt_item(a, 160) for a in cands],
    }
    prompt = ("아래 기사 각각에 대해 칸을 채워라. 모든 id에 대해 하나씩 답하라.\n"
              + json.dumps(payload, ensure_ascii=False))
    rows = _call(prompt, STAGE1_SCHEMA, guard)
    return {r["id"]: r for r in rows if isinstance(r, dict) and "id" in r}


def stage2_write(picks: list, today: str, guard: QuotaGuard) -> dict:
    payload = {"today_kst": today, "articles": [_fmt_item(a, 400) for a in picks]}
    prompt = ("난독증이 있고 기사를 잘 안 읽는 군인이 10초 안에 이해하도록 써라. "
              "짧은 문장, 쉬운 단어, 숫자는 꼭 필요한 것만. 기사에 없는 내용은 쓰지 마라. "
              "event_date_check 는 앞선 판단을 참고하지 말고 기사 내용만 보고 새로 정하라.\n"
              + json.dumps(payload, ensure_ascii=False))
    rows = _call(prompt, STAGE2_SCHEMA, guard)
    return {r["id"]: r for r in rows if isinstance(r, dict) and "id" in r}

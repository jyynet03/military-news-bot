"""하루 한 번 아침 브리핑.  python -m bot.main prepare  →  (페이지 배포)  →  python -m bot.main send

GitHub Actions 가 08:10~08:46(KST) 사이에 5번 깨운다(깃허브 예약은 늦게 출발할 때가 많아서).
- prepare: 기사 수집 → AI 칸 채우기 → 코드 매칭 → 날짜 교차 확인 → 카톡 문구 + 브리핑 페이지 생성
- send   : 08:50까지 기다렸다가 카톡 1개 발송 → 보낸 기사 기억
- 오늘 이미 보냈으면(state.json) 나머지 실행은 바로 끝난다 → 하루에 딱 한 번.
- 새 소식이 없는 날에도 '오늘은 새로 알릴 소식이 없어요' 를 보낸다.
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime

from . import config, formatter, gemini, kakao, matcher, news, storage

PENDING = os.path.join(config.ROOT, ".cache", "pending.json")


def _set_output(key, value):
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def should_skip(now, state) -> str | None:
    if config.FORCE or config.DRY_RUN:
        return None
    if state.get("last_sent_date") == now.date().isoformat():
        return f"오늘 이미 {state.get('last_sent_at')}에 보냈습니다."
    if now.hour >= config.LATE_DEADLINE_HOUR:
        return f"{config.LATE_DEADLINE_HOUR}시가 지나 자동 발송하지 않습니다. (수동 실행 시 force 사용)"
    return None


def prepare():
    now = datetime.now(config.KST)
    today = now.date().isoformat()
    state, history = storage.load_state(), storage.load_history()
    reason = should_skip(now, state)
    if reason:
        print(f"[건너뜀] {reason}")
        _set_output("skip", "true")
        if os.path.exists(PENDING):
            os.remove(PENDING)
        return
    _set_output("skip", "false")

    items = news.fetch_all()
    cands = matcher.prefilter(items, history, now)
    guard = gemini.QuotaGuard(state, today)
    recent_sent = storage.recent(history, today, config.DUP_LOOKBACK_DAYS)

    picks, warnings = [], []
    try:
        if cands:
            rows1 = gemini.stage1_classify(cands, recent_sent, today, guard)
            ranked = matcher.rank(cands, rows1, history, now)
            pool = matcher.select(ranked, config.STAGE2_PICK_POOL, matcher.pool_caps())
            rows2 = gemini.stage2_write(pool, today, guard) if pool else {}
            verified = []
            for a in pool:
                w = rows2.get(a["id"])
                if not w or not w.get("easy_title") or not w.get("easy_points"):
                    continue
                ok, why = matcher.cross_check(a["ai"].get("event_date", ""), w.get("event_date_check", ""),
                                              a["published"], now.date())
                print(f"  {'✓' if ok else '✗'} 날짜 {why}: {a['title'][:40]}")
                if ok:
                    verified.append(dict(a, write=w))
            picks = matcher.select(verified, config.ARTICLE_COUNT)
    except Exception as e:
        print(f"[경고] AI 단계 실패 → 제목만 보냅니다: {e}")
        traceback.print_exc()
        warnings.append("⚠️ 오늘은 AI 요약이 안 돼서 원래 제목만 보여요.")
        picks = sorted(cands, key=lambda a: (-a["trust"], -matcher.keyword_bonus(a)))[: config.ARTICLE_COUNT]

    if not config.DRY_RUN:
        storage.save_state(state)   # AI 호출 횟수는 실패해도 기록 (무료 한도 보호)

    for a in picks:   # JSON 저장용
        a["published"] = a["published"].isoformat() if a.get("published") else ""
    text = formatter.kakao_message(now, picks)

    # 브리핑 페이지 (GitHub Pages 로 배포됨)
    os.makedirs(config.SITE_DIR, exist_ok=True)
    page = formatter.page_html(now, picks, warnings)
    for name in (f"{today}.html", "index.html"):
        with open(os.path.join(config.SITE_DIR, name), "w", encoding="utf-8") as f:
            f.write(page)

    os.makedirs(os.path.dirname(PENDING), exist_ok=True)
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump({"date": today, "text": text, "picks": picks}, f, ensure_ascii=False, indent=2)

    print(f"\n[카톡 미리보기] {len(text)}자\n{'─' * 30}\n{text}\n{'─' * 30}\n  [기사 원문 보기] 버튼")


def send():
    now = datetime.now(config.KST)
    state, history = storage.load_state(), storage.load_history()
    reason = should_skip(now, state)
    if reason:
        print(f"[건너뜀] {reason}")
        return
    with open(PENDING, encoding="utf-8") as f:
        p = json.load(f)
    today, picks = p["date"], p["picks"]

    # 버튼 링크: 브리핑 페이지가 배포됐으면 그 페이지, 아니면 1번 기사(없으면 뉴스 홈)
    page_url = os.getenv("PAGE_URL", "").strip()
    if page_url:
        link = page_url.rstrip("/") + f"/{today}.html"
    else:
        link = picks[0]["url"] if picks else config.HOME_LINK
        print("[안내] 브리핑 페이지 주소(PAGE_URL)가 없어 1번 기사로 연결합니다.")
    button = "기사 원문 보기" if picks else "뉴스 보러 가기"

    if config.DRY_RUN:
        print(f"[DRY_RUN] 보내지 않음. 버튼 → {link}")
        return

    token, warnings = kakao.refresh_access_token(state)   # 실패하면 여기서 멈추고 Actions 가 실패 메일을 보냄

    wait = (now.replace(hour=config.SEND_HOUR, minute=config.SEND_MINUTE, second=0, microsecond=0)
            - datetime.now(config.KST)).total_seconds()
    if wait > 0 and not config.FORCE and not config.NO_WAIT:
        print(f"[대기] {config.SEND_HOUR:02d}:{config.SEND_MINUTE:02d}까지 {int(wait)}초 기다립니다.")
        time.sleep(wait)

    kakao.send_text(token, p["text"], link, button)
    for w in warnings:   # 재발급권 만료 같은 관리 알림만 따로 (드묾)
        kakao.send_text(token, w, config.HOME_LINK)
    sent_at = datetime.now(config.KST)
    print(f"[완료] {sent_at:%H:%M:%S} 카톡 발송 ({len(picks)}개 기사)")

    if not config.FORCE:   # 수동 force 시험 발송은 '오늘 보냄'으로 치지 않음 → 예약 발송은 그대로 진행
        state["last_sent_date"] = sent_at.date().isoformat()
        state["last_sent_at"] = sent_at.strftime("%H:%M:%S")
    storage.add_to_history(history, picks, today)
    storage.save_state(state)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("prepare", "all"):
        prepare()
    if cmd in ("send", "all") and os.path.exists(PENDING):
        send()

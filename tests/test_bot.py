"""네트워크 없이 매칭/날짜확인/메시지 길이를 검사.  python -m unittest discover tests"""
import unittest
from datetime import datetime, timedelta

from bot import config, formatter, matcher

NOW = datetime(2026, 11, 12, 8, 30, tzinfo=config.KST)


def art(i, title, hours_ago=3, trust=1.0):
    return {"id": f"a{i}", "url": f"https://www.yna.co.kr/view/{i}", "title": title,
            "description": "설명", "published": NOW - timedelta(hours=hours_ago), "source": "연합뉴스", "trust": trust}


def ai(i, cat="국제정세", imp=4, rel=4, date="2026-11-12", key=None, **flags):
    row = {"id": f"a{i}", "category": cat, "importance": imp, "military_relevance": rel,
           "is_opinion": False, "is_sensational": False, "is_ad_or_pr": False,
           "event_date": date, "topic_key": key or f"주제{i}", "repeats_recent": False}
    row.update(flags)
    return row


class T(unittest.TestCase):
    def test_prefilter_drops_sent_old_and_similar(self):
        items = [art(1, "북한, 동해상으로 탄도미사일 발사"), art(2, "오래된 기사 제목입니다", hours_ago=50),
                 art(3, "[포토] 행사 사진 모음"), art(4, "북한 동해상으로 탄도미사일 발사…합참")]
        history = [{"date": "2026-11-11", "url": "https://www.yna.co.kr/view/9", "title": "x", "topic_key": ""}]
        out = matcher.prefilter(items, history, NOW)
        self.assertEqual([a["id"] for a in out], ["a1"])  # a4는 a1과 거의 같은 제목

    def test_prefilter_drops_yesterday_title(self):
        history = [{"date": "2026-11-11", "url": "u", "title": "한미 국방장관 회담 개최", "topic_key": ""}]
        self.assertEqual(matcher.prefilter([art(1, "한미 국방장관 회담 개최")], history, NOW), [])

    def test_rank_hard_filters(self):
        cands = [art(i, f"기사 제목 번호 {i} 입니다") for i in range(1, 7)]
        rows = {r["id"]: r for r in [ai(1), ai(2, is_opinion=True), ai(3, imp=2), ai(4, repeats_recent=True),
                                     ai(5, date="2026-10-01"), ai(6, key="북한_미사일발사")]}
        history = [{"date": "2026-11-11", "url": "u", "title": "t", "topic_key": "북한_미사일발사"}]
        self.assertEqual([a["id"] for a in matcher.rank(cands, rows, history, NOW)], ["a1"])

    def test_select_caps(self):
        cands = [art(i, f"기사 제목 번호 {i} 입니다") for i in range(1, 6)]
        rows = {f"a{i}": ai(i, cat="국제정세") for i in range(1, 6)}
        picked = matcher.select(matcher.rank(cands, rows, [], NOW), 5)
        self.assertEqual(len(picked), config.CATEGORY_CAP["국제정세"])

    def test_cross_check(self):
        pub = NOW - timedelta(hours=2)
        self.assertTrue(matcher.cross_check("2026-11-12", "2026-11-11", pub, NOW.date())[0])
        self.assertFalse(matcher.cross_check("2026-11-12", "2026-11-05", pub, NOW.date())[0])
        self.assertFalse(matcher.cross_check("2026-11-12", "2025-13-40", None, NOW.date())[0])
        self.assertTrue(matcher.cross_check("", "", pub, NOW.date())[0])

    def test_one_message_under_200(self):
        w = {"easy_title": "가" * 18, "easy_points": ["나" * 30] * 3, "why_it_matters": "다",
             "term": "제재", "term_explain": "벌로 거래를 막는 것"}
        picks = [dict(art(i, "원래 제목"), ai=ai(i), write=w) for i in range(1, 6)]
        t = formatter.kakao_message(NOW, picks)
        self.assertLessEqual(len(t), 200)
        self.assertEqual(t.count("가" * 18), 5)          # 기사 5개 전부 들어감
        self.assertIn("오늘의 용어", t)
        long = [dict(p, write=dict(w, easy_title="라" * 40)) for p in picks]
        self.assertLessEqual(len(formatter.kakao_message(NOW, long)), 200)

    def test_empty_day_message(self):
        self.assertIn("없어요", formatter.kakao_message(NOW, []))

    def test_page_has_every_link(self):
        picks = [dict(art(i, "제목"), ai=ai(i), published="2026-11-12T08:00:00+09:00",
                      write={"easy_title": "t", "easy_points": ["p"], "why_it_matters": "w"}) for i in range(1, 4)]
        page = formatter.page_html(NOW, picks, [])
        for p in picks:
            self.assertIn(p["url"], page)

if __name__ == "__main__":
    unittest.main()

"""카톡 메시지 1개 + 브리핑 웹페이지.

카카오 '나에게 보내기' 텍스트는 최대 200자, 버튼 링크도 하나뿐이라
- 카톡: 오늘 기사 전부(한 줄씩) → 📖 오늘의 용어 → [기사 원문 보기] 버튼
- 버튼을 누르면: 기사별 쉬운 3줄 요약 + 기사마다 원문 링크가 있는 페이지
"""
import html

from . import config
from .kakao import TEXT_LIMIT

EMOJI = {"국제정세": "🌏", "북한·안보": "🛡️", "국내정치": "🏛️", "경제": "💰", "사회": "👥", "기타": "📌"}
WEEK = "월화수목금토일"


def day_label(now) -> str:
    return f"{now.month}/{now.day}({WEEK[now.weekday()]})"


def _title(a: dict) -> str:
    w = a.get("write") or {}
    return (w.get("easy_title") or a["title"]).strip()


def _terms(picks: list) -> list:
    out = []
    for a in picks:
        w = a.get("write") or {}
        if w.get("term", "").strip() and w.get("term_explain", "").strip():
            line = f"{w['term'].strip()}: {w['term_explain'].strip()}"
            if line not in out:
                out.append(line)
    return out


def kakao_message(now, picks: list) -> str:
    """기사 전부 + 오늘의 용어를 200자 안에 넣는다. 넘치면 용어 → 제목 길이 순으로 줄인다."""
    head = f"☀️ {day_label(now)} 아침 브리핑"
    if not picks:
        return f"{head}\n\n오늘은 새로 알릴 소식이 없어요.\n어제 소식을 한 번 더 떠올려 봐요 🙂"
    terms = _terms(picks)

    def build(title_len, n_terms):
        lines = [head, ""]
        for i, a in enumerate(picks, 1):
            t = _title(a)
            t = t if len(t) <= title_len else t[: title_len - 1] + "…"
            lines.append(f"{EMOJI.get(a.get('ai', {}).get('category'), '📌')} {t}")
        if n_terms:
            lines += ["", "📖 오늘의 용어"] + terms[:n_terms]
        return "\n".join(lines)

    for title_len in (24, 20, 17, 14, 12):
        for n_terms in range(min(len(terms), 2), -1, -1):
            text = build(title_len, n_terms)
            if len(text) <= TEXT_LIMIT:
                return text
    return build(10, 0)[:TEXT_LIMIT]


def page_html(now, picks: list, warnings: list) -> str:
    """난독증 친화 페이지: 큰 글씨, 넓은 줄 간격, 짧은 줄, 기사마다 원문 버튼."""
    e = html.escape
    cards = []
    for i, a in enumerate(picks, 1):
        w = a.get("write") or {}
        cat = a.get("ai", {}).get("category", "기타")
        pts = "".join(f"<li>{e(p)}</li>" for p in w.get("easy_points", [])[:3])
        why = f'<p class="why">🎖️ {e(w["why_it_matters"])}</p>' if w.get("why_it_matters") else ""
        pub = a["published"][:10] if isinstance(a.get("published"), str) else ""
        cards.append(f"""
<section class="card">
  <div class="cat">{EMOJI.get(cat, "📌")} {e(cat)}</div>
  <h2>{i}. {e(_title(a))}</h2>
  <ul>{pts}</ul>{why}
  <p class="meta">🗓 {e(pub)} · {e(a["source"])} · 원래 제목: {e(a["title"])}</p>
  <a class="btn" href="{e(a["url"])}" target="_blank" rel="noopener">기사 원문 보기 →</a>
</section>""")
    terms = "".join(f"<li>{e(t)}</li>" for t in _terms(picks))
    term_box = f'<section class="card"><h2>📖 오늘의 용어</h2><ul>{terms}</ul></section>' if terms else ""
    warn = "".join(f'<p class="warn">{e(x)}</p>' for x in warnings)
    body = "".join(cards) or '<section class="card"><h2>오늘은 새로 알릴 소식이 없어요.</h2></section>'
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>아침 브리핑 {now:%Y-%m-%d}</title>
<style>
:root{{--bg:#f7f5ef;--card:#fff;--ink:#1d1d1f;--sub:#5b5b60;--acc:#2f5d3a;--line:#e3e0d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181a;--card:#202326;--ink:#ececec;--sub:#a5a8ad;--acc:#8fc79b;--line:#33373b}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:19px/1.85 "Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif;letter-spacing:.01em}}
main{{max-width:640px;margin:0 auto;padding:20px 16px 48px}}
h1{{font-size:24px;margin:8px 0 18px}} h2{{font-size:21px;line-height:1.5;margin:6px 0 10px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 18px 20px;margin:0 0 16px}}
.cat{{font-size:15px;color:var(--acc);font-weight:700}} ul{{padding-left:20px;margin:0 0 8px}} li{{margin:4px 0}}
.why{{font-weight:700;margin:8px 0}} .meta{{font-size:14px;color:var(--sub);margin:8px 0 14px;line-height:1.6}}
.btn{{display:block;text-align:center;background:var(--acc);color:var(--bg);text-decoration:none;font-weight:700;padding:12px;border-radius:10px}}
.warn{{background:#fff3cd;color:#5c4400;padding:10px 14px;border-radius:10px;font-size:16px}}
</style></head><body><main>
<h1>☀️ {day_label(now)} 아침 브리핑</h1>{warn}{body}{term_box}
</main></body></html>"""

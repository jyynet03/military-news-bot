"""믿을 수 있는 출처(화이트리스트)의 RSS에서 기사를 모은다."""
import hashlib
import html
import re
from calendar import timegm
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import requests

from . import config

UA = "Mozilla/5.0 (compatible; daily-briefing-bot/1.0)"
_TAG = re.compile(r"<[^>]+>")


def normalize_url(url: str) -> str:
    """추적용 파라미터(utm 등)와 #조각을 지워서 같은 기사를 같은 주소로 만든다."""
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "at_", "fbclid", "ocid"))]
    return urlunparse((p.scheme, p.netloc.lower(), p.path, "", urlencode(q), ""))


def clean(text: str, limit: int = 300) -> str:
    text = html.unescape(_TAG.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _published(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(timegm(t), tz=timezone.utc).astimezone(config.KST)
    return None


def fetch_all() -> list:
    items, seen = [], set()
    for feed in config.FEEDS:
        try:
            r = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=20)
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
        except Exception as e:  # 한 곳이 실패해도 나머지는 계속
            print(f"[경고] 피드 실패: {feed['url']} ({e})")
            continue
        for e in parsed.entries:
            url = normalize_url(e.get("link", ""))
            host = urlparse(url).netloc
            if not url.startswith("https://") or host != feed["domain"]:
                continue  # 화이트리스트 밖 링크는 버림
            if url in seen:
                continue
            seen.add(url)
            items.append({
                "id": hashlib.sha1(url.encode()).hexdigest()[:10],
                "url": url,
                "title": clean(e.get("title", ""), 150),
                "description": clean(e.get("summary", "") or e.get("description", "")),
                "published": _published(e),
                "source": feed["name"],
                "trust": feed["trust"],
                "feed": feed["url"],
                "quota": feed.get("quota", 8),
            })
    print(f"[수집] 기사 {len(items)}건")
    return items

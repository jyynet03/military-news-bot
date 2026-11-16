"""기억 장치: 보낸 기사 기록(history.json)과 실행 상태(state.json).
워크플로가 실행 후 이 파일들을 저장소에 커밋해서 다음 날에도 기억한다."""
import json
import os
from datetime import datetime, timedelta

from . import config


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_history() -> list:
    return _load(config.HISTORY_PATH, [])


def load_state() -> dict:
    return _load(config.STATE_PATH, {})


def remote_state() -> dict | None:
    """GitHub 저장소에 지금 올라가 있는 최신 state.json 을 읽는다.
    (다른 실행이 방금 '오늘 보냄'을 기록했는지 보내기 직전에 확인하기 위함). 실패하면 None."""
    import subprocess
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=config.ROOT, check=True,
                       capture_output=True, timeout=60)
        out = subprocess.run(["git", "show", "origin/main:data/state.json"], cwd=config.ROOT, check=True,
                             capture_output=True, timeout=30).stdout
        return json.loads(out.decode("utf-8"))
    except Exception as e:
        print(f"[경고] 저장소 최신 기록 확인 실패({type(e).__name__}) → 내 기록만으로 판단")
        return None


def save_state(state: dict):
    _save(config.STATE_PATH, state)


def add_to_history(history: list, articles: list, today: str) -> list:
    for a in articles:
        history.append({
            "date": today,
            "url": a["url"],
            "title": a["title"],
            "topic_key": a.get("topic_key", ""),
        })
    cutoff = (datetime.fromisoformat(today) - timedelta(days=config.HISTORY_KEEP_DAYS)).date().isoformat()
    history = [h for h in history if h.get("date", "") >= cutoff]
    _save(config.HISTORY_PATH, history)
    return history


def recent(history: list, today: str, days: int) -> list:
    cutoff = (datetime.fromisoformat(today) - timedelta(days=days)).date().isoformat()
    return [h for h in history if h.get("date", "") >= cutoff]

"""
Twitter(X) API v2 수집 모듈
- 시간 기반 수집 (start_time, 최근 N분)
- note_tweet 지원 (장문 트윗)
- 참고 코드 기반으로 requests 직접 사용
"""

import logging
import requests
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


def resolve_user_id(bearer_token: str, username: str) -> str:
    """username → user_id 변환"""
    url = f"https://api.x.com/2/users/by/username/{username}"
    headers = {"Authorization": f"Bearer {bearer_token}"}

    res = requests.get(url, headers=headers, timeout=10)
    if res.status_code != 200:
        raise ValueError(f"user_id 조회 실패 (@{username}): {res.status_code} {res.text}")

    data = res.json().get("data")
    if not data:
        raise ValueError(f"사용자를 찾을 수 없습니다: @{username}")

    log.info(f"@{username} user_id 조회 완료: {data['id']}")
    return str(data["id"])


def get_recent_tweets(bearer_token: str, user_id: str, minutes: int = 30) -> list[dict]:
    """
    최근 N분간 발행된 원문 트윗 수집.
    note_tweet(장문) 포함, 리트윗·댓글 제외.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)
    start_time = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    log.info(f"[트윗 조회] user_id={user_id} | since: {start_time}")

    url = f"https://api.x.com/2/users/{user_id}/tweets"
    params = {
        "start_time":    start_time,
        "tweet.fields":  "id,created_at,text,note_tweet",
        "exclude":       "retweets,replies",
        "max_results":   100,
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}

    res = requests.get(url, headers=headers, params=params, timeout=10)

    if res.status_code != 200:
        log.error(f"[트윗 조회 실패] {res.status_code} {res.text}")
        return []

    data = res.json().get("data", [])
    log.info(f"[트윗 조회 성공] {len(data)}건 (최근 {minutes}분)")

    tweets = []
    for t in data:
        # 장문 트윗(note_tweet)이 있으면 전체 본문 사용
        text = t.get("note_tweet", {}).get("text") or t.get("text", "")
        tweets.append({
            "id":         str(t["id"]),
            "text":       text,
            "created_at": t.get("created_at", ""),
        })

    # 오래된 순 정렬
    tweets.sort(key=lambda x: x["id"])
    return tweets

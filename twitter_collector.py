"""
Twitter(X) API v2 수집 모듈
"""

import logging
import tweepy

log = logging.getLogger(__name__)


def get_client(bearer_token: str) -> tweepy.Client:
    return tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)


def resolve_user_id(client: tweepy.Client, username: str) -> str:
    resp = client.get_user(username=username, user_fields=["id", "name"])
    if not resp.data:
        raise ValueError(f"사용자를 찾을 수 없습니다: @{username}")
    return str(resp.data.id)


def fetch_new_tweets(
    client: tweepy.Client,
    user_id: str,
    since_id: str | None,
    max_results: int = 20,
) -> list[dict]:
    """
    since_id 이후 새 트윗 수집 (원문 트윗만, 최대 max_results건)
    """
    kwargs = dict(
        id=user_id,
        max_results=min(max_results, 100),
        tweet_fields=["created_at", "text", "id"],
        exclude=["retweets", "replies"],
    )
    if since_id:
        kwargs["since_id"] = since_id

    try:
        resp = client.get_users_tweets(**kwargs)
    except tweepy.errors.TweepyException as e:
        log.error(f"Twitter API 오류 (user_id={user_id}): {e}")
        return []

    if not resp.data:
        return []

    tweets = [
        {"id": str(t.id), "text": t.text, "created_at": str(t.created_at)}
        for t in resp.data
    ]
    # 오래된 순으로 정렬
    tweets.sort(key=lambda t: t["id"])
    return tweets

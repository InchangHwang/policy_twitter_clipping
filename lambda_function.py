"""
AWS Lambda Entry Point
- EventBridge (rate: 15 minutes) → lambda_handler 호출
- 로컬 실행: python lambda_function.py
"""

import logging
import os

# ── CloudWatch Logs 연동 로깅 설정 ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger(__name__)

# 로컬 실행 시 .env 로드 (Lambda 환경에서는 무시됨)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import get_secrets, get_accounts, get_app_config
from state_manager import StateManager
from twitter_collector import get_client, resolve_user_id, fetch_new_tweets
from gemini_filter import GeminiFilter
from telegram_sender import TelegramSender


# ── Lambda Handler ────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda 진입점.
    EventBridge 스케줄 또는 수동 호출 모두 지원.
    """
    log.info("===== 클리핑 시작 =====")

    # 1. 설정 로드
    cfg     = get_app_config()
    secrets = get_secrets()
    accounts = get_accounts()

    log.info(f"수집 대상 계정: {[a['username'] for a in accounts]}")

    # 2. 클라이언트 초기화
    twitter  = get_client(secrets["TWITTER_BEARER_TOKEN"])
    gemini   = GeminiFilter(
        api_key    = secrets["GEMINI_API_KEY"],
        model_name = cfg["gemini_model"],
        rpm_limit  = cfg["gemini_rpm_limit"],
    )
    telegram = TelegramSender(
        bot_token = secrets["TELEGRAM_BOT_TOKEN"],
        chat_id   = secrets["TELEGRAM_CHAT_ID"],
    )
    state = StateManager(
        table_name = cfg["state_table"],
        region     = cfg["aws_region"],
    )

    # 3. 계정별 수집 · 필터 · 발송
    total_sent = total_filtered = 0

    for account in accounts:
        username = account["username"]
        log.info(f"--- 계정 처리 시작: @{username} ({account['label']}) ---")

        try:
            # user_id 조회 (state에 캐싱)
            user_id = state.get_last_tweet_id(f"_uid_{username}")
            if not user_id:
                user_id = resolve_user_id(twitter, username)
                state.set_last_tweet_id(f"_uid_{username}", user_id)
                log.info(f"@{username} user_id 조회: {user_id}")

            # 새 트윗 수집
            since_id = state.get_last_tweet_id(username)
            tweets   = fetch_new_tweets(
                twitter,
                user_id,
                since_id,
                max_results=cfg["max_tweets_per_run"],
            )
            log.info(f"@{username} 새 트윗 {len(tweets)}건 수집")

            if not tweets:
                continue

            sent_count = filtered_count = 0
            latest_id  = since_id

            for tweet in tweets:
                # 필터링 여부 판단
                if account.get("filter_enabled", True):
                    relevant, reason = gemini.check_relevance(tweet["text"])
                else:
                    relevant, reason = True, "필터링 미적용"

                if relevant:
                    msg = telegram.format_message(tweet, account, reason)
                    telegram.send(msg)
                    sent_count += 1
                    log.info(f"[발송 ✅] {tweet['id']} | {reason} | {tweet['text'][:40]}")
                else:
                    filtered_count += 1
                    log.info(f"[필터 ❌] {tweet['id']} | {reason} | {tweet['text'][:40]}")

                latest_id = tweet["id"]

            # 상태 저장
            if latest_id and latest_id != since_id:
                state.set_last_tweet_id(username, latest_id)

            log.info(f"@{username} 결과: 발송 {sent_count}건 / 필터 {filtered_count}건")
            total_sent     += sent_count
            total_filtered += filtered_count

        except Exception as e:
            log.exception(f"@{username} 처리 중 오류: {e}")
            continue  # 한 계정 실패해도 다음 계정 계속 처리

    log.info(f"===== 완료: 전체 발송 {total_sent}건 / 필터 {total_filtered}건 =====")

    return {
        "statusCode": 200,
        "body": {
            "total_sent":     total_sent,
            "total_filtered": total_filtered,
            "accounts":       [a["username"] for a in accounts],
        },
    }


# ── 로컬 실행 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import schedule
    import time

    cfg = get_app_config()
    interval = cfg["fetch_interval_minutes"]
    log.info(f"로컬 스케줄러 시작 | 주기: {interval}분")

    lambda_handler({}, None)
    schedule.every(interval).minutes.do(lambda_handler, event={}, context=None)

    while True:
        schedule.run_pending()
        time.sleep(30)

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
from twitter_collector import resolve_user_id, get_recent_tweets
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
    cfg      = get_app_config()
    secrets  = get_secrets()
    accounts = get_accounts()

    bearer_token = secrets["TWITTER_BEARER_TOKEN"]
    log.info(f"수집 대상 계정: {[a['username'] for a in accounts]}")

    # 2. 클라이언트 초기화
    gemini = GeminiFilter(
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

    # 3. 계정별 수집 · 중복 제거 · 필터 · 발송
    total_sent = total_filtered = total_duplicate = 0

    for account in accounts:
        username = account["username"]
        log.info(f"--- 계정 처리 시작: @{username} ({account['label']}) ---")

        try:
            # user_id 조회 (state에 캐싱)
            user_id = state.get_user_id(username)
            if not user_id:
                user_id = resolve_user_id(bearer_token, username)
                state.set_user_id(username, user_id)

            # 최근 30분 트윗 수집
            tweets = get_recent_tweets(
                bearer_token = bearer_token,
                user_id      = user_id,
                minutes      = cfg.get("crawl_minutes", 30),
            )
            log.info(f"@{username} 수집: {len(tweets)}건")

            if not tweets:
                continue

            # 이미 발송된 tweet_id 로드 → 중복 제거
            sent_ids   = state.get_sent_ids(username)
            new_tweets = [t for t in tweets if t["id"] not in sent_ids]
            dup_count  = len(tweets) - len(new_tweets)

            if dup_count:
                log.info(f"@{username} 중복 제거: {dup_count}건 스킵")
            total_duplicate += dup_count

            sent_count = filtered_count = 0
            sent_ids_to_save = []    # 발송 성공한 ID
            filtered_ids_to_save = []  # 필터링된 ID (재판단 방지용)

            for tweet in new_tweets:
                # Gemini 필터링
                if account.get("filter_enabled", True):
                    relevant, reason = gemini.check_relevance(tweet["text"])
                else:
                    relevant, reason = True, "필터링 미적용"

                if relevant:
                    msg = telegram.format_message(tweet, account, reason)
                    try:
                        telegram.send(msg)
                        sent_ids_to_save.append(tweet["id"])
                        sent_count += 1
                        log.info(f"[발송 ✅] {tweet['id']} | {tweet['text'][:40]}")
                    except Exception as send_err:
                        log.error(f"[발송 실패] {tweet['id']} | {send_err} → 다음 타임에 재시도")
                else:
                    filtered_ids_to_save.append(tweet["id"])
                    filtered_count += 1
                    log.info(f"[필터 ❌] {tweet['id']} | {reason} | {tweet['text'][:40]}")

            # 발송 성공 ID + 필터링 ID 저장 (발송 실패 ID는 저장 안 함 → 재시도)
            ids_to_save = sent_ids_to_save + filtered_ids_to_save
            if ids_to_save:
                state.add_sent_ids(username, ids_to_save)

            log.info(
                f"@{username} 결과: 발송 {sent_count}건 / "
                f"필터 {filtered_count}건 / 중복 {dup_count}건"
            )
            total_sent     += sent_count
            total_filtered += filtered_count

        except Exception as e:
            log.exception(f"@{username} 처리 중 오류: {e}")
            continue

    log.info(
        f"===== 완료: 발송 {total_sent}건 / "
        f"필터 {total_filtered}건 / 중복제거 {total_duplicate}건 ====="
    )

    return {
        "statusCode": 200,
        "body": {
            "total_sent":      total_sent,
            "total_filtered":  total_filtered,
            "total_duplicate": total_duplicate,
            "accounts":        [a["username"] for a in accounts],
        },
    }


# ── 로컬 실행 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import schedule
    import time

    cfg      = get_app_config()
    interval = cfg["fetch_interval_minutes"]
    log.info(f"로컬 스케줄러 시작 | 주기: {interval}분")

    lambda_handler({}, None)
    schedule.every(interval).minutes.do(lambda_handler, event={}, context=None)

    while True:
        schedule.run_pending()
        time.sleep(30)

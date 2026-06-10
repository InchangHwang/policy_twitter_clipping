"""
Telegram 발송 모듈
"""

import logging
import requests
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def to_kst_korean(utc_str: str) -> str:
    """UTC 문자열 → 한국어 날짜시간 형식 변환 (예: 2026.06.10 오후 3시)"""
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        kst_dt = dt.astimezone(KST)
        hour = kst_dt.hour
        ampm = "오전" if hour < 12 else "오후"
        hour_12 = hour % 12 or 12
        return kst_dt.strftime(f"%Y.%m.%d {ampm} {hour_12}시")
    except Exception:
        return utc_str  # 변환 실패 시 원본 반환


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send(self, text: str, retries: int = 2):
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id":                  self.chat_id,
            "text":                     text,
            "parse_mode":               "HTML",
            "disable_web_page_preview": False,
        }
        for attempt in range(retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=10)
                resp.raise_for_status()
                return
            except requests.HTTPError as e:
                log.error(f"Telegram 발송 실패 (시도 {attempt+1}): {e}")
                if attempt == retries:
                    raise

    def format_message(self, tweet: dict, account: dict, reason: str = "") -> str:
        header = account.get("telegram_header", f"[{account['label']} 트위터]")
        tweet_url = f"https://twitter.com/{account['username']}/status/{tweet['id']}"

        
        parts = [
            f"<b>{header}</b>",
            to_kst_korean(tweet["created_at"]),
            f"<a href=\"{tweet_url}\">본문링크</a>",
        ]
        return "\n".join(parts)

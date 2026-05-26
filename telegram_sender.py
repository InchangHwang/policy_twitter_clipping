"""
Telegram 발송 모듈
"""

import logging
import requests

log = logging.getLogger(__name__)


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
            f"<b>{header}</b>\n",
            tweet["text"],
            "",
        ]
        if reason:
            parts.append(f"📌 <i>{reason}</i>")
        parts += [
            f"🕐 {tweet['created_at']}",
            f"🔗 <a href=\"{tweet_url}\">원문 보기</a>",
        ]
        return "\n".join(parts)

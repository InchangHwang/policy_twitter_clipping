"""
대외정책 뉴스클리핑 배치 프로그램
- Twitter(@Jaemyung_Lee) → Gemini SK가스 관련성 필터링 → Telegram 발송
- 15분 주기 실행
"""

import os
import json
import time
import logging
import schedule
from pathlib import Path
from dotenv import load_dotenv

import tweepy
import google.generativeai as genai
import requests

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("clipping.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────────────────────────────

TWITTER_BEARER_TOKEN   = os.environ["TWITTER_BEARER_TOKEN"]
GEMINI_API_KEY         = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN     = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID       = os.environ["TELEGRAM_CHAT_ID"]
TARGET_USERNAME        = os.getenv("TWITTER_TARGET_USERNAME", "Jaemyung_Lee")
FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "15"))

STATE_FILE = Path("state.json")

# ── SK가스 관련성 판단 프롬프트 ───────────────────────────────────────────────

FILTER_PROMPT = """당신은 한국 에너지 기업 'SK가스'의 경영전략 분석가입니다.
SK가스는 LPG·LNG 공급, 수소에너지, 분산발전, 탄소중립, 전력시장 등 에너지 산업 전반에 걸쳐 사업을 영위합니다.

아래 트윗이 SK가스의 사업 환경에 직접적 또는 간접적으로 관련이 있는지 의미적으로 판단해주세요.

[관련 있음으로 판단할 주제]
- 에너지 산업: LPG, LNG, 천연가스, 수소, 전력, 발전, 전력망
- 탄소·환경: 탄소배출권, 탄소세, 탄소중립, 친환경 정책, 온실가스
- 전력 시장: 전기요금, 한전, 전기사업법, 전력 수급, 에너지 요금
- 디지털 인프라: 데이터센터, AI 인프라, 전력 수요 증가
- 에너지 정책: 분산에너지, 에너지 안보, 자원 외교, 석유화학
- 송전 기술: HVDC, 초고압 직류송전, 전력망 인프라
- 위 주제와 직·간접적으로 연결되는 산업·경제·정책 이슈

[관련 없음으로 판단할 주제]
- 개인 일상, 감정 표현, 사적인 이야기
- 단순 국내 정치 공방, 선거, 지지율
- 복지, 교육, 부동산 등 에너지와 무관한 정책
- 스포츠, 문화, 연예
- 에너지·산업과 연결고리가 없는 일반 사회 이슈

[판단 원칙]
- 단순 키워드 매칭이 아닌 문맥과 의미를 기반으로 판단하세요.
- "간접적 관련"도 포함합니다. 예: 산업용 전기요금 인상 → 에너지 비용 이슈 → SK가스 관련
- 애매한 경우 관련 없음으로 처리하세요.

트윗:
\"\"\"{tweet_text}\"\"\"

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이):
{{"relevant": true 또는 false, "reason": "한 줄 판단 근거"}}"""

# ── 상태 관리 ─────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_tweet_id": None, "target_user_id": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Twitter 수집 ──────────────────────────────────────────────────────────────

def get_twitter_client() -> tweepy.Client:
    return tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN, wait_on_rate_limit=True)


def resolve_user_id(client: tweepy.Client, username: str) -> str:
    resp = client.get_user(username=username, user_fields=["id", "name"])
    if not resp.data:
        raise ValueError(f"사용자를 찾을 수 없습니다: @{username}")
    return str(resp.data.id)


def fetch_new_tweets(client: tweepy.Client, user_id: str, since_id: str | None) -> list[dict]:
    """since_id 이후의 새 트윗을 최대 100건 가져온다."""
    kwargs = dict(
        id=user_id,
        max_results=100,
        tweet_fields=["created_at", "text", "id"],
        exclude=["retweets", "replies"],
    )
    if since_id:
        kwargs["since_id"] = since_id

    resp = client.get_users_tweets(**kwargs)
    if not resp.data:
        return []

    tweets = [{"id": str(t.id), "text": t.text, "created_at": str(t.created_at)} for t in resp.data]
    tweets.sort(key=lambda t: t["id"])
    return tweets


# ── Gemini 필터링 ─────────────────────────────────────────────────────────────

def init_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-2.5-flash")


def check_relevance(model, tweet_text: str) -> tuple[bool, str]:
    """SK가스 관련성 여부와 판단 근거를 반환."""
    prompt = FILTER_PROMPT.format(tweet_text=tweet_text)
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            result = json.loads(raw)
            time.sleep(13)  # 분당 5회 제한 준수
            return bool(result["relevant"]), result.get("reason", "")
        except Exception as e:
            msg = str(e)
            if "429" in msg:
                wait = 65
                log.warning(f"Gemini 속도 제한 → {wait}초 대기 후 재시도 ({attempt+1}/3)")
                time.sleep(wait)
            else:
                log.warning(f"Gemini 응답 파싱 실패: {msg[:200]}")
                return False, "판단 실패"
    return False, "판단 실패 (재시도 초과)"


# ── Telegram 발송 ─────────────────────────────────────────────────────────────

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()


def format_message(tweet: dict, reason: str) -> str:
    tweet_url = f"https://twitter.com/{TARGET_USERNAME}/status/{tweet['id']}"
    return (
        f"<b>[이재명 대통령 트위터]</b>\n\n"
        f"{tweet['text']}\n\n"
        f"📌 <i>{reason}</i>\n"
        f"🕐 {tweet['created_at']}\n"
        f"🔗 <a href=\"{tweet_url}\">원문 보기</a>"
    )


# ── 메인 루프 ─────────────────────────────────────────────────────────────────

def run_once():
    log.info("===== 수집 시작 =====")
    state = load_state()

    try:
        twitter = get_twitter_client()
        gemini  = init_gemini()

        if not state["target_user_id"]:
            state["target_user_id"] = resolve_user_id(twitter, TARGET_USERNAME)
            log.info(f"@{TARGET_USERNAME} user_id = {state['target_user_id']}")
            save_state(state)

        tweets = fetch_new_tweets(twitter, state["target_user_id"], state["last_tweet_id"])
        log.info(f"새 트윗 {len(tweets)}건 수집")

        sent_count  = 0
        skip_count  = 0
        latest_id   = state["last_tweet_id"]

        for tweet in tweets:
            relevant, reason = check_relevance(gemini, tweet["text"])

            if relevant:
                msg = format_message(tweet, reason)
                send_telegram(msg)
                sent_count += 1
                log.info(f"[발송 ✅] {tweet['id']} | {reason} | {tweet['text'][:40]}")
            else:
                skip_count += 1
                log.info(f"[필터 ❌] {tweet['id']} | {reason} | {tweet['text'][:40]}")

            latest_id = tweet["id"]

        state["last_tweet_id"] = latest_id or state["last_tweet_id"]
        save_state(state)
        log.info(f"결과: 발송 {sent_count}건 / 필터 {skip_count}건 | 다음 실행까지 {FETCH_INTERVAL_MINUTES}분 대기")

    except tweepy.errors.TweepyException as e:
        log.error(f"Twitter API 오류: {e}")
    except requests.HTTPError as e:
        log.error(f"Telegram 발송 오류: {e}")
    except Exception as e:
        log.exception(f"예기치 않은 오류: {e}")


def main():
    log.info(f"SK가스 클리핑 시작 | 대상: @{TARGET_USERNAME} | 주기: {FETCH_INTERVAL_MINUTES}분")
    run_once()
    schedule.every(FETCH_INTERVAL_MINUTES).minutes.do(run_once)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()

"""
설정 로더 - AWS Secrets Manager & SSM Parameter Store / 로컬 환경변수 모두 지원
"""

import os
import json
import logging

log = logging.getLogger(__name__)

# ── Secrets 로드 ──────────────────────────────────────────────────────────────

def get_secrets() -> dict:
    """
    AWS Secrets Manager에서 민감 정보를 로드.
    로컬 실행 시 환경변수(.env)에서 fallback.
    """
    secret_name = os.environ.get("SECRET_NAME", "twitter-clipping/secrets")

    try:
        import boto3
        region = os.environ.get("AWS_REGION", "ap-northeast-2")
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secrets = json.loads(response["SecretString"])
        log.info("Secrets Manager에서 시크릿 로드 완료")
        return secrets
    except Exception as e:
        log.warning(f"Secrets Manager 조회 실패, 환경변수 fallback: {e}")
        # 로컬 개발 환경: 환경변수에서 직접 로드
        return {
            "TWITTER_BEARER_TOKEN": os.environ["TWITTER_BEARER_TOKEN"],
            "GEMINI_API_KEY":       os.environ["GEMINI_API_KEY"],
            "TELEGRAM_BOT_TOKEN":   os.environ["TELEGRAM_BOT_TOKEN"],
            "TELEGRAM_CHAT_ID":     os.environ["TELEGRAM_CHAT_ID"],
        }


# ── 계정 목록 로드 ────────────────────────────────────────────────────────────

def get_accounts() -> list[dict]:
    """
    수집 대상 계정 목록 로드.
    우선순위: SSM Parameter Store → 로컬 accounts.json
    """
    param_name = os.environ.get("ACCOUNTS_PARAM", "/twitter-clipping/accounts")

    try:
        import boto3
        region = os.environ.get("AWS_REGION", "ap-northeast-2")
        ssm = boto3.client("ssm", region_name=region)
        response = ssm.get_parameter(Name=param_name, WithDecryption=False)
        accounts = json.loads(response["Parameter"]["Value"])
        log.info(f"SSM에서 계정 목록 로드: {len(accounts)}개")
        return [a for a in accounts if a.get("active", True)]
    except Exception as e:
        log.warning(f"SSM 조회 실패, 로컬 accounts.json fallback: {e}")
        # 로컬 개발 환경: 파일에서 직접 로드
        accounts_path = os.path.join(os.path.dirname(__file__), "accounts.json")
        with open(accounts_path, encoding="utf-8") as f:
            accounts = json.load(f)
        return [a for a in accounts if a.get("active", True)]


# ── 공통 설정 ─────────────────────────────────────────────────────────────────

def get_app_config() -> dict:
    return {
        "fetch_interval_minutes": int(os.environ.get("FETCH_INTERVAL_MINUTES", "15")),
        "max_tweets_per_run":     int(os.environ.get("MAX_TWEETS_PER_RUN", "20")),
        "state_table":            os.environ.get("STATE_TABLE", "twitter-clipping-state"),
        "aws_region":             os.environ.get("AWS_REGION", "ap-northeast-2"),
        "gemini_model":           os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "gemini_rpm_limit":       int(os.environ.get("GEMINI_RPM_LIMIT", "5")),
    }

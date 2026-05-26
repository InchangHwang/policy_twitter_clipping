"""
상태 관리 - DynamoDB 기반 (Lambda 무상태 환경 대응)
로컬 실행 시 state.json fallback 지원
"""

import os
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "state.json"  # 로컬 fallback


class StateManager:
    def __init__(self, table_name: str, region: str = "ap-northeast-2"):
        self.table_name = table_name
        self.region = region
        self._table = None
        self._use_dynamodb = True
        self._init_dynamodb()

    def _init_dynamodb(self):
        try:
            import boto3
            dynamodb = boto3.resource("dynamodb", region_name=self.region)
            self._table = dynamodb.Table(self.table_name)
            # 연결 확인
            self._table.load()
            log.info(f"DynamoDB 연결 성공: {self.table_name}")
        except Exception as e:
            log.warning(f"DynamoDB 연결 실패, 로컬 state.json fallback: {e}")
            self._use_dynamodb = False

    def get_last_tweet_id(self, username: str) -> str | None:
        if self._use_dynamodb:
            try:
                resp = self._table.get_item(Key={"username": username})
                return resp.get("Item", {}).get("last_tweet_id")
            except Exception as e:
                log.error(f"DynamoDB 읽기 실패 ({username}): {e}")
                return self._local_get(username)
        return self._local_get(username)

    def set_last_tweet_id(self, username: str, tweet_id: str):
        if self._use_dynamodb:
            try:
                self._table.put_item(Item={
                    "username":      username,
                    "last_tweet_id": tweet_id,
                })
                log.debug(f"DynamoDB 저장: {username} → {tweet_id}")
                return
            except Exception as e:
                log.error(f"DynamoDB 쓰기 실패 ({username}): {e}")
        self._local_set(username, tweet_id)

    # ── 로컬 fallback ─────────────────────────────────────────────────────────

    def _load_local(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {}

    def _save_local(self, data: dict):
        STATE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _local_get(self, username: str) -> str | None:
        return self._load_local().get(username)

    def _local_set(self, username: str, tweet_id: str):
        data = self._load_local()
        data[username] = tweet_id
        self._save_local(data)

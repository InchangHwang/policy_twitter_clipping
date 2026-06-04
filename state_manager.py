"""
상태 관리 - DynamoDB 기반 (Lambda 무상태 환경 대응)
로컬 실행 시 state.json fallback 지원

저장 항목:
  - _uid_{username}   : Twitter user_id 캐시
  - _sent_{username}  : 발송 완료된 tweet_id 목록 (중복 발송 방지)
"""

import os
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

STATE_FILE  = Path(__file__).parent / "state.json"
MAX_SENT_IDS = 500  # 저장할 최대 tweet_id 수 (메모리/용량 관리)


class StateManager:
    def __init__(self, table_name: str, region: str = "ap-northeast-2"):
        self.table_name = table_name
        self.region     = region
        self._table     = None
        self._use_dynamodb = True
        self._init_dynamodb()

    def _init_dynamodb(self):
        try:
            import boto3
            dynamodb   = boto3.resource("dynamodb", region_name=self.region)
            self._table = dynamodb.Table(self.table_name)
            self._table.load()
            log.info(f"DynamoDB 연결 성공: {self.table_name}")
        except Exception as e:
            log.warning(f"DynamoDB 연결 실패, 로컬 state.json fallback: {e}")
            self._use_dynamodb = False

    # ── user_id 캐시 ──────────────────────────────────────────────────────────

    def get_user_id(self, username: str) -> str | None:
        return self._get(f"_uid_{username}", "value")

    def set_user_id(self, username: str, user_id: str):
        self._set(f"_uid_{username}", {"value": user_id})

    # ── 발송 완료 tweet_id 관리 (중복 방지) ──────────────────────────────────

    def get_sent_ids(self, username: str) -> set:
        """발송 완료된 tweet_id 집합 반환"""
        ids = self._get(f"_sent_{username}", "sent_ids")
        return set(ids) if ids else set()

    def add_sent_ids(self, username: str, new_ids: list[str]):
        """새로 발송된 tweet_id 추가, 최대 MAX_SENT_IDS 유지"""
        existing = list(self.get_sent_ids(username))
        merged   = existing + [i for i in new_ids if i not in existing]
        # 오래된 것부터 제거 (최신 MAX_SENT_IDS개만 유지)
        trimmed  = merged[-MAX_SENT_IDS:]
        self._set(f"_sent_{username}", {"sent_ids": trimmed})
        log.debug(f"sent_ids 저장: @{username} +{len(new_ids)}건 (총 {len(trimmed)}건)")

    # ── 내부 공통 읽기/쓰기 ──────────────────────────────────────────────────

    def _get(self, key: str, field: str):
        if self._use_dynamodb:
            try:
                resp = self._table.get_item(Key={"username": key})
                return resp.get("Item", {}).get(field)
            except Exception as e:
                log.error(f"DynamoDB 읽기 실패 ({key}): {e}")
        return self._local_get(key, field)

    def _set(self, key: str, fields: dict):
        item = {"username": key, **fields}
        if self._use_dynamodb:
            try:
                self._table.put_item(Item=item)
                return
            except Exception as e:
                log.error(f"DynamoDB 쓰기 실패 ({key}): {e}")
        self._local_set(key, fields)

    # ── 로컬 fallback ─────────────────────────────────────────────────────────

    def _load_local(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {}

    def _save_local(self, data: dict):
        STATE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _local_get(self, key: str, field: str):
        return self._load_local().get(key, {}).get(field)

    def _local_set(self, key: str, fields: dict):
        data      = self._load_local()
        data[key] = {**data.get(key, {}), **fields}
        self._save_local(data)

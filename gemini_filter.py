"""
Gemini AI 필터링 모듈 - SK가스 관련성 판단
"""

import json
import time
import logging
import google.generativeai as genai

log = logging.getLogger(__name__)

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
- "간접적 관련"도 포함합니다.
- 애매한 경우 관련 없음으로 처리하세요.

트윗:
\"\"\"{tweet_text}\"\"\"

반드시 아래 JSON 형식으로만 답변하세요 (다른 텍스트 없이):
{{"relevant": true 또는 false, "reason": "한 줄 판단 근거"}}"""


class GeminiFilter:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash", rpm_limit: int = 5):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.min_interval = 60.0 / rpm_limit  # 초 단위 최소 호출 간격
        self._last_call_time = 0.0

    def _rate_limit_wait(self):
        """RPM 한도 준수를 위한 스마트 대기"""
        elapsed = time.time() - self._last_call_time
        wait = self.min_interval - elapsed
        if wait > 0:
            log.debug(f"Rate limit 대기: {wait:.1f}초")
            time.sleep(wait)

    def check_relevance(self, tweet_text: str, max_retries: int = 3) -> tuple[bool, str]:
        """SK가스 관련성 판단. (relevant, reason) 반환"""
        prompt = FILTER_PROMPT.format(tweet_text=tweet_text)

        for attempt in range(max_retries):
            self._rate_limit_wait()
            try:
                self._last_call_time = time.time()
                response = self.model.generate_content(prompt)
                raw = response.text.strip()
                if "```" in raw:
                    raw = raw.split("```")[1].lstrip("json").strip()
                result = json.loads(raw)
                return bool(result["relevant"]), result.get("reason", "")

            except Exception as e:
                msg = str(e)
                if "429" in msg:
                    wait = 65
                    log.warning(f"Gemini 속도 제한 → {wait}초 대기 ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                    self._last_call_time = time.time()
                else:
                    log.warning(f"Gemini 응답 파싱 실패: {msg[:200]}")
                    return False, "판단 실패"

        return False, "판단 실패 (재시도 초과)"

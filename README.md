# 대외정책 뉴스클리핑 - 이재명 대통령 트위터 모니터링

이재명 대통령 X(트위터) 계정을 15분 주기로 수집하여 SK가스 관련 내용을 Gemini AI로 필터링한 후 텔레그램으로 발송하는 배치 프로그램입니다.

## 동작 흐름

```
Twitter(@Jaemyung_Lee) → Gemini 2.5 Flash 필터링 → Telegram 발송
         15분 주기              SK가스 관련성 판단
```

## 필터링 기준 (SK가스 관련 주제)

- 에너지 산업: LPG, LNG, 천연가스, 수소, 전력, 발전, 전력망
- 탄소·환경: 탄소배출권, 탄소세, 탄소중립, 친환경 정책
- 전력 시장: 전기요금, 한전, 전기사업법
- 디지털 인프라: 데이터센터, AI 인프라 전력 수요
- 에너지 정책: 분산에너지, 자원, 석유화학
- 송전 기술: HVDC 등

## 설치 방법

### 1. 사전 준비 (API 키 발급)

| 항목 | 발급처 |
|------|--------|
| Twitter Bearer Token | [developer.twitter.com](https://developer.twitter.com) (Basic 플랜 이상) |
| Gemini API Key | [aistudio.google.com](https://aistudio.google.com) |
| Telegram Bot Token | 텔레그램 @BotFather |
| Telegram Chat ID | 메시지 받을 계정 ID |

### 2. 환경변수 설정

`.env.example`을 복사하여 `.env` 파일 생성 후 값 입력:

```bash
cp .env.example .env
```

```env
TWITTER_BEARER_TOKEN=your_token
GEMINI_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TWITTER_TARGET_USERNAME=Jaemyung_Lee
FETCH_INTERVAL_MINUTES=15
```

### 3. 패키지 설치 및 실행

```bash
# Windows
setup.bat

# 또는 수동 설치
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 파일 구조

```
├── main.py              # 메인 프로그램
├── requirements.txt     # 패키지 목록
├── .env.example         # 환경변수 양식
├── setup.bat            # Windows 설치 스크립트
└── README.md
```

## 로그

실행 후 `clipping.log` 파일에서 발송/필터 내역 확인 가능:

```
[발송 ✅] 트윗ID | Gemini 판단 근거 | 트윗 내용 앞부분
[필터 ❌] 트윗ID | Gemini 판단 근거 | 트윗 내용 앞부분
```

## 주의사항

- `.env` 파일은 절대 공유하거나 GitHub에 업로드하지 마세요 (API 키 포함)
- Twitter API는 Basic 플랜 이상 필요 (월 $100)
- Gemini API 무료 티어: 분당 5회 제한

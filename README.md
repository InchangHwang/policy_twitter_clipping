# Twitter 클리핑 - SK가스 대외정책 모니터링

트위터 계정을 15분 주기로 수집하여 SK가스 관련 내용을 Gemini AI로 필터링한 후 텔레그램으로 발송하는 **AWS Lambda 서버리스 배치 프로그램**입니다.

## 아키텍처

```
EventBridge (15분)
    ↓
AWS Lambda (lambda_function.py)
    ├── Secrets Manager   → API 키 로드
    ├── SSM Parameter Store → 계정 목록 로드
    ├── Twitter API v2    → 새 트윗 수집
    ├── Gemini 2.5 Flash  → SK가스 관련성 필터링
    ├── Telegram Bot      → 관련 트윗 발송
    └── DynamoDB          → 수집 상태 저장 (last_tweet_id)
```

## 수집 대상 계정

`accounts.json` 파일 또는 SSM Parameter Store(`/twitter-clipping/accounts`)로 관리:

| 계정 | 설명 | 필터링 |
|------|------|--------|
| @Jaemyung_Lee | 이재명 대통령 | 활성 |
| @no1nowon | 기후부 장관 | 활성 |

계정 추가 시 `accounts.json`에 항목 추가 후 SSM 업데이트.

## 필터링 기준 (SK가스 관련 주제)

- 에너지 산업: LPG, LNG, 천연가스, 수소, 전력, 발전, 전력망
- 탄소·환경: 탄소배출권, 탄소세, 탄소중립, 친환경 정책
- 전력 시장: 전기요금, 한전, 전기사업법
- 디지털 인프라: 데이터센터, AI 인프라 전력 수요
- 에너지 정책: 분산에너지, 자원, 석유화학, HVDC

## 파일 구조

```
├── lambda_function.py     # Lambda 진입점 (handler + 로컬 스케줄러)
├── config.py              # Secrets Manager / SSM 설정 로더
├── state_manager.py       # DynamoDB 상태 관리
├── twitter_collector.py   # Twitter API v2 수집
├── gemini_filter.py       # Gemini AI 필터링
├── telegram_sender.py     # Telegram 발송
├── accounts.json          # 수집 계정 목록 (민감정보 없음)
├── requirements.txt       # 의존성
├── build_lambda.bat       # ZIP 패키지 빌드 스크립트 (Windows)
├── .env.example           # 로컬 환경변수 양식
├── .gitignore
└── .pre-commit-config.yaml  # 시크릿 유출 방지 훅
```

## AWS 배포 (수동 - 콘솔 ZIP 업로드)

### 1단계. Secrets Manager 시크릿 생성

AWS 콘솔 → Secrets Manager → **새 시크릿 저장** → 기타 유형 선택 후 아래 키/값 입력:

| 키 | 값 |
|----|-----|
| TWITTER_BEARER_TOKEN | Twitter API Bearer Token |
| GEMINI_API_KEY | Google AI Studio API Key |
| TELEGRAM_BOT_TOKEN | Telegram Bot Token |
| TELEGRAM_CHAT_ID | Telegram Chat ID |

- 시크릿 이름: `twitter-clipping/secrets`
- 리전: `ap-northeast-2` (서울)

---

### 2단계. SSM Parameter Store 계정 목록 등록

AWS 콘솔 → Systems Manager → Parameter Store → **파라미터 생성**

- 이름: `/twitter-clipping/accounts`
- 유형: `String`
- 값:
```json
[
  {"username":"Jaemyung_Lee","label":"이재명 대통령","telegram_header":"[이재명 대통령 트위터]","filter_enabled":true,"active":true},
  {"username":"no1nowon","label":"기후부 장관","telegram_header":"[기후부 장관 트위터]","filter_enabled":true,"active":true}
]
```

---

### 3단계. DynamoDB 테이블 생성

AWS 콘솔 → DynamoDB → **테이블 생성**

| 항목 | 값 |
|------|-----|
| 테이블 이름 | `twitter-clipping-state` |
| 파티션 키 | `username` (문자열) |
| 용량 모드 | 온디맨드 |

---

### 4단계. Lambda 함수 생성

AWS 콘솔 → Lambda → **함수 생성**

| 항목 | 값 |
|------|-----|
| 함수 이름 | `twitter-clipping` |
| 런타임 | Python 3.12 |
| 아키텍처 | x86_64 |

---

### 5단계. ZIP 패키지 빌드 및 업로드

```bash
# Windows: 빌드 스크립트 실행
build_lambda.bat
```

생성된 `lambda_package.zip` 파일을 Lambda 콘솔 → **코드 소스** → **업로드** → `.zip 파일` 선택하여 업로드.

- 핸들러 설정: `lambda_function.lambda_handler`

---

### 6단계. Lambda 환경 변수 설정

Lambda 콘솔 → **구성** → **환경 변수** → 편집:

| 키 | 값 |
|----|-----|
| SECRET_NAME | `twitter-clipping/secrets` |
| ACCOUNTS_PARAM | `/twitter-clipping/accounts` |
| STATE_TABLE | `twitter-clipping-state` |
| AWS_REGION | `ap-northeast-2` |
| GEMINI_MODEL | `gemini-2.5-flash` |
| MAX_TWEETS_PER_RUN | `20` |

---

### 7단계. Lambda IAM 권한 설정

Lambda 콘솔 → **구성** → **권한** → 실행 역할 클릭 → IAM 역할에 아래 정책 추가:

- `SecretsManagerReadWrite`
- `AmazonSSMReadOnlyAccess`
- `AmazonDynamoDBFullAccess`

---

### 8단계. EventBridge 스케줄 설정

Lambda 콘솔 → **트리거 추가** → EventBridge

- 새 규칙 생성
- 규칙 이름: `twitter-clipping-schedule`
- 일정 표현식: `rate(15 minutes)`

---

### 계정 추가 방법 (재배포 불필요)

AWS 콘솔 → SSM Parameter Store → `/twitter-clipping/accounts` → **편집** → JSON에 계정 추가 후 저장

## 로컬 실행 (개발용)

```bash
# 1. 의존성 설치
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 3. 실행 (DynamoDB 없으면 state.json으로 자동 fallback)
python lambda_function.py
```

## 보안 설정

### Git 커밋 시 시크릿 유출 방지

```bash
# pre-commit 설치 (최초 1회)
pip install pre-commit detect-secrets
detect-secrets scan > .secrets.baseline
pre-commit install
```

이후 커밋 시 API 키·토큰 등 민감정보가 자동으로 차단됩니다.

### 절대 커밋 금지 파일
- `.env` (API 키 포함)
- `credentials`, `*.pem`, `*.key`
- `state.json` (실행 상태)

## 주의사항

- Twitter API Basic 플랜 이상 필요 (월 $100)
- Gemini API 무료 티어: 분당 5회 제한 → Lambda 타임아웃(5분) 내 최대 20건 처리
- Lambda 최대 실행시간: 15분 / 설정: 5분 (`MAX_TWEETS_PER_RUN`으로 조정)

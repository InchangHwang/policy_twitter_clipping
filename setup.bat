@echo off
echo [1/3] 가상환경 생성 중...
python -m venv venv
call venv\Scripts\activate

echo [2/3] 패키지 설치 중...
pip install -r requirements.txt

echo [3/3] 완료!
echo .env 파일에 크리덴셜을 입력한 뒤 아래 명령어로 실행하세요:
echo   venv\Scripts\activate
echo   python main.py
pause

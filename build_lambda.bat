@echo off
echo [1/4] 기존 빌드 파일 정리 중...
if exist build rmdir /s /q build
if exist lambda_package.zip del lambda_package.zip

echo [2/4] 의존성 설치 중 (Lambda 전용)...
mkdir build
pip install ^
  tweepy==4.15.0 ^
  google-generativeai==0.8.3 ^
  requests==2.32.3 ^
  boto3==1.35.0 ^
  --target build --quiet

echo [3/4] 소스코드 복사 중...
copy lambda_function.py build\
copy config.py          build\
copy state_manager.py   build\
copy twitter_collector.py build\
copy gemini_filter.py   build\
copy telegram_sender.py build\
copy accounts.json      build\

echo [4/4] ZIP 파일 생성 중...
powershell -Command "Compress-Archive -Path build\* -DestinationPath lambda_package.zip -Force"

echo.
echo 완료! lambda_package.zip 파일을 AWS 콘솔에 업로드하세요.
echo 파일 크기:
powershell -Command "(Get-Item lambda_package.zip).length / 1MB | ForEach-Object { '{0:N2} MB' -f $_ }"
pause

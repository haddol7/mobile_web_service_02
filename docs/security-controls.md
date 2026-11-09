# 로그인 보호와 AI 사용량 제한

## 로그인 정책

웹 로그인, Django 관리자 로그인과 `/api-token-auth/`의 POST에 같은 제한을 적용한다.

| 기준 | 기본값 |
| --- | --- |
| 같은 IP와 계정의 실패 | 5회 |
| 같은 IP의 전체 실패 | 20회 |
| 실패 집계 구간과 차단 시간 | 15분 |
| 차단 응답 | HTTP 429와 Retry-After |

동시에 들어온 시도도 비밀번호 검사 전에 자리를 예약한다. 성공한 로그인은 해당 IP와 계정의 실패 기록을 초기화하고, 다른 계정의 실패 기록은 유지한다. 서버 오류는 실패 횟수에서 돌려준다. 로그인 화면 GET과 기존 인증을 사용한 기록 조회는 이 제한의 대상이 아니다. CSRF 검사도 유지한다.

PythonAnywhere에서는 공식 문서에 따라 플랫폼이 덮어쓰는 X-Real-IP를 사용한다. 승인된 PythonAnywhere 설정을 읽는 `deploy.production.load_environment`에서만 이 동작을 기본으로 활성화한다. 직접 실행한 로컬 서버는 REMOTE_ADDR를 사용한다. 임의의 X-Forwarded-For 첫 항목을 신뢰하지 않는다.

출처: [PythonAnywhere 클라이언트 IP 안내](https://help.pythonanywhere.com/pages/WebAppClientIPAddresses)

## AI 정책

| 항목 | 기본값 | 환경변수 |
| --- | --- | --- |
| AI 설명 생성 요청 | 하루 3회 | HISTORY_LLM_DAILY_LIMIT |
| 텍스트 임베딩 요청 | 하루 100회 | HISTORY_EMBEDDING_DAILY_LIMIT |

서버 전체의 실제 외부 요청 시도를 기준으로 집계한다. 한국 시간 자정에 새 날짜의 한도를 적용한다. 공급자 오류나 타임아웃도 한 번의 시도로 계산하며 자동 재시도로 추가 호출하지 않는다. 금액 기준이 아닌 호출 횟수 기준의 상한이다. 입력과 출력의 기존 크기 제한을 함께 유지한다.

캐시된 질문 벡터, 완료된 질문의 재전송과 대화 복원은 새 요청으로 집계하지 않는다. 한도에 도달하면 유료 호출을 멈추고 저장된 기록의 집계와 근거 사진을 반환한다. 답변에는 한도 도달 안내가 표시되며 대화에도 저장된다. 환경변수를 0으로 설정하면 해당 유료 호출을 중지한다. 유효 범위는 0부터 10000까지이며 잘못된 설정은 시작 시 거부한다.

운영자는 `/api/v1/history/usage/`에서 날짜, 한도, 사용 횟수와 남은 횟수를 조회할 수 있다. 이 조회는 운영자 인증이 필요하며 사용량을 차감하지 않는다.

## 저장과 검증

카운터는 기본적으로 비공개 HISTORY_MEDIA_ROOT 아래 `.request-limits.sqlite3`에 저장한다. SECURITY_STATE_ROOT로 위치를 지정할 수도 있다. SQLite 트랜잭션으로 여러 WSGI 작업자의 요청을 직렬화하고 서버 재시작 후에도 기록을 유지한다. 파일은 소유자 전용 0600 권한으로 생성하며 심볼릭 링크는 거부한다. 로그인 키는 비밀키로 HMAC 처리한 값이고 원문 IP, 계정명, 비밀번호와 API 키는 저장하지 않는다.

검증 명령은 WSL 전용 가상환경에서 `python PhotoBlogServer/tools/verify_security.py`다. 임시 카운터 위치를 사용하고 실제 모델 인증을 비활성화한다. 테스트는 동시 요청 상한, 한국 시간 자정, 성공 후 초기화, 관리자와 토큰 로그인, CSRF, 권한, 캐시 재사용과 한도 도달 시 외부 통신 차단을 확인한다. 결과는 `evidence/content/server`에 기록한다.

## 운영 반영

배포 도구는 `tools/deployment/deploy_security_patch.py`다. 기존 공식 API 인증을 재사용해 원격 원본 해시와 변경 범위를 확인하고, 복구용 백업을 검증한 뒤 반영한다. 관리자 비밀번호나 모델 API를 사용한 배포 검사는 수행하지 않는다. 사진과 기존 Django DB 스키마 및 의존성을 유지한다.

실제 반영 결과는 `evidence/security/deployment.json`, 검증된 로컬 패키지는 `evidence/security/deployment-preparation.json`으로 구분한다. 현재 확인된 Wi-Fi 회선의 PythonAnywhere 미국 서버 연결 문제가 해소돼야 운영 반영을 완료할 수 있다.

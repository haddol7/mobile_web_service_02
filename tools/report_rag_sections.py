"""Explain supported RAG guards using real regression outputs and deployed responses."""


def append_rag_sections(doc, *, section, text, figure, data_table, record):
    def heading(title):
        section(doc, title, new_page=False)
        doc.paragraphs[-1].paragraph_format.page_break_before = True

    heading("B33 생성 답변의 날짜 전체 대조")
    figure(doc, "evidence/screenshots/rag-guards-20261110/date-code.png", 5.8,
           "그림 B33 년과 월 및 일을 달력 날짜로 변환해 대조하는 실제 코드")
    text(doc, "생성 답변의 날짜를 하나의 값으로 읽어 현재 조회 결과 facts.dates와 대조한다. 근거가 2026년 11월 10일일 때 같은 숫자를 바꿔 쓴 2026년 10월 11일은 다른 날짜이므로 거절한다. 증빙의 다른 시각이나 사진 ID에 등장한 숫자로 날짜를 허용하지 않는다.")
    text(doc, "YYYY-MM-DD, 슬래시 및 점 구분, 한글 년월일 표현을 처리한다. 연도가 생략된 11월 10일은 근거 날짜에 같은 월일이 있을 때 허용한다. 실제 달력에 없는 날짜와 근거에 없는 날짜는 거절한다. 분석일을 촬영일로 바꾸어 말하는 경우도 구분한다.")
    data_table(doc, ["근거 날짜", "모의 제공자 답변", "검증 결과"], [
        ["2026-11-10", "분석 날짜는 2026년 11월 10일", "허용"],
        ["2026-11-10", "분석 날짜는 2026년 10월 11일", "거절"],
        ["2026-11-10", "분석 날짜는 10월 11일", "거절"],
        ["분석일 2026-11-10", "촬영 날짜는 11월 10일", "거절"]], [1.55, 3.35, 1.0])
    text(doc, "이 표는 WSL에서 모의 제공자 응답을 실제 생성 검증 함수에 통과시킨 결과다. 새 유료 생성의 정답률을 측정한 표와 구분한다. 지원하는 날짜 표현의 사실 대조이며 모든 자연어 주장의 진위를 보장하는 검사는 아니다.", 9)

    heading("B34 부정 조건과 색인 변경 후 검색 범위")
    figure(doc, "evidence/screenshots/rag-guards-20261110/query-scope-code.png", 5.8,
           "그림 B34 촬영 설명 조건을 의미 검색보다 먼저 적용하는 실제 조회 코드")
    text(doc, "인물과 날짜를 제한한 DB 자료에 촬영 설명 조건을 먼저 적용한다. 이후 의미 검색을 수행하므로 색인이 오래됐거나 없는 상태에서도 모자 착용 질문은 해당 설명이 있는 촬영 범위를 유지한다. 의미 검색을 이용할 수 없으면 그 상태를 알리고 조건을 유지한 DB 기록으로 답한다.")
    text(doc, "운영자 확인 상태가 바뀌면 임베딩 문서 지문도 달라질 수 있다. 격리 DB에서는 모자 촬영을 조회한 뒤 확인 상태를 바꾸어 색인 변경 상태를 만들었다. 같은 질문이 계속 모자 촬영 한 건만 반환하는지 확인했다. 이 검사는 실제 운영 자료를 수정하는 절차와 구분한다.")
    text(doc, "모자를 착용하지 않은 촬영이나 모자 쓴 촬영은 제외 같은 부정 조건을 긍정 조건으로 바꾸어 검색하지 않는다. 현재 촬영 설명만으로 확정하기 어려운 조건은 needs_clarification 상태와 구체적인 조건을 요청하는 안내로 처리한다. 이때 임베딩과 답변 생성 요청도 생략한다.")
    data_table(doc, ["입력 또는 상태", "최종 처리"], [
        ["모자 착용, 색인 정상", "모자 설명이 있는 촬영 안에서 의미 검색"],
        ["모자 착용, 확인 후 색인 변경", "모자 설명이 있는 DB 출처 1건 유지"],
        ["모자 착용, 색인 누락", "모자 설명이 있는 DB 출처 1건 유지"],
        ["미착용 또는 제외 조건", "조건 확인 안내, 유료 호출 0회"]], [3.0, 2.9])

    heading("B35 RAG 회귀 사례 실행 결과")
    proof = record("evidence/history/rag-guard-improvement-20261110.json")
    assert proof["pass"] and len(proof["checks"]) == 8 and proof["real_provider_calls"] == 0
    figure(doc, "evidence/screenshots/rag-guards-20261110/guard-tests.png", 5.8,
           "그림 B35 두 검증 절차에서 여덟 사례를 확인한 실제 WSL 실행 로그")
    data_table(doc, ["검증 묶음", "사례 수", "실제 확인 결과"], [
        ["날짜 전체 대조와 날짜 기준", "4", "정상 날짜 허용, 잘못된 날짜와 촬영일 전환 거절"],
        ["부정 및 제외 질문", "2", "조건 확인 안내, 근거 출처 0개"],
        ["확인 후 색인 변경과 누락", "2", "모자 설명의 출처 1개 유지"]], [1.8, .75, 3.35])
    text(doc, "전체 여덟 사례는 모두 예상 결과와 일치했다. 출력의 Ran 2 tests는 날짜와 DB 조회의 두 검증 절차를 뜻하며 각 절차가 여러 입력을 검사한다. 실제 외부 전송 함수는 모의 처리했고 DB는 격리된 시험 자료를 사용했다. 전체 Django 검사 302개와 HTTP 15개 결과는 B31에 제시했다.")
    text(doc, "실행 명령  WSL 가상환경에서 python tools/verify_rag_guards.py\n원본 결과  evidence/history/rag-guard-improvement-20261110.json\n이번 보완의 추가 유료 임베딩 및 생성 요청은 각각 0회다.", 9)

    heading("B36 운영 서버의 검색 조건 확인")
    cloud = record("evidence/history/rag-guard-cloud-20261110.json")
    assert cloud["pass"] and len(cloud["checks"]) == 4
    figure(doc, "evidence/screenshots/rag-guards-20261110/cloud-result.png", 5.8,
           "그림 B36 실제 운영 API 응답 저장본의 조건 확인 안내 부분")
    data_table(doc, ["운영 확인 요청", "조회 방식", "출처 수", "결과"], [
        ["하대진의 모자 착용 촬영", "저장 벡터", "1", "해당 촬영만 반환"],
        ["모자를 착용하지 않은 촬영", "조건 확인", "0", "구체적 조건 안내"],
        ["모자 쓴 촬영은 제외", "조건 확인", "0", "구체적 조건 안내"],
        ["하대진의 모자 착용 촬영", "DB 조건 조회", "1", "해당 촬영만 반환"]], [2.8, 1.0, .65, 1.45])
    text(doc, "수정한 소스를 PythonAnywhere에 반영한 뒤 HTTPS API에서 확인했다. 네 요청 모두 cache_only=true와 generate=false로 보냈다. 저장된 벡터를 재사용하거나 DB 조건으로 조회했고 반환된 api_requests는 모두 0이었다. 요청은 6초 이상 간격으로 보냈다.")
    text(doc, "이 화면은 운영 API의 실제 응답을 저장해 로컬 읽기 전용 브라우저로 연 검토 자료다. 새 LLM 답변 생성과 구분하며 기존 생성 예시는 B28, 최종 배포 후의 추가 생성은 B37에 있다. 조건 변경과 색인 누락에 대한 검증은 B35의 격리 DB 사례다.\n운영 응답 원본  evidence/history/rag-guard-cloud-20261110.json", 9)

    proof = record("evidence/history/final-release-generation-20261110.json")
    assert proof["pass"] and proof["generation_http_attempts"] == 1
    assert proof["new_embedding_api_requests"] == 0
    section(doc, "B37 최종 배포본의 실제 AI 답변")
    text(doc, "최종 RAG 배포본의 운영 코드 네 파일을 검증 소스와 대조한 뒤 하대진의 모자 착용 촬영을 질문했다. 아래는 실제 새 답변을 저장한 운영 대화 화면이다.")
    figure(doc, "evidence/screenshots/final-release-rag-20261110/actual-generated-answer.png", 6.1,
           "그림 B37 최종 RAG 배포본에서 실제 생성한 답변과 근거 사진")
    text(doc, "실제 답변  " + proof["response"]["llm"]["text"], 9.5)
    data_table(doc, ["확인 항목", "실제 결과"], [
        ["답변 상태", "generated, 실제 제공자 응답"],
        ["출처와 날짜", "모자 착용 촬영 1건, 2026년 11월 10일"],
        ["인용과 표시 사진", "선택한 출처의 대표 사진 1장과 인용 ID 일치"],
        ["임베딩 API", "저장된 질문 벡터 재사용, 신규 호출 0회"],
        ["추가 생성", "1회, 일일 사용량 4회에서 5회"],
        ["대화 저장", "새 대화에 질문과 답변 한 건 저장, 재조회 일치"]], [1.35, 4.55])
    text(doc, "모자 촬영의 관측 사진 두 장 중 대표 근거 한 장을 표시한 결과이며 사람 수나 방문 횟수를 뜻하지 않는다. 답변의 날짜, 출처, 확인 인물과 인용 사진을 반환 기록 및 실제 화면과 대조했다. 이 한 질문의 검증으로 일반 답변 정확도를 보장하지 않는다.", 9)
    reference = text(doc, "최종 운영 패치  " + proof["active_release_after"]["release"] + "\n원본 요청과 응답  evidence/history/final-release-generation-20261110.json", 9)
    reference.paragraph_format.keep_together = True

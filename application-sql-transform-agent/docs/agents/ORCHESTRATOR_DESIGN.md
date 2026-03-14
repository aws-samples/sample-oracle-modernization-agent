# Orchestrator Agent Design Document

## 1. Agent 개요

### 1.1 목적
- **주요 목표**: 대화형 파이프라인 제어, 상태 모니터링, 단일 SQL 관리를 통한 전체 마이그레이션 프로세스 통합 관리
- **사용자**: Oracle → PostgreSQL 마이그레이션 수행 팀
- **사용 시나리오**: 
  - 전체 파이프라인 자동 실행 및 제어
  - 실시간 진행 상황 모니터링
  - 단계별 재실행 및 에러 복구
  - 키워드 기반 SQL 검색 및 개별 테스트
  - 전략 압축 및 최적화

### 1.2 입력/출력
```
입력: 
  - 사용자 대화형 명령 (자연어)
  - 파이프라인 상태 정보 (DB)
  - 각 Agent 실행 결과

출력: 
  - 파이프라인 실행 결과
  - 실시간 진행률 표시
  - 에러 진단 및 복구 제안
  - SQL 검색 및 테스트 결과
```

### 1.3 성공 기준
- [x] 자연어 명령을 파이프라인 작업으로 변환
- [x] 전체 파이프라인 자동 실행 (analyze → transform → review → validate → test → merge)
- [x] 실시간 상태 모니터링 및 진행률 표시
- [x] 단계별 재실행 및 에러 복구
- [x] 키워드 기반 SQL 검색 및 개별 관리
- [x] 전략 압축 및 최적화 제어

---

## 2. 아키텍처

### 2.1 전체 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                  🎯 Orchestrator Agent (대화형)                   │
│                                                                  │
│  "전체 파이프라인 실행해줘"  "변환 단계 재수행해줘"                │
│  "User 관련 SQL 테스트해봐"  "전략 압축해줘"                      │
│  "변환 결과 비교해줘" (ReviewManager 위임)                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┬────────────┬──────────┐
        ▼                ▼                ▼            ▼          ▼
   ┌─────────┐     ┌─────────┐  ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Analyze │  →  │Transform│→ │ Review  │→│Validate │→│  Test   │→ Merge
   │+Strategy│     │  Agent  │  │(다관점) │ │  Agent  │ │  Agent  │
   └─────────┘     └─────────┘  └─────────┘ └─────────┘ └─────────┘
        │                │                │            │            │
        ▼                ▼                ▼            ▼            ▼
   Mapper 스캔      패턴 분석        AI 자동 변환   품질 검증    DB 실행 테스트
   SQL ID 추출     전략 생성        배치 처리      Syntax+Equiv  에러 자동 수정
                   학습 & 압축                     구체적 피드백  전략 보강

                         ↓ (delegate)
                  ┌─────────────┐
                  │ReviewManager│
                  │   Agent     │
                  └─────────────┘
                         │
                         ▼
                  Diff Tools
                  SQL 비교/승인
```

### 2.2 Orchestrator 워크플로우

```
┌──────────────────────────────────────────────────────────────────┐
│  Phase 1: 명령 해석 및 라우팅                                     │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ 자연어 명령 분석         │
              │ - 의도 파악              │
              │ - 파라미터 추출          │
              │ - 작업 타입 결정         │
              └────────┬────────────────┘
                       │
                       ▼
              ┌─────────────────────────┐
              │ 작업 라우팅              │
              │ - 파이프라인 실행        │
              │ - 상태 확인              │
              │ - 단계 재실행            │
              │ - SQL 검색/테스트        │
              │ - 전략 관리              │
              └────────┬────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Phase 2: 파이프라인 제어                                         │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ 환경 설정 확인           │
              │ - setup.json 존재        │
              │ - DB 접속 가능           │
              │ - 필수 디렉토리 존재     │
              └────────┬────────────────┘
                       │
                       ▼
              ┌─────────────────────────┐
              │ 단계별 실행              │
              │ - 의존성 체크            │
              │ - 병렬 처리 제어         │
              │ - 에러 처리 및 복구      │
              │ - 진행률 실시간 표시     │
              └────────┬────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Phase 3: 모니터링 및 관리                                        │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ 상태 모니터링            │
              │ - 실시간 진행률          │
              │ - 에러 감지 및 알림      │
              │ - 성능 메트릭 수집       │
              └────────┬────────────────┘
                       │
                       ▼
              ┌─────────────────────────┐
              │ 결과 보고 및 제안        │
              │ - 성공/실패 요약         │
              │ - 다음 단계 제안         │
              │ - 최적화 권장사항        │
              └─────────────────────────┘
```

### 2.3 디렉토리 구조

```
src/agents/orchestrator/
├── agent.py                        # Agent 메인
├── prompt.md                       # Agent 프롬프트
├── schemas.py                      # TypedDict 스키마 정의
├── README.md                       # Agent 설명
└── tools/
    ├── __init__.py
    ├── orchestrator_tools.py       # Orchestrator 14 tools (StateManager 사용)

src/agents/review_manager/
├── agent.py                        # Agent 메인
├── prompt.md                       # Agent 프롬프트
├── schemas.py                      # TypedDict 스키마 정의
├── README.md                       # Agent 설명
└── tools/
    ├── __init__.py
    └── diff_tools.py               # Diff 5 tools

src/core/
└── state_manager.py                # 중앙화된 상태 관리

src/
├── run_orchestrator.py             # Orchestrator 실행 스크립트
└── run_single_test.py              # 단일 SQL 테스트 스크립트
```

---

## 3. Prompt 설계

### 3.1 핵심 원칙

1. **대화형 제어**: 자연어 명령을 정확한 작업으로 변환
2. **상황 인식**: 현재 파이프라인 상태를 파악하여 적절한 조치 제안
3. **사용자 친화**: 기술적 세부사항을 숨기고 직관적인 인터페이스 제공
4. **에러 복구**: 실패 시 자동 진단 및 복구 방안 제시

### 3.2 명령 해석 가이드 (Prompt에 포함)

```markdown
## 명령 해석 패턴

### 1. 파이프라인 실행 명령
- "전체 파이프라인 실행해줘" → run_full_pipeline()
- "처음부터 다시 실행해줘" → reset_all_steps() + run_full_pipeline()
- "분석부터 시작해줘" → run_pipeline_from('analyze')

### 2. 단계별 제어 명령
- "현재 상태 확인해줘" → check_step_status()
- "변환 단계 재수행해줘" → reset_step('transform') + run_step('transform')
- "테스트만 다시 해줘" → run_step('test', reset=True)

### 3. SQL 관리 명령
- "User 관련 SQL 테스트해봐" → search_sql_ids("User") + 선택 후 run_single_test()
- "UserMapper.xml의 selectUserList 테스트해봐" → run_single_test("UserMapper.xml", "selectUserList")
- "실패한 SQL들 다시 테스트해봐" → get_failed_sqls() + batch_retest()

### 4. 전략 관리 명령
- "전략 압축해줘" → compact_strategy()
- "전략 상태 확인해줘" → check_strategy_status()
- "전략 다시 생성해줘" → regenerate_strategy()

### 5. 상태 확인 명령
- "진행률 보여줘" → show_progress()
- "에러 있나 확인해줘" → check_errors()
- "성능 통계 보여줘" → show_performance_stats()
```

### 3.3 에러 처리 가이드 (Prompt에 포함)

```markdown
## 에러 처리 전략

### 1. 환경 설정 에러
- setup.json 없음 → "환경 설정이 필요합니다. python3 src/run_setup.py 실행해주세요."
- DB 접속 실패 → "DB 접속 정보를 확인해주세요. AWS Parameter Store 설정을 점검하세요."

### 2. 파이프라인 에러
- 단계 의존성 위반 → "이전 단계를 먼저 완료해야 합니다. [단계명] 실행을 제안합니다."
- 병렬 처리 실패 → "Worker 수를 줄여서 재시도하거나 단건 처리로 전환합니다."

### 3. SQL 테스트 에러
- DB 접속 실패 → "PostgreSQL 접속 정보를 확인하고 DB 서버 상태를 점검하세요."
- SQL 구문 에러 → "해당 SQL을 Transform Agent로 재변환하거나 수동 수정을 제안합니다."

### 4. 복구 제안
- 자동 복구 가능 → 즉시 복구 실행
- 수동 개입 필요 → 구체적인 해결 방법 제시
- 대안 방법 제공 → 우회 경로 또는 부분 실행 옵션 제안
```

---

## 4. Tools 설계

### 4.1 Orchestrator Tools (14개)

| Tool | 목적 | 입력 | 출력 |
|------|------|------|------|
| check_setup | 환경 설정 확인 | 없음 | `{status, missing_items, suggestions}` |
| check_step_status | 파이프라인 상태 확인 | 없음 | `{steps: {analyze, transform, validate, test}, progress}` |
| run_step | 단일 단계 실행 | step_name, reset, workers | `{status, duration, results}` |
| reset_step | 단계 초기화 | step_name | `{status, reset_items}` |
| get_summary | 전체 요약 생성 | 없음 | `{overall_status, outputs, reports}` |
| search_sql_ids | SQL ID 검색 | keyword | `{matches: [{mapper, sql_id, type}]}` |
| run_single_test | 단일 SQL 테스트 | mapper_file, sql_id | `{status, test_result, error_details}` |
| transform_single_sql | 단일 SQL 변환 | mapper_file, sql_id | `{status, transformed_sql}` |
| validate_single_sql | 단일 SQL 검증 | mapper_file, sql_id | `{status, validation_result}` |
| test_and_fix_single_sql | 단일 SQL 테스트+수정 | mapper_file, sql_id | `{status, test_result, fixed}` |
| compact_strategy | 전략 압축 | 없음 | `{status, before_size, after_size, reduction}` |
| regenerate_strategy | 전략 재생성 | 없음 | `{status, strategy_file}` |
| show_progress | 진행률 표시 | 없음 | `{overall_progress, step_details, eta}` |
| delegate_to_review_manager | ReviewManager 위임 | user_request | ReviewManager의 응답 |

**특징**:
- StateManager를 통한 중앙화된 DB 접근
- TypedDict 기반 타입 안전성
- 직접 DB 호출 최소화 (34 → 29개)

### 4.2 ReviewManager Tools (5개)

ReviewManager Agent가 독립적으로 제공하는 도구:

| Tool | 목적 | 입력 | 출력 |
|------|------|------|------|
| show_sql_diff | SQL 비교 표시 | mapper_file, sql_id | Oracle vs PostgreSQL Diff |
| generate_diff_report | 변환 리포트 생성 | mapper_file (선택) | Markdown 리포트 |
| get_review_candidates | 검토 대상 조회 | filter | `{candidates: [{mapper, sql_id}]}` |
| approve_conversion | 변환 승인 | mapper_file, sql_id, note | `{status, approved}` |
| suggest_revision | 수정 제안 적용 | mapper_file, sql_id, suggestion | `{status, revised}` |

**특징**:
- Orchestrator로부터 완전히 독립
- Diff 작업 전문화
- TypedDict 기반 타입 안전성

### 4.2 check_setup 상세

**목적**: 환경 설정 완료 여부 확인

**로직**:
```python
1. setup.json 파일 존재 확인
2. 필수 디렉토리 존재 확인 (output/, logs/, reports/)
3. AWS 자격 증명 확인
4. DB 접속 테스트 (Oracle, PostgreSQL)
5. Java 환경 확인 (SQL 테스트용)
```

**출력 예시**:
```json
{
  "status": "incomplete",
  "missing_items": [
    "PostgreSQL connection failed",
    "Java not found in PATH"
  ],
  "suggestions": [
    "Check PostgreSQL server status",
    "Install Java 11+ or update PATH"
  ]
}
```

### 4.3 check_step_status 상세

**목적**: 각 파이프라인 단계의 진행 상황 확인

**로직**:
```python
1. DB에서 각 단계별 완료 상태 조회
2. 파일 시스템에서 결과 파일 확인
3. 진행률 계산 (완료/전체)
4. 다음 실행 가능한 단계 판단
```

**출력 예시**:
```json
{
  "steps": {
    "analyze": {"status": "completed", "timestamp": "2026-02-14 15:00:00"},
    "strategy": {"status": "completed", "timestamp": "2026-02-14 15:05:00"},
    "transform": {"status": "partial", "progress": "45/86", "timestamp": "2026-02-14 15:30:00"},
    "validate": {"status": "partial", "progress": "45/86", "timestamp": "2026-02-14 15:45:00"},
    "test": {"status": "partial", "progress": "40/70", "timestamp": "2026-02-14 16:00:00"},
    "merge": {"status": "not_started"}
  },
  "overall_progress": "65%",
  "next_action": "Continue transform step or run test step"
}
```

### 4.4 run_step 상세

**목적**: 특정 파이프라인 단계 실행

**파라미터**:
- `step_name`: 'analyze', 'strategy', 'transform', 'review', 'validate', 'test', 'merge'
- `reset`: True/False (단계 초기화 후 실행)
- `workers`: 병렬 처리 수 (기본 8)

**로직**:
```python
1. 단계별 스크립트 매핑
   - analyze → run_source_analyzer.py
   - strategy → run_strategy.py
   - transform → run_sql_transform.py
   - review → run_sql_review.py
   - validate → run_sql_validate.py
   - test → run_sql_test.py
   - merge → run_sql_merge.py

2. 의존성 체크
   - transform: analyze 완료 필요
   - review: transform 완료 필요
   - validate: review 완료 필요
   - test: validate 완료 필요
   - merge: test 완료 필요

3. 스크립트 실행
   - subprocess로 실행
   - 실시간 로그 출력
   - 에러 캐치 및 처리

4. 결과 수집 및 반환
```

### 4.5 search_sql_ids 상세

**목적**: 키워드로 SQL ID 검색

**파라미터**:
- `keyword`: 검색할 키워드 (대소문자 무시)

**로직**:
```python
1. DB에서 source_xml_list 조회
2. 각 SQL ID에서 키워드 검색
   - SQL ID 이름에서 검색
   - Mapper 파일명에서 검색
   - SQL 내용에서 검색 (선택적)
3. 매칭 결과 정렬 (관련도 순)
```

**출력 예시**:
```json
{
  "keyword": "User",
  "matches": [
    {
      "mapper": "UserMapper.xml",
      "sql_id": "selectUserList",
      "type": "select",
      "match_type": "sql_id",
      "relevance": 100
    },
    {
      "mapper": "UserMapper.xml", 
      "sql_id": "selectUserCount",
      "type": "select",
      "match_type": "sql_id",
      "relevance": 100
    },
    {
      "mapper": "OrderMapper.xml",
      "sql_id": "selectOrderByUser",
      "type": "select", 
      "match_type": "content",
      "relevance": 80
    }
  ]
}
```

### 4.6 run_single_test 상세

**목적**: 특정 SQL ID 개별 테스트

**파라미터**:
- `mapper_file`: Mapper 파일명 (예: "UserMapper.xml")
- `sql_id`: SQL ID (예: "selectUserList")

**로직**:
```python
1. 해당 SQL의 현재 상태 확인
   - 원본 SQL 로드
   - 변환된 SQL 로드 (있는 경우)
   - 이전 테스트 결과 확인

2. 필요 시 변환 수행
   - Transform Agent 호출
   - 변환 결과 저장

3. PostgreSQL 테스트 실행
   - Java 테스트 프로그램 실행
   - 결과 파싱 및 분석

4. 실패 시 자동 수정 시도
   - Test Agent 호출
   - 수정된 SQL 재테스트

5. 결과 반환
```

**출력 예시**:
```json
{
  "status": "success",
  "mapper": "UserMapper.xml",
  "sql_id": "selectUserList",
  "test_result": {
    "execution_time": "0.05s",
    "rows_affected": 0,
    "error": null
  },
  "transformations": [
    "SYSDATE → CURRENT_TIMESTAMP",
    "NVL → COALESCE"
  ]
}
```

### 4.7 compact_strategy 상세

**목적**: 전략 파일 압축 및 최적화

**로직**:
```python
1. 전략 파일 크기 확인
2. 학습 섹션 항목 수 확인
3. 압축 필요성 판단 (>50KB 또는 >5 학습 항목)
4. Strategy Agent의 compact_strategy 호출
5. 압축 결과 반환
```

### 4.8 show_progress 상세

**목적**: 실시간 진행률 및 상태 표시

**로직**:
```python
1. 각 단계별 진행률 계산
2. 전체 진행률 계산 (가중 평균)
3. 예상 완료 시간 계산 (ETA)
4. 시각적 진행률 바 생성
```

**출력 예시**:
```json
{
  "overall_progress": 65,
  "step_details": {
    "analyze": {"progress": 100, "status": "✅ 완료"},
    "strategy": {"progress": 100, "status": "✅ 완료"},
    "transform": {"progress": 52, "status": "🔄 진행중 (45/86)"},
    "validate": {"progress": 52, "status": "🔄 진행중 (45/86)"},
    "test": {"progress": 57, "status": "🔄 진행중 (40/70)"},
    "merge": {"progress": 0, "status": "⏳ 대기중"}
  },
  "eta": "약 25분 남음",
  "current_activity": "Transform Agent 실행중 (Worker 8개)"
}
```

---

## 5. 데이터 흐름

### 5.1 전체 파이프라인 실행

```
1. 사용자: "전체 파이프라인 실행해줘"
   ↓
2. check_setup()
   → {status: "ready", missing_items: []}
   ↓
3. check_step_status()
   → {steps: {analyze: "not_started", ...}, overall_progress: "0%"}
   ↓
4. run_step('analyze')
   → {status: "success", duration: "30s", results: {total_mappers: 11, total_sqls: 86}}
   ↓
5. run_step('strategy') [자동 실행]
   → {status: "success", duration: "45s", results: {strategy_file: "created"}}
   ↓
6. run_step('transform', workers=8)
   → {status: "success", duration: "8m", results: {transformed: 86, failed: 0}}
   ↓
7. run_step('review', workers=8)  # 다관점 리뷰 (Syntax + Equivalence 병렬)
   → {status: "success", duration: "4m", results: {reviewed: 86, failed: 3, retransformed: 3}}
   ↓
8. run_step('validate', workers=8)
   → {status: "success", duration: "5m", results: {validated: 86, failed: 3}}
   ↓
9. run_step('test', workers=8)
   → {status: "success", duration: "12m", results: {tested: 70, passed: 65, failed: 5}}
   ↓
10. run_step('merge')
   → {status: "success", duration: "1m", results: {merged_files: 11}}
   ↓
11. 최종 보고서 생성 및 표시
```

### 5.2 단일 SQL 테스트

```
1. 사용자: "User 관련 SQL 테스트해봐"
   ↓
2. search_sql_ids("User")
   → {matches: [
       {mapper: "UserMapper.xml", sql_id: "selectUserList", type: "select"},
       {mapper: "UserMapper.xml", sql_id: "selectUserCount", type: "select"},
       {mapper: "UserMapper.xml", sql_id: "selectUserDetail", type: "select"}
     ]}
   ↓
3. 사용자에게 선택 옵션 제시
   ↓
4. 사용자: "selectUserList"
   ↓
5. run_single_test("UserMapper.xml", "selectUserList")
   → 변환 상태 확인
   → 필요 시 Transform Agent 호출
   → PostgreSQL 테스트 실행
   → {status: "success", test_result: {...}}
```

### 5.3 에러 복구 시나리오

```
1. 파이프라인 실행 중 Transform 단계 실패
   ↓
2. check_errors()
   → {errors: [{step: "transform", type: "timeout", message: "Worker timeout"}]}
   ↓
3. 자동 복구 시도
   - Worker 수 감소 (8 → 4)
   - 타임아웃 증가
   - 실패한 배치만 재실행
   ↓
4. 복구 실패 시 사용자에게 옵션 제시
   - 단건 처리로 전환
   - 수동 개입 필요한 SQL 건너뛰기
   - 전체 재시작
```

### 5.4 전략 관리

```
1. 사용자: "전략 압축해줘"
   ↓
2. 전략 파일 상태 확인
   → 파일 크기: 52KB, 학습 항목: 7개
   ↓
3. compact_strategy()
   → Strategy Agent 호출
   → 중복 제거 및 일반화
   → {status: "success", before_size: "52KB", after_size: "18KB", reduction: "65%"}
   ↓
4. 압축 결과 보고
```

---

## 6. 사용 예시

### 6.1 기본 파이프라인 실행

```bash
# Orchestrator 시작
python3 src/run_orchestrator.py
```

**대화 예시**:
```
🤖 OMA Orchestrator에 오신 것을 환영합니다!
   Oracle → PostgreSQL 마이그레이션을 도와드리겠습니다.

⚛️  > 전체 파이프라인 실행해줘

🤖 > 환경 설정을 확인하겠습니다...
   ✅ setup.json 존재
   ✅ AWS 자격 증명 확인
   ✅ Oracle DB 접속 가능
   ✅ PostgreSQL DB 접속 가능
   ✅ Java 환경 확인
   
   파이프라인을 시작합니다...
   
   📊 Step 1: Source Analysis
   ⏳ Mapper XML 파일 스캔 중...
   ✅ 완료 (30초) - 11개 Mapper, 86개 SQL 발견
   
   📋 Step 2: Strategy Generation  
   ⏳ SQL 패턴 분석 및 전략 생성 중...
   ✅ 완료 (45초) - 프로젝트별 전략 생성됨
   
   🔄 Step 3: SQL Transform (8 workers)
   ⏳ Oracle → PostgreSQL 변환 중... [████████████████████] 86/86 (100%)
   ✅ 완료 (8분) - 86개 SQL 변환 완료
   
   ✅ Step 4: Validation (8 workers)
   ⏳ 변환 품질 검증 중... [████████████████████] 86/86 (100%)
   ⚠️  완료 (5분) - 83개 성공, 3개 재변환됨
   
   🧪 Step 5: Database Test (8 workers)
   ⏳ PostgreSQL 실행 테스트 중... [██████████████████  ] 65/70 (93%)
   ⚠️  완료 (12분) - 65개 성공, 5개 수정됨
   
   📦 Step 6: XML Merge
   ⏳ 최종 Mapper XML 생성 중...
   ✅ 완료 (1분) - 11개 파일 생성됨
   
   🎉 파이프라인 완료! 총 소요시간: 26분 30초
   
   📊 최종 결과:
   - 총 SQL: 86개
   - 성공: 81개 (94.2%)
   - 수동 검토 필요: 5개 (5.8%)
   
   📁 결과 파일:
   - 변환된 XML: output/mapper/
   - 상세 보고서: reports/migration_report.md

⚛️  > 수동 검토 필요한 SQL들 보여줘

🤖 > 수동 검토가 필요한 5개 SQL을 확인했습니다:
   
   1. OrderMapper.xml - selectComplexOrder
      이슈: CONNECT BY 구문이 복잡함
      권장: WITH RECURSIVE로 변환 후 성능 테스트 필요
   
   2. PaymentMapper.xml - calculateCommission  
      이슈: Oracle 특화 함수 사용
      권장: 비즈니스 로직 검토 후 PostgreSQL 함수로 재작성
   
   ...
   
   각 SQL을 개별적으로 테스트하거나 수정하시겠습니까?
```

### 6.2 단계별 제어

```
⚛️  > 현재 상태 확인해줘

🤖 > 📊 현재 파이프라인 상태:
   
   ✅ analyze: 완료 (2026-02-14 15:00:00)
   ✅ strategy: 완료 (2026-02-14 15:05:00)  
   🔄 transform: 진행중 45/86 (52%) - 예상 완료: 5분 후
   ⏳ validate: 대기중
   ⏳ test: 대기중
   ⏳ merge: 대기중
   
   전체 진행률: 35%

⚛️  > 변환 단계 재수행해줘

🤖 > Transform 단계를 초기화하고 재실행하겠습니다.
   
   🔄 기존 변환 결과 초기화 중...
   ✅ 초기화 완료
   
   🔄 Transform 재시작 (8 workers)...
   ⏳ Oracle → PostgreSQL 변환 중... [████████████████████] 86/86 (100%)
   ✅ 완료 (7분 30초) - 86개 SQL 변환 완료
   
   다음 단계(Validate)를 실행하시겠습니까?

⚛️  > 네, 계속 진행해줘

🤖 > ✅ Validate 단계를 시작합니다...
```

### 6.3 SQL 검색 및 테스트

```
⚛️  > User 관련 SQL 테스트해봐

🤖 > "User" 키워드로 검색한 결과:
   
   📁 UserMapper.xml:
   1. selectUserList (select) - 사용자 목록 조회
   2. selectUserCount (select) - 사용자 수 조회  
   3. selectUserDetail (select) - 사용자 상세 조회
   4. insertUser (insert) - 사용자 등록
   5. updateUser (update) - 사용자 수정
   
   📁 OrderMapper.xml:
   6. selectOrderByUser (select) - 사용자별 주문 조회
   
   어떤 SQL을 테스트하시겠습니까? (번호 또는 SQL ID 입력)

⚛️  > selectUserList

🤖 > UserMapper.xml의 selectUserList를 테스트하겠습니다...
   
   🔍 현재 상태 확인:
   - 원본 SQL: 존재 ✅
   - 변환된 SQL: 존재 ✅  
   - 이전 테스트: 성공 ✅
   
   🧪 PostgreSQL 테스트 실행:
   ⏳ 테스트 중...
   ✅ 성공! (실행시간: 0.05초)
   
   🔄 적용된 변환:
   - SYSDATE → CURRENT_TIMESTAMP
   - NVL(a.name, 'Unknown') → COALESCE(a.name, 'Unknown')
   - FROM users a, user_roles b WHERE a.id = b.user_id
     → FROM users a INNER JOIN user_roles b ON a.id = b.user_id
   
   다른 SQL도 테스트하시겠습니까?

⚛️  > OrderMapper.xml의 selectOrderByUser도 테스트해봐

🤖 > OrderMapper.xml의 selectOrderByUser를 테스트하겠습니다...
   
   🔍 현재 상태 확인:
   - 원본 SQL: 존재 ✅
   - 변환된 SQL: 없음 ❌
   
   🔄 Transform Agent로 변환 수행:
   ⏳ 변환 중...
   ✅ 변환 완료
   
   🧪 PostgreSQL 테스트 실행:
   ⏳ 테스트 중...
   ❌ 실패: column "user_id" must appear in the GROUP BY clause
   
   🔧 Test Agent로 자동 수정:
   ⏳ 수정 중...
   ✅ 수정 완료 - GROUP BY 절에 user_id 추가
   
   🧪 재테스트:
   ⏳ 테스트 중...
   ✅ 성공! (실행시간: 0.12초)
   
   수정된 SQL이 전략에 학습되었습니다.
```

### 6.4 전략 관리

```
⚛️  > 전략 압축해줘

🤖 > 전략 파일 상태를 확인하겠습니다...
   
   📊 현재 전략 파일:
   - 파일 크기: 52KB
   - 학습 항목: 7개
   - 마지막 업데이트: 2026-02-14 16:30:00
   
   💡 압축이 권장됩니다 (50KB 초과)
   
   🗜️ 전략 압축 시작:
   ⏳ 학습 패턴 분석 중...
   ⏳ 중복 패턴 제거 중...
   ⏳ 패턴 일반화 중...
   ⏳ 누적 요약 생성 중...
   
   ✅ 압축 완료!
   
   📊 압축 결과:
   - 압축 전: 52KB
   - 압축 후: 18KB  
   - 감소율: 65%
   - 학습 항목: 7개 → 3개 카테고리로 통합
   
   압축된 전략이 더 효율적으로 Transform Agent에 적용됩니다.

⚛️  > 전략 상태 확인해줘

🤖 > 📋 전략 상태 요약:
   
   📁 전략 파일: output/strategy/transform_strategy.md
   - 크기: 18KB (최적화됨 ✅)
   - 생성일: 2026-02-14 16:00:00
   - 마지막 압축: 2026-02-14 16:45:00
   
   📊 프로젝트 특성:
   - 총 SQL: 86개 (11개 Mapper)
   - 주요 패턴: SYSDATE (45.3%), Comma Join (81.4%)
   - 복잡도: Medium 50%, Complex 37.2%
   
   📚 학습 내역:
   - XML 이스케이프 패턴 (3건)
   - GROUP BY 절 누락 패턴 (2건)  
   - 타입 캐스팅 패턴 (2건)
   
   전략이 최신 상태이며 효과적으로 적용되고 있습니다.
```

---

## 7. 다른 Agent와의 연계

### 7.1 Agent 간 통신 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                           │
│                   (중앙 제어 및 조정)                             │
└─────────────────────────┬───────────────────────────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    │                     │                     │
    ▼                     ▼                     ▼
┌─────────┐          ┌─────────┐          ┌─────────┐
│ Source  │          │Strategy │          │Transform│
│Analyzer │    ←→    │ Agent   │    ←→    │ Agent   │
│ Agent   │          │         │          │         │
└─────────┘          └─────────┘          └─────────┘
    │                     │                     │
    │                     │                     │
    ▼                     ▼                     ▼
┌─────────┐          ┌─────────┐          ┌─────────┐
│Validate │          │  Test   │          │ Merge   │
│ Agent   │    ←→    │ Agent   │    ←→    │ Agent   │
│         │          │         │          │         │
└─────────┘          └─────────┘          └─────────┘
```

### 7.2 각 Agent와의 연계 방식

#### 7.2.1 Source Analyzer Agent
**연계 방식**: 스크립트 실행 + DB 상태 확인
```python
# Orchestrator → Source Analyzer
run_step('analyze'):
  subprocess.run(['python3', 'src/run_source_analyzer.py'])
  
# Source Analyzer → Orchestrator  
DB 테이블 업데이트:
  - source_xml_list: 스캔된 Mapper 정보
  - sql_analysis: SQL 복잡도 분석 결과
```

**데이터 흐름**:
- **입력**: Java 소스 경로 (setup.json)
- **출력**: DB 테이블 (source_xml_list), 분석 보고서
- **Orchestrator 역할**: 실행 제어, 진행률 모니터링, 에러 처리

#### 7.2.2 Strategy Agent  
**연계 방식**: 자동 실행 + 수동 호출
```python
# 자동 실행 (Analyze 완료 후)
run_step('analyze') 완료 시:
  자동으로 run_step('strategy') 호출
  
# 수동 호출 (전략 압축)
compact_strategy():
  Strategy Agent의 compact_strategy 도구 호출
```

**데이터 흐름**:
- **입력**: source_xml_list (DB), 일반 규칙 파일
- **출력**: transform_strategy.md, 학습 내역
- **Orchestrator 역할**: 자동 실행 제어, 압축 관리, 전략 상태 모니터링

#### 7.2.3 Transform Agent
**연계 방식**: 배치 실행 + 단건 실행
```python
# 배치 실행
run_step('transform', workers=8):
  subprocess.run(['python3', 'src/run_sql_transform.py', '--workers', '8'])
  
# 단건 실행 (단일 SQL 테스트 시)
run_single_test(mapper, sql_id):
  Transform Agent 직접 호출하여 해당 SQL만 변환
```

**데이터 흐름**:
- **입력**: source_xml_list (DB), transform_strategy.md
- **출력**: 변환된 SQL (DB), 변환 보고서
- **Orchestrator 역할**: 병렬 처리 제어, 실패 시 재시도, 단일 SQL 변환 요청

#### 7.2.4 Validate Agent
**연계 방식**: 배치 실행 + 실패 패턴 학습
```python
# 배치 실행
run_step('validate', workers=8):
  subprocess.run(['python3', 'src/run_sql_validate.py', '--workers', '8'])
  
# 실패 패턴 학습
validate 완료 후:
  실패 로그 파싱하여 Strategy Agent에 학습 데이터 전달
```

**데이터 흐름**:
- **입력**: 변환된 SQL (DB)
- **출력**: 검증 결과 (DB), 실패 패턴 로그
- **Orchestrator 역할**: 실행 제어, 실패 패턴 수집, 전략 학습 트리거

#### 7.2.5 Test Agent
**연계 방식**: 2단계 실행 + 자동 수정
```python
# Phase 1: 일괄 테스트
run_step('test', workers=8):
  Java 프로그램으로 모든 SQL 일괄 실행
  
# Phase 2: 실패건 개별 수정
실패한 SQL들에 대해:
  Test Agent 호출하여 개별 수정
  수정된 SQL 재테스트
```

**데이터 흐름**:
- **입력**: 검증된 SQL (DB), PostgreSQL 접속 정보
- **출력**: 테스트 결과 (DB), 수정된 SQL, 실패 패턴 로그
- **Orchestrator 역할**: 2단계 실행 제어, 자동 수정 관리, 전략 학습 트리거

#### 7.2.6 Merge Agent
**연계 방식**: 최종 조립 실행
```python
# 최종 XML 조립
run_step('merge'):
  subprocess.run(['python3', 'src/run_sql_merge.py'])
```

**데이터 흐름**:
- **입력**: 테스트 완료된 SQL (DB)
- **출력**: 최종 Mapper XML 파일들
- **Orchestrator 역할**: 실행 제어, 결과 파일 확인

### 7.3 상태 동기화

#### 7.3.1 DB 기반 상태 관리
```sql
-- 각 Agent가 업데이트하는 상태 테이블
CREATE TABLE pipeline_status (
    step_name VARCHAR(20) PRIMARY KEY,
    status VARCHAR(20),           -- 'not_started', 'running', 'completed', 'failed'
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    progress_current INTEGER,
    progress_total INTEGER,
    error_message TEXT
);

-- SQL별 상세 상태
CREATE TABLE sql_status (
    mapper_file VARCHAR(100),
    sql_id VARCHAR(100),
    step_name VARCHAR(20),
    status VARCHAR(20),
    error_message TEXT,
    updated_at TIMESTAMP,
    PRIMARY KEY (mapper_file, sql_id, step_name)
);
```

#### 7.3.2 실시간 진행률 추적
```python
# Orchestrator가 실시간으로 모니터링
def monitor_progress():
    while True:
        status = check_step_status()
        display_progress_bar(status)
        
        if status['current_step'] == 'completed':
            break
            
        time.sleep(5)  # 5초마다 업데이트
```

### 7.4 에러 전파 및 복구

#### 7.4.1 에러 전파 체인
```
Agent 실행 실패
    ↓
Orchestrator 에러 감지
    ↓
에러 타입 분석
    ↓
자동 복구 시도
    ↓
복구 실패 시 사용자에게 옵션 제시
```

#### 7.4.2 복구 전략
```python
# Transform Agent 실패 시
if transform_failed:
    # 1. Worker 수 감소하여 재시도
    retry_with_fewer_workers()
    
    # 2. 실패한 배치만 재실행
    retry_failed_batches()
    
    # 3. 단건 처리로 전환
    switch_to_single_processing()

# Test Agent 실패 시  
if test_failed:
    # 1. PostgreSQL 접속 확인
    check_postgresql_connection()
    
    # 2. 실패한 SQL만 재테스트
    retest_failed_sqls()
    
    # 3. 수동 검토 플래그 설정
    mark_for_manual_review()
```

### 7.5 성능 최적화

#### 7.5.1 병렬 처리 조정
```python
# 시스템 리소스에 따른 Worker 수 자동 조정
def optimize_workers():
    cpu_count = os.cpu_count()
    memory_gb = get_memory_size()
    
    # CPU 기반 조정
    max_workers = min(cpu_count, 8)
    
    # 메모리 기반 조정 (Agent당 1GB 가정)
    max_workers = min(max_workers, memory_gb)
    
    return max_workers
```

#### 7.5.2 캐싱 전략
```python
# 전략 파일 캐싱
strategy_cache = {}

def get_strategy():
    if 'transform_strategy' not in strategy_cache:
        strategy_cache['transform_strategy'] = load_strategy_file()
    return strategy_cache['transform_strategy']

# DB 연결 풀링
connection_pool = create_connection_pool()
```

### 7.6 로깅 및 모니터링

#### 7.6.1 통합 로깅
```python
# 모든 Agent의 로그를 중앙 집중
logging.config.dictConfig({
    'handlers': {
        'orchestrator': {
            'filename': 'logs/orchestrator.log'
        },
        'agents': {
            'filename': 'logs/agents.log'  
        }
    }
})
```

#### 7.6.2 메트릭 수집
```python
# 성능 메트릭 수집
metrics = {
    'total_sqls': 86,
    'processing_time': {
        'analyze': 30,      # seconds
        'transform': 480,   # seconds  
        'validate': 300,    # seconds
        'test': 720,        # seconds
        'merge': 60         # seconds
    },
    'success_rate': {
        'transform': 100.0,  # %
        'validate': 96.5,    # %
        'test': 92.9         # %
    }
}
```

---

**문서 버전**: 1.2
**작성일**: 2026-02-14
**최종 업데이트**: 2026-03-03
**작성자**: OMA Development Team
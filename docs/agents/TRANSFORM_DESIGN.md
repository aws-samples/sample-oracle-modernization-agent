# SQL Transform Agent Design Document

## 1. Agent 개요

### 1.1 목적
- **주요 목표**: MyBatis Mapper XML 내 Oracle SQL을 PostgreSQL로 AI 기반 자동 변환
- **사용자**: Oracle → PostgreSQL 마이그레이션 수행 팀
- **사용 시나리오**: 
  - Source Analyzer 및 Strategy Agent 실행 후
  - 분석된 Mapper XML과 생성된 전략을 기반으로 SQL 변환 수행
  - 배치 처리로 비용 효율적 변환
  - General Rules에 없는 Oracle 구문도 전문가 판단으로 변환

### 1.2 입력/출력
```
입력: 
  - 원본 Mapper XML 파일 (DB의 source_xml_list)
  - 일반 변환 규칙 (src/reference/oracle_to_postgresql_rules.md)
  - 프로젝트 전략 (output/strategy/transform_strategy.md)
  - PostgreSQL 메타데이터 (pg_metadata 테이블)

출력: 
  - SQL ID별 추출 파일 (output/extract/)
  - 변환된 SQL 파일 (output/transform/)
  - 원본 백업 (output/origin/)
  - 변환 진행률 로그 (logs/transform_progress.log)
  - Mapper별 상세 로그 (logs/transform/[Mapper].log)
```

### 1.3 성공 기준
- [x] 모든 Mapper XML의 SQL ID를 개별 추출
- [x] 2-Tier 전략 적용 (일반 규칙 + 프로젝트 전략)
- [x] 배치 처리로 비용 최적화 (3~5개 그룹)
- [x] 실시간 진행률 표시
- [x] 변환 결과 DB 업데이트 (transformed='Y')

---

## 2. 아키텍처

### 2.1 전체 구조

```
┌─────────────────────────────────────────────────────────────┐
│  2-Tier 전략 시스템                                          │
│                                                              │
│  Tier 1: 정적 규칙 (모든 프로젝트 공통)                      │
│  └─ src/reference/oracle_to_postgresql_rules.md            │
│     - NVL → COALESCE                                        │
│     - (+) → LEFT JOIN                                       │
│     - ROWNUM → LIMIT/OFFSET                                 │
│                                                              │
│  Tier 2: 동적 전략 (프로젝트별 특화)                         │
│  └─ output/strategy/transform_strategy.md                  │
│     - 프로젝트 특성 분석                                     │
│     - 변환 우선순위                                          │
│     - 학습 내역 (FIXED 패턴)                                 │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Transform Agent (Claude Sonnet 4.5, max_tokens=64000)      │
│  - Prompt Caching으로 전략 재사용                            │
│  - 배치 처리로 비용 최적화                                   │
│  - PostgreSQL 메타데이터 참조                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 핵심 전략: 배치 처리

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 1: 전처리 (1회)                                        │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ split_mapper()          │
              │ - Mapper XML 파싱        │
              │ - SQL ID별 분리          │
              └────────┬────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    extract/      origin/      DB 등록
    (개별 SQL)    (원본 백업)   (메타데이터)

┌──────────────────────────────────────────────────────────────┐
│  Phase 2: 배치 변환 (병렬 8 Workers)                          │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ 그룹핑 (30KB 이하)       │
              │ - 파일 크기 기준         │
              │ - 3~5개 SQL 묶음         │
              └────────┬────────────────┘
                       │
                       ▼
              ┌─────────────────────────┐
              │ Agent 호출 (배치)        │
              │ - 전략 적용              │
              │ - 메타데이터 참조        │
              │ - 3~5개 동시 변환        │
              └────────┬────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    transform/    DB 업데이트    진행률 로그
    (변환 SQL)    (transformed='Y')  (실시간)
```

### 2.3 배치 처리 이유

#### 비용 효율성 💰
```
개별 처리: 86개 SQL × Agent 호출 = 86번 API 호출
배치 처리: 86/5개 그룹 × Agent 호출 = 17번 API 호출
→ 비용 절감: 약 80%
```

#### 처리 속도 ⚡
- 병렬 8개 Worker로 동시 처리
- 네트워크 오버헤드 최소화
- Agent가 여러 SQL을 한 번에 분석하여 컨텍스트 공유

#### 변환 품질 🎯
- Agent가 같은 Mapper 내 여러 SQL을 함께 보면서 패턴 학습
- 일관된 변환 스타일 유지
- SQL 간 관계 파악 가능

### 2.4 디렉토리 구조

```
src/agents/sql_transform/
├── agent.py                        # Agent 메인
├── prompt.md                       # Agent 프롬프트
├── README.md                       # Agent 설명
└── tools/
    ├── __init__.py
    ├── split_mapper.py             # SQL ID별 분리
    ├── assemble_mapper.py          # XML 재조립
    ├── save_conversion.py          # 변환 결과 저장
    └── metadata_tools.py           # PostgreSQL 메타데이터

output/
├── extract/                        # SQL ID별 추출
│   ├── UserMapper_selectUserList.sql
│   └── ...
├── transform/                      # 변환된 SQL
│   ├── UserMapper_selectUserList.sql
│   └── ...
├── origin/                         # 원본 백업
│   ├── UserMapper.xml
│   └── ...
└── logs/
    ├── transform_progress.log      # 진행률
    └── transform/
        ├── UserMapper.log          # Mapper별 상세
        └── ...
```

---

## 3. Prompt 설계

### 3.1 핵심: 2-Tier 전략 적용

Agent는 변환 규칙을 직접 수행하고, Tool은 파일 I/O만 담당합니다.

```python
# 시스템 프롬프트 구성
system_prompt = f"""
{base_prompt}

## Tier 1: 일반 변환 규칙 (모든 프로젝트 공통)
{read('src/reference/oracle_to_postgresql_rules.md')}

## Tier 2: 프로젝트별 전략 (이 프로젝트 특화)
{read('output/strategy/transform_strategy.md')}

## PostgreSQL 메타데이터
{pg_metadata}
"""
```

### 3.2 변환 규칙 (Tier 1 - 일반)

`src/reference/oracle_to_postgresql_rules.md` 파일에 정의된 4-Phase 변환 규칙을 적용합니다:

- **Phase 1: Structural** - 스키마 제거, Hint 제거, DUAL 제거, DB Link 제거
- **Phase 2: Syntax** - Comma JOIN → 명시적 JOIN, (+) → LEFT/RIGHT JOIN, 서브쿼리 별칭
- **Phase 3: Functions & Operators** - NVL → COALESCE, DECODE → CASE WHEN, 날짜 함수, 정규식, 시퀀스 (40+ 함수)
- **Phase 4: Advanced** - CONNECT BY → WITH RECURSIVE, MERGE → ON CONFLICT, ROWNUM → LIMIT/OFFSET
- **참조 규칙** - Parameter Casting, XML 특수 문자 처리, MyBatis 동적 SQL 보존 (각 Phase에서 적용)

### 3.3 프로젝트 전략 (Tier 2 - 동적)

```markdown
## 프로젝트별 변환 우선순위

### Priority 1: SYSDATE → CURRENT_TIMESTAMP (45.3%)
이 프로젝트에서 가장 빈번한 패턴.

### Priority 2: Comma Join → Explicit JOIN (81.4%)
대부분의 SQL이 comma join 사용.

### Priority 3: Outer Join (+) → LEFT/RIGHT JOIN (40.7%)
Oracle의 (+) 연산자를 명시적 OUTER JOIN으로 변환.

## 학습 내역 (FIXED 패턴)
- XML 이스케이프: < → &lt;, > → &gt; (3건)
- COALESCE 타입 캐스팅: COALESCE(amount, 0::NUMERIC) (2건)
```

### 3.4 Workflow (Prompt에 명시)

```markdown
## Workflow

1. 배치로 받은 SQL 목록 확인 (3~5개)
2. 각 SQL에 대해:
   a. Tier 1 일반 규칙 적용
   b. Tier 2 프로젝트 전략 적용
   c. PostgreSQL 메타데이터 참조 (타입 확인)
   d. MyBatis 태그 보존
   e. XML 이스케이프 적용
3. 변환 결과를 save_conversion() 도구로 저장
4. SELF-CHECK (저장 전 필수 확인):
   - Oracle 잔재 없는지 확인 (NVL, DECODE, SYSDATE, TO_DATE 등)
   - Parameter casting 적용 여부 확인
   - XML escaping (< <=만 escape, > >=는 불필요)
   - MyBatis 태그 무결성
```

---

## 4. Tools 설계

### 4.1 Tool 목록

| Tool | 목적 | 입력 | 출력 |
|------|------|------|------|
| split_mapper | XML → SQL ID 분리 | mapper_file | `{sql_ids: [{id, type, sql}]}` |
| get_pending_transforms | 미변환 SQL 조회 | 없음 | `{pending: [{mapper, sql_id}]}` |
| read_sql_source | SQL 읽기 | mapper_file, sql_id | `{sql_id, sql_content}` |
| save_conversion | 변환 결과 저장 | sql_id, converted_sql, ... | `{status, sql_id}` |
| lookup_column_type | 타입 조회 | table, column | `{table, column, type}` |
| generate_metadata | 메타데이터 생성 | 없음 | `{status, tables_count}` |

### 4.2 split_mapper 상세

**목적**: Mapper XML을 SQL ID별로 분리

**파라미터**:
- `mapper_file`: Mapper XML 파일 경로

**로직**:
```python
1. XML 파싱
2. SQL 태그 추출 (<select>, <insert>, <update>, <delete>)
3. 각 SQL ID별로:
   - extract/[Mapper]_[SQL_ID].sql 저장
   - origin/[Mapper].xml 백업
   - DB에 메타데이터 등록
4. 결과 반환
```

**출력 예시**:
```json
{
  "mapper": "UserMapper.xml",
  "namespace": "user",
  "sql_ids": [
    {
      "id": "selectUserList",
      "type": "select",
      "sql": "SELECT * FROM users WHERE status = 'A'",
      "line_count": 3,
      "extract_path": "output/extract/UserMapper_selectUserList.sql"
    }
  ],
  "total": 8
}
```

### 4.3 get_pending_transforms 상세

**목적**: 아직 변환되지 않은 SQL 목록 조회

**로직**:
```python
1. DB 쿼리: SELECT * FROM transform_target_list WHERE transformed = 'N'
2. 파일 크기 기준으로 그룹핑 (30KB 이하)
3. 그룹 목록 반환
```

**출력 예시**:
```json
{
  "total_pending": 45,
  "groups": [
    {
      "group_id": 1,
      "size_kb": 25,
      "sqls": [
        {"mapper": "UserMapper.xml", "sql_id": "selectUserList"},
        {"mapper": "UserMapper.xml", "sql_id": "selectUserCount"},
        {"mapper": "UserMapper.xml", "sql_id": "selectUserDetail"}
      ]
    },
    {
      "group_id": 2,
      "size_kb": 28,
      "sqls": [
        {"mapper": "OrderMapper.xml", "sql_id": "selectOrderList"},
        {"mapper": "OrderMapper.xml", "sql_id": "selectOrderDetail"}
      ]
    }
  ]
}
```

### 4.4 save_conversion 상세

**목적**: 변환 결과 저장 및 DB 업데이트

**파라미터**:
- `sql_id`: SQL ID
- `mapper_file`: Mapper 파일명
- `converted_sql`: 변환된 SQL
- `conversion_notes`: 변환 노트 (선택)

**로직**:
```python
1. transform/[Mapper]_[SQL_ID].sql 저장
2. DB 업데이트: transformed = 'Y', transform_date = NOW()
3. 진행률 로그 업데이트
4. 결과 반환
```

**출력 예시**:
```json
{
  "status": "saved",
  "sql_id": "selectUserList",
  "mapper": "UserMapper.xml",
  "output_path": "output/transform/UserMapper_selectUserList.sql",
  "progress": "25/86 (29%)"
}
```

### 4.5 lookup_column_type 상세

**목적**: PostgreSQL 메타데이터에서 컬럼 타입 조회

**파라미터**:
- `table_name`: 테이블명
- `column_name`: 컬럼명

**로직**:
```python
1. pg_metadata 테이블 조회
2. 타입 정보 반환
3. 없으면 null 반환
```

**출력 예시**:
```json
{
  "table": "users",
  "column": "created_at",
  "type": "timestamp without time zone",
  "nullable": true,
  "default": "CURRENT_TIMESTAMP"
}
```

---

## 5. 데이터 흐름

### 5.1 전처리 (1회)

```
1. split_mapper('UserMapper.xml')
   → {
       mapper: 'UserMapper.xml',
       sql_ids: [
         {id: 'selectUserList', type: 'select', sql: '...', line_count: 15},
         {id: 'insertUser', type: 'insert', sql: '...', line_count: 5}
       ],
       total: 8
     }

2. generate_metadata()
   → {
       status: 'success',
       tables_count: 25,
       columns_count: 350
     }
```

### 5.2 배치 변환

```
1. get_pending_transforms()
   → {
       total_pending: 45,
       groups: [
         {group_id: 1, size_kb: 25, sqls: [...]},
         {group_id: 2, size_kb: 28, sqls: [...]}
       ]
     }

2. Worker가 Group 1 처리:
   a. read_sql_source('UserMapper.xml', 'selectUserList')
      → {sql_id: 'selectUserList', sql_content: 'SELECT ...'}
   
   b. Agent가 변환 수행 (Tier 1 + Tier 2 전략 적용)
   
   c. lookup_column_type('users', 'created_at')
      → {table: 'users', column: 'created_at', type: 'timestamp'}
   
   d. save_conversion('selectUserList', 'UserMapper.xml', converted_sql)
      → {status: 'saved', progress: '25/86 (29%)'}

3. 진행률 로그 업데이트:
   [29%] [UserMapper] selectUserList - ✅ 완료
```

---

## 6. 진행률 표시

### 6.1 실시간 진행률

```bash
# logs/transform_progress.log
[  5%] [UserMapper] selectUserList - 🔄 변환중
[ 12%] [UserMapper] selectUserList - ✅ 완료
[ 18%] [ProductMapper] selectProduct - 🔄 변환중
[ 25%] [ProductMapper] selectProduct - ✅ 완료
```

### 6.2 Mapper별 상세 로그

```bash
# logs/transform/UserMapper.log
2026-02-14 16:00:00 - INFO - 변환 시작: selectUserList
2026-02-14 16:00:05 - INFO - 전략 적용: Tier 1 + Tier 2
2026-02-14 16:00:10 - INFO - 변환 완료: selectUserList
2026-02-14 16:00:10 - INFO - 저장 완료: output/transform/UserMapper_selectUserList.sql
```

---

## 7. 성능 최적화

### 7.1 Prompt Caching

```python
# SystemContentBlock으로 전략 캐싱
system_blocks = [
    SystemContentBlock(
        text=base_prompt,
        cache_control={"type": "ephemeral"}
    ),
    SystemContentBlock(
        text=tier1_rules,
        cache_control={"type": "ephemeral"}
    ),
    SystemContentBlock(
        text=tier2_strategy,
        cache_control={"type": "ephemeral"}
    )
]

# 캐시 히트 시 비용 90% 절감
```

### 7.2 병렬 처리

```python
# 8개 Worker 동시 실행
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(process_group, group) for group in groups]
    for future in as_completed(futures):
        result = future.result()
```

---

## 8. 에러 처리

### 8.1 변환 실패
```python
if conversion_failed:
    return {
        'status': 'failed',
        'sql_id': sql_id,
        'error': error_message,
        'suggestion': '수동 검토 필요'
    }
```

### 8.2 파일 없음
```python
if not extract_file.exists():
    return {
        'error': 'Extract 파일이 없습니다.',
        'suggestion': 'split_mapper() 먼저 실행'
    }
```

### 8.3 메타데이터 없음
```python
if not metadata_exists:
    return {
        'error': 'PostgreSQL 메타데이터가 없습니다.',
        'suggestion': 'generate_metadata() 먼저 실행'
    }
```

---

## 9. 사용 예시

### 9.1 전체 변환
```bash
# 자동 실행 (Orchestrator)
python3 src/run_orchestrator.py
🧑 > 전체 파이프라인 실행해줘

# 수동 실행
python3 src/run_sql_transform.py --workers 8
```

### 9.2 재변환
```bash
# 특정 단계 초기화 후 재실행
python3 src/run_sql_transform.py --reset --workers 8
```

### 9.3 진행률 확인
```bash
# 실시간 진행률
tail -f logs/transform_progress.log

# Mapper별 상세
tail -f logs/transform/UserMapper.log
```

---

## 10. 다른 Agent와의 연계

```
Source Analyzer Agent
    │
    ├── source_xml_list (DB) ──→ Transform Agent가 읽음
    └── reports/source_analysis.md

Strategy Agent
    │
    ├── output/strategy/transform_strategy.md ──→ Transform Agent가 적용
    └── 학습 내역 (FIXED 패턴)

Transform Agent
    │
    ├── output/transform/ ──→ Review Agent가 규칙 체크
    │                          ├── PASS → Validate Agent가 기능 동등성 검증
    │                          └── FAIL → Transform Agent 재호출
    ├── logs/transform_progress.log
    └── DB 업데이트 (transformed='Y')

Validate Agent
    │
    ├── 품질 검증 ──→ FAIL 시 재변환 요청
    └── FIXED 패턴 ──→ Strategy Agent 보강
```

---

**문서 버전**: 1.1  
**작성일**: 2026-02-14  
**최종 업데이트**: 2026-02-20  
**작성자**: OMA Development Team

# Source Analyzer Agent Design Document

## 1. Agent 개요

### 1.1 목적
- **주요 목표**: Java 프로젝트 내 MyBatis Mapper XML 파일을 스캔하고 SQL ID를 추출하여 변환 대상 목록 생성
- **사용자**: Oracle → PostgreSQL 마이그레이션 수행 팀
- **사용 시나리오**: 마이그레이션 프로젝트 시작 시 첫 번째 단계로 실행하여 전체 변환 대상 파악

### 1.2 입력/출력
```
입력: Java 소스 경로 (config.json) + MyBatis Mapper XML 파일들
출력: source_xml_list (DB) + transform_target_list (DB) + 분석 보고서 + 변환 전략 자동 생성
```

### 1.3 성공 기준
- [ ] 모든 MyBatis Mapper XML 파일 스캔 완료
- [ ] SQL ID별 메타데이터 추출 (타입, 복잡도, 라인 수)
- [ ] DB에 변환 대상 목록 저장
- [ ] 분석 보고서 생성 (파일별, SQL별 통계)
- [ ] 변환 전략 자동 생성 (Strategy Agent 호출)

---

## 2. 아키텍처

### 2.1 전체 구조

```
┌─────────────────────────────────────────┐
│  Prompt (prompt.md)                     │
│  - Mapper XML 스캔 전략                 │
│  - SQL ID 추출 규칙                     │
│  - 복잡도 분석 기준                     │
│  - 워크플로우 가이드                     │
└──────────────┬──────────────────────────┘
               │ LLM이 해석하고 실행
               ▼
┌─────────────────────────────────────────┐
│  Tools                                  │
│  - scan_xml_files.py     (파일 스캔)    │
│  - save_xml_list.py      (DB 저장)      │
│  - extract_sql_ids.py    (SQL 추출)     │
│  - generate_report.py    (보고서 생성)  │
└─────────────────────────────────────────┘
```

### 2.2 핵심 전략: 단계별 분석

```
Java 프로젝트
    │
    ▼ scan_xml_files
┌──────────────────────────────────────────┐
│ Mapper XML 파일 목록                     │
│ - UserMapper.xml                         │
│ - OrderMapper.xml                        │
│ - ProductMapper.xml                      │
└────┬─────────────────────────────────────┘
     │
     ▼ extract_sql_ids
┌──────────┐ ┌──────────┐ ┌──────────┐
│ SQL ID 1 │ │ SQL ID 2 │ │ SQL ID N │
│ (SELECT) │ │ (INSERT) │ │ (UPDATE) │
│ 복잡도: 3│ │ 복잡도: 1│ │ 복잡도: 8│
└────┬─────┘ └────┬─────┘ └────┬─────┘
     │             │             │
     ▼ save_xml_list & generate_report
┌─────────────────────────────────────────┐
│ DB 저장 + 분석 보고서                   │
│ - source_xml_list                       │
│ - transform_target_list                 │
│ - reports/source_analysis.md            │
└─────────────────────────────────────────┘
     │
     ▼ 자동 호출
┌─────────────────────────────────────────┐
│ Strategy Agent                          │
│ - 패턴 분석                             │
│ - 변환 전략 생성                        │
│ - transform_strategy.md                 │
└─────────────────────────────────────────┘
```

### 2.3 디렉토리 구조

```
src/agents/source_analyzer/
├── agent.py
├── prompt.md
├── README.md
└── tools/
    ├── __init__.py
    ├── scan_xml_files.py       # Mapper XML 파일 스캔
    ├── save_xml_list.py        # DB에 파일 목록 저장
    ├── extract_sql_ids.py      # SQL ID별 메타데이터 추출
    └── generate_report.py      # 분석 보고서 생성
```

---

## 3. Prompt 설계

### 3.1 핵심: 분석 규칙을 Prompt에 내장

LLM이 MyBatis XML 구조를 이해하고, SQL 복잡도를 분석합니다.
Tool은 파일 I/O와 DB 저장만 담당하고, 분석 로직은 LLM이 수행합니다.

### 3.2 분석 규칙 (Prompt에 포함)

```markdown
## MyBatis Mapper XML 분석 규칙

### XML 구조 인식
- <mapper namespace="..."> → 네임스페이스 추출
- <select id="..."> → SELECT 쿼리
- <insert id="..."> → INSERT 쿼리
- <update id="..."> → UPDATE 쿼리
- <delete id="..."> → DELETE 쿼리
- <sql id="..."> → 재사용 SQL 조각

### SQL 복잡도 계산
- 기본: 1점
- JOIN 절: +2점 (INNER, LEFT, RIGHT, FULL OUTER)
- 서브쿼리: +3점 (SELECT 내부의 SELECT)
- UNION/UNION ALL: +2점
- CASE WHEN: +1점
- 집계 함수 (COUNT, SUM, AVG, MAX, MIN): +1점
- 윈도우 함수 (ROW_NUMBER, RANK, DENSE_RANK): +3점
- Oracle 특수 함수 (NVL, DECODE, CONNECT BY): +2점
- 동적 SQL (<if>, <choose>, <foreach>): +1점
- 라인 수 10줄 초과: +1점, 20줄 초과: +2점

### 복잡도 등급
- Simple (1-3): 단순 CRUD
- Medium (4-7): 일반적인 비즈니스 로직
- Complex (8-12): 복잡한 조인/서브쿼리
- Very Complex (13+): 고도로 복잡한 쿼리

### Oracle 특화 패턴 감지
- ROWNUM 사용 → 페이징 변환 필요
- (+) 조인 → OUTER JOIN 변환 필요
- DUAL 테이블 → 제거 필요
- CONNECT BY → WITH RECURSIVE 변환 필요
- MERGE INTO → INSERT ON CONFLICT 변환 필요
- Oracle 함수 (NVL, DECODE, TO_CHAR) → PostgreSQL 함수 변환 필요
```

### 3.3 Workflow (Prompt에 명시)

```markdown
## Workflow

1. scan_xml_files() → Java 프로젝트에서 Mapper XML 파일 스캔
2. save_xml_list(xml_files) → DB에 파일 목록 저장
3. 각 XML 파일에 대해:
   a. extract_sql_ids(file_path) → SQL ID별 메타데이터 추출
   b. 복잡도 분석 및 Oracle 패턴 감지
   c. DB에 변환 대상 목록 저장
4. generate_report() → 전체 분석 보고서 생성
5. 자동으로 Strategy Agent 호출하여 변환 전략 생성
```

---

## 4. Tools 설계

### 4.1 Tool 목록

| Tool | 목적 | 입력 | 출력 |
|------|------|------|------|
| scan_xml_files | Mapper XML 스캔 | 없음 (config.json 참조) | `{xml_files: [{file_path, file_name, file_size}]}` |
| save_xml_list | DB에 파일 목록 저장 | xml_files | `{saved_count, total_files}` |
| extract_sql_ids | SQL ID 메타데이터 추출 | file_path | `{sql_ids: [{id, type, complexity, oracle_patterns}]}` |
| generate_report | 분석 보고서 생성 | 없음 | `{report_path, summary}` |

### 4.2 중요: extract_sql_ids는 추출만

LLM이 복잡도 분석을 수행하고, `extract_sql_ids`는 결과를 DB에 저장만 합니다.

```python
@tool
def extract_sql_ids(file_path: str) -> dict:
    """Extract SQL IDs and metadata from a Mapper XML file.
    
    LLM performs the actual analysis using rules in the prompt.
    This tool extracts XML content and saves results to DB.
    """
    # XML 파싱 및 SQL ID 추출
    # LLM 분석 결과를 DB에 저장
    return {'sql_ids': [...], 'total_count': 5}
```

---

## 5. 데이터 흐름

```
1. scan_xml_files()
   → {xml_files: [
       {file_path: '/src/main/resources/mapper/UserMapper.xml', 
        file_name: 'UserMapper.xml', 
        file_size: 2048},
       ...
     ]}

2. save_xml_list(xml_files)
   → {saved_count: 15, total_files: 15}

3. extract_sql_ids('/src/main/resources/mapper/UserMapper.xml')
   → {sql_ids: [
       {id: 'selectUserList', type: 'select', complexity: 4, 
        oracle_patterns: ['NVL', 'ROWNUM'], line_count: 12},
       {id: 'insertUser', type: 'insert', complexity: 1, 
        oracle_patterns: [], line_count: 3},
     ], total_count: 8}

4. generate_report()
   → {report_path: 'reports/source_analysis.md',
      summary: {
        total_files: 15, 
        total_sql_ids: 86,
        complexity_distribution: {simple: 45, medium: 28, complex: 10, very_complex: 3},
        oracle_patterns: {nvl: 23, rownum: 8, dual: 5, connect_by: 2}
      }}

5. 자동으로 Strategy Agent 호출
   → transform_strategy.md 생성
```

---

## 6. DB 스키마

### 6.1 source_xml_list 테이블

```sql
CREATE TABLE source_xml_list (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(100) NOT NULL,
    file_size INTEGER,
    namespace VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path)
);
```

### 6.2 transform_target_list 테이블

```sql
CREATE TABLE transform_target_list (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(100) NOT NULL,
    sql_id VARCHAR(100) NOT NULL,
    sql_type VARCHAR(20) NOT NULL, -- select, insert, update, delete, sql
    complexity_score INTEGER DEFAULT 1,
    complexity_level VARCHAR(20), -- simple, medium, complex, very_complex
    line_count INTEGER,
    oracle_patterns TEXT[], -- ['NVL', 'ROWNUM', 'DUAL']
    status VARCHAR(20) DEFAULT 'pending', -- pending, transformed, validated, tested
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path, sql_id)
);
```

---

## 7. 사용 예시

### 7.1 기본 실행

```bash
python3 src/run_source_analyzer.py
```

**실행 과정:**
```
🔍 MyBatis Mapper XML 파일 스캔 중...
   ✅ 15개 파일 발견

📊 SQL ID 추출 및 분석 중...
   ✅ UserMapper.xml: 8개 SQL ID (복잡도: 평균 3.2)
   ✅ OrderMapper.xml: 12개 SQL ID (복잡도: 평균 4.1)
   ✅ ProductMapper.xml: 6개 SQL ID (복잡도: 평균 2.8)
   ...

💾 데이터베이스 저장 중...
   ✅ source_xml_list: 15개 파일
   ✅ transform_target_list: 86개 SQL ID

📋 분석 보고서 생성 중...
   ✅ reports/source_analysis.md

🎯 변환 전략 자동 생성 중...
   ✅ output/strategy/transform_strategy.md
```

### 7.2 분석 보고서 예시

```markdown
# Source Analysis Report

## 요약
- **총 파일 수**: 15개
- **총 SQL ID 수**: 86개
- **평균 복잡도**: 3.4

## 복잡도 분포
- Simple (1-3): 45개 (52%)
- Medium (4-7): 28개 (33%)
- Complex (8-12): 10개 (12%)
- Very Complex (13+): 3개 (3%)

## Oracle 패턴 분석
- NVL 함수: 23개 SQL
- ROWNUM: 8개 SQL (페이징 변환 필요)
- DUAL 테이블: 5개 SQL
- CONNECT BY: 2개 SQL (재귀 쿼리 변환 필요)

## 파일별 상세
### UserMapper.xml
- SQL ID 수: 8개
- 복잡도: Simple(4), Medium(3), Complex(1)
- Oracle 패턴: NVL(3), ROWNUM(1)

### OrderMapper.xml
- SQL ID 수: 12개
- 복잡도: Simple(6), Medium(4), Complex(2)
- Oracle 패턴: NVL(5), DUAL(2)
```

### 7.3 Strategy Agent 자동 호출

Source Analyzer 완료 후 자동으로 Strategy Agent를 호출하여 변환 전략을 생성합니다:

```python
# Source Analyzer 완료 후
strategy_result = call_strategy_agent({
    'total_sql_count': 86,
    'complexity_distribution': {...},
    'oracle_patterns': {...}
})
```

---

## 8. 구현 체크리스트

### Phase 1: 디렉토리 & Prompt
- [ ] `src/agents/source_analyzer/` 디렉토리 생성
- [ ] `prompt.md` 작성 (분석 규칙 포함)
- [ ] `README.md` 작성

### Phase 2: Tools
- [ ] `scan_xml_files.py`
- [ ] `save_xml_list.py`
- [ ] `extract_sql_ids.py`
- [ ] `generate_report.py`

### Phase 3: DB 스키마
- [ ] `source_xml_list` 테이블 생성
- [ ] `transform_target_list` 테이블 생성

### Phase 4: 통합 & 테스트
- [ ] `agent.py` 작성
- [ ] `tests/test_source_analyzer.py`
- [ ] Tool 단위 테스트
- [ ] Agent 통합 테스트

---

## 9. 다음 단계 연계

```
Source Analyzer Agent
    │
    ├── source_xml_list (DB) ──→ Transform Agent 입력
    ├── transform_target_list (DB) ──→ 모든 후속 Agent 입력
    ├── reports/source_analysis.md ──→ 프로젝트 개요
    └── 자동 호출 ──→ Strategy Agent
                                    
Strategy Agent (자동 호출)
    │
    ├── transform_target_list (DB) ←── 입력
    ├── 패턴 분석 및 전략 생성
    └── output/strategy/transform_strategy.md ──→ Transform Agent 참조
```

이렇게 Source Analyzer Agent가 전체 마이그레이션 파이프라인의 시작점 역할을 하며, 후속 모든 Agent들이 사용할 기초 데이터를 생성합니다.

---

**문서 버전**: 1.1  
**작성일**: 2026-02-14  
**최종 업데이트**: 2026-02-20  
**작성자**: OMA Development Team
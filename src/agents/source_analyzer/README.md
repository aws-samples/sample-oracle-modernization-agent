# Source Analyzer Agent

Java 애플리케이션 소스 코드를 분석하여 Oracle 마이그레이션 사전 분석을 수행하는 Strands Agent

## 개요

**SourceAnalyzerAgent**는 Strands Framework 기반의 지능형 분석 Agent로, Java 소스 코드를 자동으로 분석하고 프로젝트별 변환 전략을 생성합니다:

- MyBatis Mapper XML 파일 탐지 및 분석
- SQL 복잡도 자동 평가 (4단계 분류)
- Oracle 패턴 탐지 (28개 패턴)
- 프레임워크 및 기술 스택 식별
- 상세 분석 보고서 자동 생성
- 분석 결과 데이터베이스 저장
- **프로젝트별 변환 전략 생성** (Top 10 복잡 SQL 분석 → 전략 파일)

## 아키텍처

### Prompt + Tools 구조

```
┌─────────────────────────────────────┐
│  Prompt (prompt.md)                 │
│  - 분석 전략 정의                    │
│  - 패턴 인식 로직                    │
│  - 워크플로우 가이드                 │
└──────────────┬──────────────────────┘
               │ LLM이 해석하고 실행
               ▼
┌─────────────────────────────────────┐
│  Tools (단순 기능만 수행)            │
│  - file_scanner                     │
│  - framework_analyzer               │
│  - sql_extractor                    │
│  - db_manager                       │
│  - report_generator                 │
└─────────────────────────────────────┘
```

### 디렉토리 구조

```
src/agents/source_analyzer/
├── agent.py                    # Strands Agent 메인
├── prompt.md                   # 분석 전략 및 워크플로우
└── tools/
    ├── file_scanner.py         # XML/Java 파일 스캔
    ├── framework_analyzer.py   # 프레임워크 분석
    ├── sql_extractor.py        # SQL 복잡도 분석
    ├── db_manager.py           # DB 조회/저장
    └── report_generator.py     # 마크다운 보고서 생성
```

## 주요 기능

### 1. MyBatis Mapper 분석
- DTD 기반 MyBatis XML 자동 탐지
- Namespace 및 SQL 문 개수 추출
- 유효/빈 Mapper 분류

### 2. SQL 복잡도 분석
**4단계 복잡도 분류:**
- **Simple (1-3점)**: 기본 SELECT/INSERT/UPDATE
- **Medium (4-7점)**: JOIN, 기본 집계 함수
- **Complex (8-12점)**: 서브쿼리, 동적 SQL
- **Very Complex (13점+)**: 다중 JOIN, 복잡한 동적 SQL

**복잡도 계산 요소:**
- JOIN: +2점/개
- 서브쿼리: +3점/개
- 동적 SQL (if/choose/foreach): +1~2점/개
- UNION: +2점/개
- 집계 함수: +1점/개

### 3. 프레임워크 분석
- Maven/Gradle 빌드 도구 탐지
- Spring/Struts 프레임워크 식별
- 의존성 라이브러리 추출
- 프레임워크 패턴 탐지 (Spring MVC, JPA, Servlet 등)

### 4. 보고서 생성
- 마크다운 형식의 상세 보고서
- 섹션별 구조화 (Executive Summary, Framework, SQL 복잡도 등)
- 테이블 및 통계 시각화
- 고복잡도 쿼리 Top 10 리스트

### 5. 데이터베이스 저장
- XML 파일 목록을 SQLite DB에 저장
- 테이블 완전 초기화 (DROP & CREATE)
- 물리 경로 및 상대 경로 포함

## 사용법

### 기본 실행

```bash
# 프로젝트 루트에서 실행
cd /path/to/oma
python3 src/run_source_analyzer.py
```

### Python 코드에서 사용

```python
from agents.source_analyzer.agent import create_source_analyzer_agent

# Agent 생성
agent = create_source_analyzer_agent()

# 분석 실행
result = agent("Java 소스 코드를 분석해서 보고서를 생성하고 DB에 저장해줘")
print(result)
```

### Tool 직접 테스트

```bash
# Tool만 개별 테스트
python3 tests/test_source_analyzer.py
```

## 환경 설정

### 1. AWS 자격 증명 (Bedrock 사용 시)

```bash
# 환경 변수 설정
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_SESSION_TOKEN="your_session_token"  # 임시 자격 증명 사용 시
```

### 2. 데이터베이스 설정

`./config/oma_control.db` 파일에 다음 테이블 필요:

```sql
-- properties 테이블
CREATE TABLE properties (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- JAVA_SOURCE_FOLDER 설정
INSERT INTO properties (key, value) 
VALUES ('JAVA_SOURCE_FOLDER', '/path/to/java/source');
```

### 3. 프로젝트 구조

```
oma/
├── config/
│   └── oma_control.db          # 설정 DB
├── src/
│   ├── utils/
│   │   └── project_paths.py    # 경로 자동 탐지
│   └── agents/
│       └── source_analyzer/
├── reports/                     # 보고서 출력 위치
└── tests/
    └── test_source_analyzer.py
```

## 출력 결과

### 1. 콘솔 출력

```
✅ 분석 완료!

📊 분석 결과:
- 프레임워크: Spring Framework (Spring MVC, Spring Core)
- 총 Mapper: 11개 (유효: 11, 빈 파일: 0)
- SQL 복잡도: 평균 7.06, 최대 65
- 복잡도 분포:
  * Simple: 33 (38.37%)
  * Medium: 27 (31.40%)
  * Complex: 18 (20.93%)
  * Very Complex: 8 (9.30%)

📄 보고서: /path/to/reports/source_analysis.md

주요 발견사항:
1. Spring Framework 기반의 애플리케이션으로, MyBatis ORM을 사용중입니다.
2. 총 86개의 SQL 쿼리가 분석되었으며, 대부분(69.77%)이 단순하거나 중간 정도의 복잡도를 가집니다.
3. PaymentMapper.xml의 'selectPaymentMethodPerformanceAnalysis' 쿼리가 가장 복잡한 것으로 분석되었습니다 (복잡도 점수: 65).
```

### 2. 마크다운 보고서

`./reports/source_analysis.md` 파일 생성:
- Executive Summary
- Framework Analysis
- MyBatis Mapper Analysis
- SQL Complexity Analysis (통계, 분포, Top 10)

### 3. 데이터베이스

`source_xml_list` 테이블에 XML 파일 정보 저장:

```sql
CREATE TABLE source_xml_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    relative_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Tools 상세

### get_java_source_folder()
- DB에서 JAVA_SOURCE_FOLDER 경로 조회
- 반환: 소스 폴더 경로 (str)

### scan_mybatis_mappers(source_folder)
- MyBatis Mapper XML 파일 스캔
- 반환: `{'total': int, 'valid': int, 'empty': int, 'mappers': list}`

### analyze_framework(source_folder)
- 프레임워크 및 빌드 도구 분석
- 반환: `{'name': str, 'build_tool': str, 'type': list, 'dependencies': list}`

### analyze_sql_complexity(mapper_files)
- SQL 복잡도 계산 및 통계 생성
- 반환: `{'average': float, 'max': int, 'distribution': dict, 'details': list}`

### generate_markdown_report(analysis_data, output_filename)
- 마크다운 보고서 생성
- 반환: 보고서 파일 경로 (str)

### save_xml_list(xml_files)
- XML 파일 목록을 DB에 저장
- 반환: 성공 메시지 (str)

## 장점

### 1. 유연성
- 분석 로직을 Prompt에서 관리
- 코드 변경 없이 Prompt 수정으로 전략 변경 가능

### 2. 지능성
- LLM이 컨텍스트를 이해하고 판단
- 예외 상황 자동 처리
- 자연어로 인사이트 생성

### 3. 확장성
- 새로운 Tool 추가 용이
- 다른 Agent와 조합 가능
- Multi-Agent 패턴 지원

### 4. 유지보수성
- Tool은 단순 기능만 수행
- 복잡한 로직은 Prompt에 집중
- 테스트 및 디버깅 용이

## 확장 가능성

### 추가 가능한 기능
- Oracle 패턴 상세 분석 (5단계 복잡도)
- DataSource 설정 추출
- Java 코드 Oracle 의존성 분석
- HTML 보고서 생성
- 변환 전략 제시

### Multi-Agent 통합
```python
# 다른 Agent와 조합
from agents.source_analyzer.agent import create_source_analyzer_agent
from agents.migration_planner.agent import create_migration_planner_agent

analyzer = create_source_analyzer_agent()
planner = create_migration_planner_agent()

# 순차 실행
analysis = analyzer("소스 분석")
plan = planner(f"분석 결과를 기반으로 마이그레이션 계획 수립: {analysis}")
```

## 문제 해결

### AWS 인증 오류
```
UnrecognizedClientException: The security token included in the request is invalid
```
→ AWS 자격 증명 환경 변수 확인

### 모델 액세스 오류
```
ValidationException: on-demand throughput isn't supported
```
→ Inference profile 사용: `us.anthropic.claude-3-5-sonnet-20241022-v2:0`

### DB 경로 오류
```
RuntimeError: Project root not found
```
→ `config/` 디렉토리가 프로젝트 루트에 있는지 확인

## 라이선스

MIT

## 참고

- [Strands Agents Documentation](https://strandsagents.com)
- [기존 프로그램 참조](/Users/changik/workspace/oma-origin/bin/application/)

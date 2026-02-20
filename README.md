# OMA - Application SQL Transform Assistant

## What is OMA?

OMA is an AI-powered Multi-Agent system that automatically transforms Oracle SQL to PostgreSQL.
It converts, validates, and tests hundreds to thousands of SQL statements in MyBatis Mapper XML files, reducing migration time from months to days.

Instead of DBAs and developers manually converting and testing SQL, AI Agents automatically handle the process and complete validation against real databases.

<details>
<summary><b>한글 설명 보기</b></summary>

OMA는 Oracle SQL을 PostgreSQL로 자동 변환하는 AI 기반 Multi-Agent 시스템입니다.
MyBatis Mapper XML 내 수백~수천 개의 SQL을 AI가 자동으로 변환, 검증, 테스트하여 마이그레이션 기간을 수개월에서 수일로 단축합니다.

DBA/개발팀이 수작업으로 SQL을 변환하고 테스트하는 대신, AI Agent가 자동으로 처리하고 실제 DB에서 검증까지 완료합니다.

</details>

## Input → Output

```
┌─────────────────────┐         ┌──────────────────────────────┐         ┌─────────────────────────┐
│                     │         │                              │         │                         │
│   📂 Input          │         │  🤖 OMA                      │         │   ✅ Output             │
│                     │  ────▶  │                              │  ────▶  │                         │
│  MyBatis Mapper XML │         │  Orchestrator (Control Hub)  │         │  PostgreSQL Mapper XML  │
│  (Oracle SQL)       │         │   ├─ Diff Tools              │         │  (Validated)            │
│                     │         │   ├─ Single SQL Processing   │         │                         │
│                     │         │   └─ Pipeline Control        │         │                         │
│                     │         │                              │         │                         │
│                     │         │  6 Pipeline Agents           │         │                         │
│                     │         │   ├─ Source Analyzer         │         │                         │
│                     │         │   ├─ Transform Agent         │         │                         │
│                     │         │   ├─ Review Agent            │         │                         │
│                     │         │   ├─ Validate Agent          │         │                         │
│                     │         │   ├─ Test Agent              │         │                         │
│                     │         │   └─ Strategy Refine         │         │                         │
└─────────────────────┘         └──────────────────────────────┘         └─────────────────────────┘

   • UserMapper.xml           Pipeline Agents:              ✅ Converted SQL (PostgreSQL)
   • OrderMapper.xml           • Source Analyzer            ✅ Rule Compliance Verified
   • ProductMapper.xml         • Transform Agent            ✅ Functional Equivalence Verified
   • 100+ SQL Statements       • Review Agent               ✅ DB Execution Test Passed
                               • Validate Agent             ✅ Fix History (3-way diff)
                               • Test Agent                 ✅ Learned Conversion Strategy
                               • Strategy Refine            
                                                            
                               Orchestrator Tools:          
                               • Diff Tools (compare/approve)
                               • Single SQL Processing
                               • Pipeline Control

See [System Documentation](docs/SYSTEM_DOCUMENTATION.md#파이프라인-워크플로우) for detailed workflow.
```

<details>
<summary><b>한글 설명 보기</b></summary>

```
┌─────────────────────┐         ┌──────────────────────────────┐         ┌─────────────────────────┐
│                     │         │                              │         │                         │
│   📂 입력            │         │  🤖 OMA                      │         │   ✅ 출력                │
│                     │  ────▶  │                              │  ────▶  │                         │
│  MyBatis Mapper XML │         │  Orchestrator (제어 허브)     │         │  PostgreSQL Mapper XML  │
│  (Oracle SQL)       │         │   ├─ Diff Tools              │         │  (검증 완료)             │
│                     │         │   ├─ 단일 SQL 처리            │         │                         │
│                     │         │   └─ 파이프라인 제어          │         │                         │
│                     │         │                              │         │                         │
│                     │         │  6개 파이프라인 Agent         │         │                         │
│                     │         │   ├─ Source Analyzer         │         │                         │
│                     │         │   ├─ Transform Agent         │         │                         │
│                     │         │   ├─ Review Agent            │         │                         │
│                     │         │   ├─ Validate Agent          │         │                         │
│                     │         │   ├─ Test Agent              │         │                         │
│                     │         │   └─ Strategy Refine         │         │                         │
└─────────────────────┘         └──────────────────────────────┘         └─────────────────────────┘

   • UserMapper.xml           파이프라인 Agent:            ✅ 변환된 SQL (PostgreSQL)
   • OrderMapper.xml           • Source Analyzer           ✅ 규칙 준수 검증 완료
   • ProductMapper.xml         • Transform Agent           ✅ 기능 동등성 검증 완료
   • 100+ SQL 구문             • Review Agent              ✅ DB 실행 테스트 통과
                               • Validate Agent            ✅ 수정 이력 (fix_history)
                               • Test Agent                ✅ 학습된 변환 전략
                               • Strategy Refine           
                                                           
                               Orchestrator 도구:          
                               • Diff Tools (비교/승인)
                               • 단일 SQL 처리
                               • 파이프라인 제어

더 상세한 워크플로우를 확인하기 위해서 [System Documentation](docs/SYSTEM_DOCUMENTATION.md#파이프라인-워크플로우)를 참조하세요.
```

</details>

## Why OMA?

| Manual Migration | With OMA |
|-----------------|----------|
| DBAs manually fix SQL one by one | AI automatically converts |
| Takes months | Completes in days |
| Manual verification, risk of omissions | 4-stage automated quality assurance |
| Repetitive work, no learning | Automatic learning from failures |
| Post-migration feedback | "Let's use OMA for the next project" |
| Cost | 80% API cost reduction (Prompt Caching) |

<details>
<summary><b>한글 설명 보기</b></summary>

| 기존 수작업 마이그레이션 | OMA 적용 후 |
|------------------------|------------|
| DBA가 SQL 하나씩 수정 | AI가 자동 변환 |
| 수개월 소요 | 수일 내 완료 |
| 수작업 검증, 누락 위험 | 4단계 자동 품질 보증 |
| 반복 작업, 학습 없음 | 실패 패턴 자동 학습 |
| 마이그레이션 후 반응 | "다음 프로젝트도 OMA로" |
| 비용 | API 비용 80% 절감 (Prompt Caching) |

</details>

## How It Works

### Step 1 — Setup (~5 minutes)

```bash
# 1. Virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"

# 4. Configure environment
python3 src/run_setup.py
```

### Step 2 — Run Pipeline (Automated)

Control the entire pipeline with conversational Orchestrator:

```bash
python3 src/run_orchestrator.py
```

```
🧑 > Run the entire pipeline

🤖 > Checking setup...
     ✅ Java path: /usr/lib/jvm/java-11
     ✅ PostgreSQL connection: OK
     
     Step 1: Starting source analysis...
     ✅ Scanned 11 Mappers
     ✅ Extracted 127 SQL IDs
     ✅ Generated conversion strategy
     
     Step 2: Starting SQL transformation (8 parallel workers)...
     [  5%] [UserMapper] selectUserList - 🔄 Converting
     [ 12%] [UserMapper] selectUserList - ✅ Done
     ...
     ✅ Converted 127 SQLs
     
     Step 3: Rule compliance review...
     ✅ 125 PASS, 2 re-converted → PASS
     
     Step 4: Functional equivalence validation...
     ✅ 127 validated
     
     Step 5: DB execution test...
     ✅ 120 PASS, 7 auto-fixed → PASS
     
     Step 6: XML reassembly...
     ✅ Final Mapper XML generated
     
     🎉 Pipeline completed!
```

<details>
<summary><b>한글 대화 예시 보기</b></summary>

```
🧑 > 전체 파이프라인 실행해줘

� > Setup 확인 중...
     ✅ Java 경로: /usr/lib/jvm/java-11
     ✅ PostgreSQL 접속: 정상
     
     Step 1: 소스 분석 시작...
     ✅ 11개 Mapper 스캔 완료
     ✅ 127개 SQL ID 추출
     ✅ 변환 전략 생성 완료
     
     Step 2: SQL 변환 시작 (병렬 8개)...
     [  5%] [UserMapper] selectUserList - 🔄 변환중
     [ 12%] [UserMapper] selectUserList - ✅ 완료
     ...
     ✅ 127개 SQL 변환 완료
     
     Step 3: 규칙 준수 리뷰...
     ✅ 125개 PASS, 2개 재변환 → PASS
     
     Step 4: 기능 동등성 검증...
     ✅ 127개 검증 완료
     
     Step 5: DB 실행 테스트...
     ✅ 120개 PASS, 7개 자동 수정 → PASS
     
     Step 6: XML 재조립...
     ✅ 최종 Mapper XML 생성 완료
     
     🎉 전체 파이프라인 완료!
```

</details>

### Step 3 — Generated Assets

| Asset | Description | Location |
|-------|-------------|----------|
| **PostgreSQL SQL** | Converted SQL (127 statements) | `output/transform/` |
| **Conversion Strategy** | Project-specific patterns | `output/strategy/transform_strategy.md` |
| **Final Mapper XML** | Deployable XML files | `output/merge/` |
| **Fix History** | 3-way diff (ORIGINAL/BEFORE/AFTER) | `output/logs/fix_history/` |
| **Conversion Report** | Overall conversion summary | `output/reports/` |
| **Execution Logs** | Detailed logs per stage | `output/logs/` |

<details>
<summary><b>한글 설명 보기</b></summary>

| 생성 에셋 | 설명 | 위치 |
|----------|------|------|
| **PostgreSQL SQL** | 변환된 SQL (127개) | `output/transform/` |
| **변환 전략** | 프로젝트 특화 패턴 | `output/strategy/transform_strategy.md` |
| **최종 Mapper XML** | 배포 가능한 XML | `output/merge/` |
| **수정 이력** | 3단 비교 (ORIGINAL/BEFORE/AFTER) | `output/logs/fix_history/` |
| **변환 리포트** | 전체 변환 요약 | `output/reports/` |
| **실행 로그** | 단계별 상세 로그 | `output/logs/` |

</details>

### Step 4 — Review & Approval (Optional)

Review and approve conversion results with Diff Tools:

```
🧑 > Compare conversion for selectUserList in UserMapper.xml

🤖 > [Displays Oracle original vs PostgreSQL converted side-by-side]

🧑 > Approve it

🤖 > ✅ Approved. Review note recorded.
```

<details>
<summary><b>한글 대화 예시 보기</b></summary>

```
🧑 > UserMapper.xml의 selectUserList 변환 비교해줘

🤖 > [Oracle 원본 vs PostgreSQL 변환본 표시]

🧑 > 승인해줘

🤖 > ✅ 승인 완료. 리뷰 노트 기록됨.
```

</details>

## Pipeline Architecture

```
Setup → Analyze → Transform → Review → Validate → Test → Merge
                                ↓ FAIL
                          Re-convert (max 2 rounds)
```

| Stage | Agent | Role | Output |
|-------|-------|------|--------|
| **Analyze** | Source Analyzer | Scan Mappers, extract SQL, analyze patterns | Conversion strategy |
| **Transform** | Transform Agent | Oracle → PostgreSQL conversion | Converted SQL |
| **Review** | Review Agent | Rule compliance check (FAIL → re-convert) | PASS/FAIL |
| **Validate** | Validate Agent | Functional equivalence verification | Validated |
| **Test** | Test Agent | DB execution test, error fixing | Test passed |
| **Merge** | - | XML reassembly | Final Mapper |

See [System Documentation](docs/SYSTEM_DOCUMENTATION.md#파이프라인-워크플로우) for detailed workflow.

<details>
<summary><b>한글 설명 보기</b></summary>

| 단계 | Agent | 역할 | 출력 |
|-----|-------|------|------|
| **Analyze** | Source Analyzer | Mapper 스캔, SQL 추출, 패턴 분석 | 변환 전략 |
| **Transform** | Transform Agent | Oracle → PostgreSQL 변환 | 변환된 SQL |
| **Review** | Review Agent | 규칙 준수 체크 (FAIL → 재변환) | PASS/FAIL |
| **Validate** | Validate Agent | 기능 동등성 검증 | 검증 완료 |
| **Test** | Test Agent | DB 실행 테스트, 에러 수정 | 테스트 통과 |
| **Merge** | - | XML 재조립 | 최종 Mapper |

</details>

## Key Features

### 1. Conversational Pipeline Control
```
🧑 > Run the entire pipeline
🧑 > Check current status
🧑 > Re-run transform stage
```

### 2. SQL Comparison & Review (Diff Tools)
```
🧑 > Compare conversion for selectUserList in UserMapper.xml
🧑 > Approve it
🧑 > Generate full conversion report
```

### 3. Single SQL Processing
```
🧑 > Re-convert selectUserList in UserMapper.xml
🧑 > Re-validate selectOrderDetail
🧑 > Re-test selectProduct
```

### 4. Automated Quality Assurance
- **Review**: Rule compliance check → Auto re-convert on FAIL (max 2 rounds)
- **Validate**: Functional equivalence verification → Auto fix on FAIL
- **Test**: DB execution test → Error analysis and auto fix on FAIL
- **Learning**: Automatically reflect fix patterns into strategy

### 5. Real-time Progress & Logs
Displays real-time progress per SQL ID at each stage, and records all fix history in 3-way diff format (ORIGINAL/BEFORE/AFTER).

See [System Documentation](docs/SYSTEM_DOCUMENTATION.md) for details.

<details>
<summary><b>한글 설명 보기</b></summary>

### 1. 대화형 파이프라인 제어
```
🧑 > 전체 파이프라인 실행해줘
🧑 > 현재 상태 확인해줘
🧑 > 변환 단계 재수행해줘
```

### 2. SQL 비교 및 검토 (Diff Tools)
```
🧑 > UserMapper.xml의 selectUserList 변환 비교해줘
🧑 > 승인해줘
🧑 > 전체 변환 리포트 만들어줘
```

### 3. 단일 SQL 처리
```
🧑 > UserMapper.xml의 selectUserList 재변환해줘
🧑 > selectOrderDetail 재검증해줘
🧑 > selectProduct 재테스트해줘
```

### 4. 자동 품질 보증
- **Review**: 규칙 준수 체크 → FAIL 시 자동 재변환 (최대 2라운드)
- **Validate**: 기능 동등성 검증 → FAIL 시 자동 수정
- **Test**: DB 실행 테스트 → FAIL 시 에러 분석 및 자동 수정
- **Learning**: 수정 패턴을 전략에 자동 반영

### 5. 실시간 진행률 및 로그
각 단계에서 SQL ID별 진행 상황을 실시간으로 표시하고, 모든 수정 이력을 3단 비교(ORIGINAL/BEFORE/AFTER)로 기록합니다.

</details>

## Cost

| Item | Cost |
|------|------|
| **SQL Conversion** | ~$0.01 per SQL (with Prompt Caching) |
| **100 SQL Project** | ~$1-2 (full pipeline) |
| **Infrastructure** | AWS Bedrock usage-based (serverless) |

80% API cost reduction with Prompt Caching (90%+ cache hit rate)

<details>
<summary><b>한글 설명 보기</b></summary>

| 항목 | 비용 |
|------|------|
| **SQL 변환** | ~$0.01 per SQL (Prompt Caching 적용) |
| **100개 SQL 프로젝트** | ~$1-2 (전체 파이프라인) |
| **인프라** | AWS Bedrock 사용량 기반 (서버리스) |

Prompt Caching으로 API 비용 80% 절감 (캐시 히트율 90%+)

</details>

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI** | Strands Agents SDK · Claude Sonnet 4.5 (Bedrock) · Prompt Caching |
| **Runtime** | Python 3.11 · ThreadPoolExecutor (8 parallel) |
| **DB** | SQLite (state management) · PostgreSQL (target DB) |
| **External** | AWS Bedrock · Java MyBatis |
| **Dependencies** | boto3 · defusedxml |

<details>
<summary><b>한글 설명 보기</b></summary>

| 레이어 | 기술 |
|--------|------|
| **AI** | Strands Agents SDK · Claude Sonnet 4.5 (Bedrock) · Prompt Caching |
| **Runtime** | Python 3.11 · ThreadPoolExecutor (병렬 8) |
| **DB** | SQLite (상태 관리) · PostgreSQL (타겟 DB) |
| **외부 연동** | AWS Bedrock · Java MyBatis |
| **Dependencies** | boto3 · defusedxml |

</details>

## Project Structure

```
sql-migration-assistant/
├── src/
│   ├── agents/                   # 7 Expert Agents
│   │   ├── orchestrator/         # Pipeline control + Diff Tools
│   │   ├── source_analyzer/      # Source analysis + strategy generation
│   │   ├── sql_transform/        # SQL transformation
│   │   ├── sql_review/           # Rule compliance review
│   │   ├── sql_validate/         # Functional equivalence validation
│   │   ├── sql_test/             # DB execution test
│   │   └── strategy_refine/      # Strategy enhancement/compression
│   ├── config/oma_control.db     # SQLite (state management)
│   ├── reference/
│   │   └── oracle_to_postgresql_rules.md  # General Rules
│   └── run_*.py                  # Execution scripts
├── output/                       # All artifacts
│   ├── transform/                # Converted SQL
│   ├── strategy/                 # Project-specific strategy
│   ├── merge/                    # Final Mapper XML
│   └── logs/fix_history/         # Fix history
└── docs/                         # Detailed documentation
```

## Requirements

- Python 3.10+ (recommended 3.11)
- AWS credentials (Bedrock access)
- Java 11+ (for SQL testing)
- psql (for PostgreSQL metadata collection)

## Documentation

- [System Documentation](docs/SYSTEM_DOCUMENTATION.md) — Architecture, Agent details, DB schema
- [Project Overview](PROJECT_OVERVIEW.md) — Business value and use cases
- Agent Design Documents:
  - [Orchestrator Agent](docs/agents/ORCHESTRATOR_DESIGN.md)
  - [Source Analyzer Agent](docs/agents/SOURCE_ANALYZER_DESIGN.md)
  - [Transform Agent](docs/agents/TRANSFORM_DESIGN.md)
  - [Review Agent](docs/agents/REVIEW_DESIGN.md)
  - [Validate Agent](docs/agents/VALIDATE_DESIGN.md)
  - [Test Agent](docs/agents/TEST_DESIGN.md)
- Per-Agent README: `src/agents/*/README.md`

## License

This project is distributed under an appropriate license. See [LICENSE](LICENSE) file for details.

## Contributing

Contributions to improve the project are welcome. Refer to Agent design documents when developing new Agents.

---

**Last Updated**: 2026-02-20  
**Version**: 3.0  
**Status**: Production Ready

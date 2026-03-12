# Oracle Modernization Agent (OMA)

> AI-powered Oracle to PostgreSQL modernization toolkit

> ⚠️ Sample code for educational purposes. Not for production use without review. See [Disclaimer](#disclaimer).

## What is OMA?

**Oracle Modernization Agent (OMA)** is a collection of AI-powered agents that automate Oracle to PostgreSQL database modernization. Each module tackles a specific aspect of the migration lifecycle — from application SQL transformation to schema conversion and beyond.

Instead of DBAs and developers spending months on manual conversion and testing, AI Agents handle the heavy lifting with automated quality assurance.

<details>
<summary><b>한글 설명 보기</b></summary>

**Oracle Modernization Agent (OMA)** 는 Oracle에서 PostgreSQL로의 데이터베이스 현대화를 자동화하는 AI 에이전트 모음입니다. 각 모듈은 마이그레이션 라이프사이클의 특정 영역을 담당합니다 — 애플리케이션 SQL 변환부터 스키마 전환까지.

DBA와 개발자가 수개월간 수작업으로 변환하고 테스트하는 대신, AI Agent가 자동 품질 보증과 함께 핵심 작업을 처리합니다.

</details>

## Modules

| Module | Description | Status |
|--------|-------------|--------|
| **[Application SQL Transform Agent](application-sql-transform-agent/)** | MyBatis Mapper XML 내 Oracle SQL을 PostgreSQL로 자동 변환, 검증, 테스트 | Production Ready |
| *More modules coming soon* | Schema conversion, data migration, etc. | Planned |

## Why OMA?

| Manual Migration | With OMA |
|-----------------|----------|
| DBAs manually fix SQL one by one | AI automatically converts |
| Takes months | Completes in days |
| Manual verification, risk of omissions | Multi-stage automated quality assurance |
| Repetitive work, no learning | Automatic learning from failures |
| High cost | 80% API cost reduction (Prompt Caching) |

<details>
<summary><b>한글 설명 보기</b></summary>

| 기존 수작업 마이그레이션 | OMA 적용 후 |
|------------------------|------------|
| DBA가 SQL 하나씩 수정 | AI가 자동 변환 |
| 수개월 소요 | 수일 내 완료 |
| 수작업 검증, 누락 위험 | 다단계 자동 품질 보증 |
| 반복 작업, 학습 없음 | 실패 패턴 자동 학습 |
| 높은 비용 | API 비용 80% 절감 (Prompt Caching) |

</details>

## Quick Start

Each module has its own setup and execution instructions. Start with the module you need:

### Application SQL Transform Agent

Automatically transforms Oracle SQL to PostgreSQL in MyBatis Mapper XML files with 4-stage quality pipeline.

```bash
cd application-sql-transform-agent
```

See [Application SQL Transform Agent README](application-sql-transform-agent/README.md) for detailed setup and usage.

## Project Structure

```
sample-oracle-modernization-agent/
├── README.md                              # This file (OMA overview)
├── PROJECT_OVERVIEW.md                    # Business value & architecture overview
├── LICENSE
├── THIRD_PARTY_LICENSES.md
└── application-sql-transform-agent/       # Module: SQL Transform Agent
    ├── README.md                          #   Module-specific documentation
    ├── PROJECT_OVERVIEW.md                #   Module-specific overview
    ├── src/                               #   Source code
    ├── docs/                              #   Detailed documentation
    └── example/                           #   Quick-start example
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI** | Strands Agents SDK · Claude Sonnet 4.5 (AWS Bedrock) · Prompt Caching |
| **Runtime** | Python 3.11 · uv (package manager) |
| **Cloud** | AWS Bedrock · SSM Parameter Store |
| **Target DB** | PostgreSQL |

## Requirements

- Python 3.10+ (recommended 3.11)
- AWS credentials (Bedrock access)
- Module-specific requirements — see each module's README

## AWS Permissions

OMA modules require an IAM identity (user or role) with access to the following AWS services:

| Service | Actions | Purpose |
|---------|---------|---------|
| **Amazon Bedrock** | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | LLM inference (all Agents) |
| **SSM Parameter Store** | `ssm:PutParameter`, `ssm:GetParametersByPath` | DB connection info management |

See [Application SQL Transform Agent README](application-sql-transform-agent/README.md#aws-permissions) for the minimum IAM policy.

## Documentation

- [Project Overview](PROJECT_OVERVIEW.md) — Business value, architecture, and use cases
- **Module Documentation**:
  - [Application SQL Transform Agent](application-sql-transform-agent/README.md) — Full usage guide
  - [System Documentation](application-sql-transform-agent/docs/SYSTEM_DOCUMENTATION.md) — Architecture & Agent details
  - [Large-Scale Guide](application-sql-transform-agent/docs/LARGE_SCALE_GUIDE.md) — Worker tuning & cost optimization

## Disclaimer

This code is provided as a sample for educational and demonstration purposes only.

- **NOT FOR PRODUCTION USE**: Do not deploy without additional security testing.
- **AI-Generated Output**: SQL transformations must be reviewed before execution.
- **No Warranty**: Provided "AS IS" without warranty of any kind.

## License

This project is distributed under the MIT-0 License. See [LICENSE](LICENSE) file for details.

## Contributing

Contributions to improve the project are welcome. Each module has its own Agent design documents — refer to them when developing new Agents or modules.

---

**Last Updated**: 2026-03-13
**Version**: 4.0

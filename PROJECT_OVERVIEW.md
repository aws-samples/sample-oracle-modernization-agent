# Oracle Modernization Agent (OMA) — Project Overview

> AI-powered Oracle to PostgreSQL modernization toolkit

## Project Description

Oracle Modernization Agent (OMA) is an AI-powered multi-agent toolkit designed to accelerate Oracle to PostgreSQL database modernization. OMA provides a modular collection of specialized agents, each targeting a specific phase of the migration lifecycle.

### Current Modules

- **[Application SQL Transform Agent](application-sql-transform-agent/)**: Automatically transforms Oracle SQL to PostgreSQL in MyBatis Mapper XML files. 8 specialized AI agents handle analysis, conversion, multi-perspective review, validation, and real database testing — with automatic pattern learning from failures.

### Planned Modules

Additional modules for schema conversion, data migration, and other migration phases are planned.

## Business Value

OMA has demonstrated significant business value for enterprise database migration initiatives:

### Quantified Impact
- **86% Reduction in Migration Effort**: Decreased manual conversion work from 7 person-months to 1 person-month through GenAI automation
- **Cost Optimization**: Eliminates ongoing Oracle license fees while establishing a modernized architecture foundation based on open-source databases
- **Quality Assurance**: Multi-stage validation pipelines reduce post-migration defects and rework
- **API Cost Reduction**: Prompt caching reduces API costs by approximately 80%

### Strategic Benefits
- **Accelerated Time-to-Market**: Automated conversion enables faster migration cycles, reducing business disruption
- **Risk Mitigation**: Systematic validation and real database testing minimize migration risks
- **Knowledge Capture**: Dynamic strategy generation documents project-specific patterns for future reference
- **Scalability**: Parallel execution supports large-scale enterprise migrations

### Technical Advantages
- **AWS Native Integration**: Seamless integration with AWS Bedrock and cloud-native services
- **Open Source Foundation**: Built on PostgreSQL, eliminating vendor lock-in and enabling cloud-native architectures
- **Extensibility**: Multi-agent architecture allows easy addition of new modules and database targets
- **Learning Capability**: Automatic pattern learning from failures improves accuracy over time

## Target Use Cases

- Enterprise applications migrating from Oracle to PostgreSQL
- Organizations seeking to reduce Oracle licensing costs through open-source adoption
- Large-scale migrations requiring automated validation and testing
- Teams needing repeatable, AI-assisted database modernization workflows

## Architecture

OMA follows a modular architecture where each module operates independently while sharing common infrastructure:

```
┌─────────────────────────────────────────────────────┐
│                 OMA (Umbrella Project)               │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │       Application SQL Transform Agent         │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│  │  │ Analyze  │→ │Transform │→ │  Review     │  │  │
│  │  └──────────┘  └──────────┘  └────────────┘  │  │
│  │       ┌──────────┐  ┌──────────┐             │  │
│  │       │ Validate │→ │  Test    │→ Merge      │  │
│  │       └──────────┘  └──────────┘             │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │           (Future Modules)                    │  │
│  │  Schema Conversion · Data Migration · ...     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Common: AWS Bedrock · Strands Agents SDK · Python  │
└─────────────────────────────────────────────────────┘
```

## Technology Foundation

- **AI Model**: Claude Sonnet 4.5 (AWS Bedrock)
- **Framework**: Strands Agents SDK — Multi-agent orchestration
- **Target Database**: PostgreSQL
- **Programming Language**: Python 3.11+ (uv package manager)
- **Cloud Services**: AWS Bedrock, SSM Parameter Store

---

**Last Updated**: 2026-03-13
**Version**: 4.0

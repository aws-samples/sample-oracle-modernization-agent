# Application SQL Transform Agent

> Part of **OMA (Oracle Modernization Agent)**

## Overview

Oracle SQL을 PostgreSQL/MySQL로 자동 변환하는 하이브리드 AI 시스템.
MyBatis Mapper XML 파일 내의 SQL을 추출, 변환, 검증, 병합하여
Target DB용 최종 XML을 생성한다.

## Architecture

Claude Code 메인 세션이 오케스트레이터 역할을 하며, LLM 작업은 5개 subagent에,
결정적 인프라 작업은 `oma` CLI에 위임한다.

```
Claude Code (Orchestrator)
  ├── .claude/agents/  — 5 subagents (transformer, reviewer, validator, test-fixer, strategy-refiner)
  ├── .claude/skills/  — Pipeline workflow (SSOT)
  └── src/cli/         — oma CLI (setup, status, db, analyze, merge, test-exec, report)
```

- **상태 SSOT**: SQLite DB (`output/oma_control.db`)
- **Target DB**: PostgreSQL, MySQL (설정으로 전환)
- **품질 파이프라인**: Analyze → Transform → Review → Validate → Merge → Test → Report

## Key Features

- **7단계 품질 파이프라인** — Review FAIL 시 피드백 기반 자동 재변환 (최대 3라운드)
- **체크포인트 승인형** — 매 단계 결과 요약 후 사용자 승인 대기
- **2-Tier 규칙 체계** — 정적 General Rules + 프로젝트별 동적 전략 (자동 학습)
- **다중 Target DB** — PostgreSQL/MySQL 동시 지원
- **중단/재개** — DB 기반 상태 관리로 세션 중단 후 즉시 재개

## Quick Start

```bash
uv sync
uv run oma setup --non-interactive --source <java-source-path> --target-db postgresql
# Claude Code 세션에서: "변환 시작"
```

## Documentation

| 문서 | 내용 |
|------|------|
| `CLAUDE.md` | Claude Code 가이드 (아키텍처, 코딩 규칙, 환경 변수) |
| `docs/SYSTEM_DOCUMENTATION.md` | 시스템 전체 문서 (CLI 레퍼런스, 상태 모델, 데이터 흐름) |
| `docs/LARGE_SCALE_GUIDE.md` | 대규모 프로젝트(수백~수천 SQL) 운영 가이드 |
| `docs/SITE_GUIDE.md` | 실 프로젝트 투입 시 runbook |
| `docs/db-schema.md` | DB 스키마 관계도 |

---

**Version**: 5.0 | **Updated**: 2026-07

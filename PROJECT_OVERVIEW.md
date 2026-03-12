# OMA - Oracle Modernization Agent

## Project Description

OMA (Oracle Modernization Agent) is an AI-powered multi-agent system designed to accelerate Oracle to PostgreSQL database migration. The system provides comprehensive support for MyBatis Mapper XML transformation, including:

- **Automated SQL Conversion**: Leverages Claude Sonnet 4.5 via AWS Bedrock to intelligently convert Oracle SQL to PostgreSQL syntax
- **Multi-Stage Quality Assurance**: 4-tier validation pipeline (Transform → Review [multi-perspective: Syntax + Equivalence] → Validate → Test) ensures conversion accuracy
- **Sample Transform**: Run representative subset (N SQLs with type coverage + mapper round-robin) to verify strategy quality before full pipeline
- **Intelligent Pattern Learning**: Dynamic strategy generation adapts to project-specific SQL patterns and automatically learns from failures
- **Real Database Testing**: Validates converted SQL against actual PostgreSQL instances to ensure functional equivalence
- **Rich Progress UI**: Real-time progress bars, structured pipeline status tables, git-like colored diff display
- **Batch Processing Optimization**: Groups related SQL statements for efficient processing with prompt caching, reducing API costs by ~80%

The system combines rule-based transformation with AI-powered expert judgment to handle complex Oracle-specific constructs, providing diagnosis, analysis, and migration best practices to accelerate real workload migration from Oracle to AWS open-source databases.

## Business Value

OMA has demonstrated significant business value for enterprise database migration initiatives:

### Quantified Impact
- **86% Reduction in Migration Effort**: Decreased manual conversion work from 7 person-months to 1 person-month through GenAI automation
- **Cost Optimization**: Eliminates ongoing Oracle license fees while establishing a modernized architecture foundation based on open-source databases
- **Quality Assurance**: 4-stage validation pipeline reduces post-migration defects and rework
- **API Cost Reduction**: Batch processing with prompt caching reduces API costs by approximately 80%

### Strategic Benefits
- **Accelerated Time-to-Market**: Automated conversion enables faster migration cycles, reducing business disruption
- **Risk Mitigation**: Systematic validation and real database testing minimize migration risks
- **Knowledge Capture**: Dynamic strategy generation documents project-specific patterns for future reference
- **Scalability**: Batch processing and parallel execution support large-scale enterprise migrations

### Technical Advantages
- **AWS Native Integration**: Seamless integration with AWS Bedrock and cloud-native services
- **Open Source Foundation**: Built on PostgreSQL, eliminating vendor lock-in and enabling cloud-native architectures
- **Extensibility**: Multi-agent architecture allows easy addition of new validation stages or database targets
- **Learning Capability**: Automatic pattern learning from failures improves conversion accuracy over time

This successful implementation validates the potential of GenAI technology to transform traditional database migration approaches, establishing a repeatable framework for Oracle modernization initiatives.

## Target Use Cases

- Enterprise applications with extensive MyBatis-based data access layers
- Oracle to PostgreSQL migration projects requiring high conversion accuracy
- Organizations seeking to reduce Oracle licensing costs through open-source adoption
- Teams needing automated validation and testing for database migrations
- Large-scale migrations with hundreds or thousands of SQL statements

## Technology Foundation

- **AI Model**: Claude Sonnet 4.5 (AWS Bedrock)
- **Framework**: Strands Agents SDK (v1.24.0+) - Multi-agent orchestration
- **Target Database**: PostgreSQL
- **Source Framework**: MyBatis (XML Mapper files)
- **Programming Language**: Python 3.11+ (uv package manager)
- **Key Dependencies**: boto3, defusedxml, rich, sqlalchemy

## Architecture Highlights

- **4-Stage Quality Pipeline**: Transform → Review (multi-perspective) → Validate → Test
- **2-Tier Rule System**: Static General Rules + Dynamic Project Strategy
- **Batch Processing**: Groups 3-5 SQL statements for cost-efficient processing
- **Prompt Caching**: 3-block caching structure reduces API costs by 90%
- **Parallel Execution**: 8 concurrent workers for faster processing
- **Automatic Learning**: Failed patterns automatically added to strategy

---

**Last Updated**: 2026-03-13
**Version**: 4.0
**Status**: Production Ready

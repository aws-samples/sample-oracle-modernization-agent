"""Report generator tool"""
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from strands import tool
import sys

# Add src to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils.project_paths import REPORTS_DIR


@tool
def generate_markdown_report(analysis_data: Dict, output_filename: str = "source_analysis.md") -> str:
    """Generate comprehensive markdown analysis report.
    
    Args:
        analysis_data: Dictionary containing all analysis results
        output_filename: Output filename (default: source_analysis.md)
        
    Returns:
        Path to generated report
    """
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / output_filename
    
    sections = []
    
    # Header
    sections.append(_generate_header())
    
    # Executive Summary
    sections.append(_generate_executive_summary(analysis_data))
    
    # Framework Analysis
    sections.append(_generate_framework_section(analysis_data.get('framework', {})))
    
    # MyBatis Mapper Analysis
    sections.append(_generate_mybatis_section(analysis_data.get('mappers', {})))
    
    # SQL Complexity Analysis
    sections.append(_generate_sql_complexity_section(analysis_data.get('complexity', {})))
    
    # Migration Strategy (if exists)
    sections.append(_generate_strategy_section())
    
    # Recommendations
    sections.append(_generate_recommendations(analysis_data))
    
    # Write report
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(sections))
    
    return str(report_path)


def _generate_header() -> str:
    return f"""# Java Source Code Analysis Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Analysis Type:** Oracle Migration Pre-Analysis

---"""


def _generate_executive_summary(data: Dict) -> str:
    framework = data.get('framework', {})
    mappers = data.get('mappers', {})
    complexity = data.get('complexity', {})
    
    # Calculate migration complexity level
    avg_complexity = complexity.get('average', 0)
    if avg_complexity < 5:
        migration_level = "Low"
        migration_desc = "대부분 단순 쿼리로 구성되어 마이그레이션이 비교적 용이합니다."
    elif avg_complexity < 10:
        migration_level = "Medium"
        migration_desc = "중간 복잡도의 쿼리가 포함되어 있어 일부 수작업이 필요합니다."
    else:
        migration_level = "High"
        migration_desc = "고복잡도 쿼리가 다수 포함되어 있어 상세한 변환 계획이 필요합니다."
    
    return f"""## Executive Summary

본 보고서는 Java 애플리케이션의 소스 코드를 분석하여 Oracle 데이터베이스 마이그레이션을 위한 사전 분석 결과를 제시합니다.

### 주요 발견사항

| 항목 | 내용 |
|------|------|
| **프레임워크** | {framework.get('name', 'Unknown')} |
| **빌드 도구** | {framework.get('build_tool', 'Unknown')} |
| **ORM 프레임워크** | MyBatis |
| **총 Mapper 파일** | {mappers.get('total', 0)}개 |
| **유효 Mapper** | {mappers.get('valid', 0)}개 ({mappers.get('valid', 0) / max(mappers.get('total', 1), 1) * 100:.1f}%) |
| **총 SQL 쿼리** | {complexity.get('total_queries', 0)}개 |
| **평균 SQL 복잡도** | {complexity.get('average', 0):.2f}점 |
| **마이그레이션 복잡도** | **{migration_level}** |

### 마이그레이션 평가

{migration_desc}

**복잡도 분포:**
- Simple (1-3점): {complexity.get('distribution', {}).get('Simple', 0)}개 ({complexity.get('distribution', {}).get('Simple', 0) / max(complexity.get('total_queries', 1), 1) * 100:.1f}%)
- Medium (4-7점): {complexity.get('distribution', {}).get('Medium', 0)}개 ({complexity.get('distribution', {}).get('Medium', 0) / max(complexity.get('total_queries', 1), 1) * 100:.1f}%)
- Complex (8-12점): {complexity.get('distribution', {}).get('Complex', 0)}개 ({complexity.get('distribution', {}).get('Complex', 0) / max(complexity.get('total_queries', 1), 1) * 100:.1f}%)
- Very Complex (13점+): {complexity.get('distribution', {}).get('Very Complex', 0)}개 ({complexity.get('distribution', {}).get('Very Complex', 0) / max(complexity.get('total_queries', 1), 1) * 100:.1f}%)

### 권장 사항

1. **우선순위**: Very Complex 및 Complex 쿼리부터 검토 시작
2. **예상 작업량**: 약 {_estimate_effort(complexity)}인일 소요 예상
3. **리스크**: {_assess_risk(complexity)}"""


def _generate_framework_section(framework: Dict) -> str:
    section = """## 1. Framework Analysis

### 1.1 프레임워크 식별

본 애플리케이션은 다음과 같은 기술 스택으로 구성되어 있습니다."""
    
    section += f"""

| 항목 | 내용 |
|------|------|
| 프레임워크 | {framework.get('name', 'Unknown')} |
| 빌드 도구 | {framework.get('build_tool', 'Unknown')} |
| 버전 | {framework.get('version', 'Unknown')} |
"""
    
    if framework.get('type'):
        section += "\n### 1.2 탐지된 프레임워크 패턴\n\n"
        section += "소스 코드 분석을 통해 다음 패턴들이 탐지되었습니다:\n\n"
        for pattern in framework['type']:
            section += f"- **{pattern}**: 해당 패턴의 어노테이션 및 클래스 사용 확인\n"
    
    if framework.get('dependencies'):
        section += f"\n### 1.3 주요 의존성 라이브러리 ({len(framework['dependencies'])}개)\n\n"
        section += "| Group ID | Artifact ID | Version |\n"
        section += "|----------|-------------|----------|\n"
        for dep in framework['dependencies'][:15]:
            section += f"| {dep['group']} | {dep['artifact']} | {dep['version']} |\n"
        
        if len(framework['dependencies']) > 15:
            section += f"\n*... 외 {len(framework['dependencies']) - 15}개 의존성*\n"

    mybatis_info = framework.get('mybatis_info', {})
    if mybatis_info.get('doctype_found'):
        section += "\n### 1.4 MyBatis DOCTYPE 처리 방침\n\n"
        section += f"| 항목 | 내용 |\n|------|------|\n"
        section += f"| MyBatis 버전 | {mybatis_info.get('version') or '3.x'} |\n"
        section += f"| DOCTYPE 존재 | {'있음' if mybatis_info['doctype_found'] else '없음'} |\n"
        section += f"| DOCTYPE 제거 가능 | {'✅ 가능' if mybatis_info.get('doctype_removable') else '❌ 불가'} |\n"
        if mybatis_info.get('note'):
            section += f"\n> {mybatis_info['note']}\n"

    return section


def _generate_mybatis_section(mappers: Dict) -> str:
    section = """## 2. MyBatis Mapper Analysis

### 2.1 매퍼 파일 개요

MyBatis를 ORM 프레임워크로 사용하고 있으며, 다음과 같은 매퍼 구성을 가지고 있습니다."""
    
    section += f"""

| 항목 | 개수 | 비율 |
|------|------|------|
| 총 Mapper 파일 | {mappers.get('total', 0)} | 100% |
| 유효 Mapper (SQL 포함) | {mappers.get('valid', 0)} | {mappers.get('valid', 0) / max(mappers.get('total', 1), 1) * 100:.1f}% |
| 빈 Mapper (SQL 없음) | {mappers.get('empty', 0)} | {mappers.get('empty', 0) / max(mappers.get('total', 1), 1) * 100:.1f}% |
"""
    
    if mappers.get('mappers'):
        section += "\n### 2.2 Mapper 파일 목록\n\n"
        section += "| No | 파일명 | Namespace | SQL 개수 |\n"
        section += "|----|--------|-----------|----------|\n"
        
        for idx, mapper in enumerate(mappers['mappers'][:20], 1):
            section += f"| {idx} | {mapper['name']} | {mapper.get('namespace', 'N/A')} | {mapper.get('sql_count', 0)} |\n"
        
        if len(mappers['mappers']) > 20:
            section += f"\n*... 외 {len(mappers['mappers']) - 20}개 매퍼*\n"
    
    return section


def _generate_sql_complexity_section(complexity: Dict) -> str:
    section = """## 3. SQL Complexity Analysis

### 3.1 복잡도 통계

SQL 쿼리의 복잡도를 분석하여 마이그레이션 난이도를 평가하였습니다."""
    
    section += f"""

| 지표 | 값 | 설명 |
|------|-----|------|
| 총 쿼리 수 | {complexity.get('total_queries', 0)} | 분석 대상 SQL 문 |
| 평균 복잡도 | {complexity.get('average', 0):.2f}점 | 전체 평균 |
| 최대 복잡도 | {complexity.get('max', 0)}점 | 가장 복잡한 쿼리 |
| 최소 복잡도 | {complexity.get('min', 0)}점 | 가장 단순한 쿼리 |
| 표준편차 | {_calculate_std_dev(complexity):.2f} | 복잡도 편차 |
"""
    
    # Complexity Distribution
    distribution = complexity.get('distribution', {})
    if distribution:
        total = complexity.get('total_queries', 1)
        section += "\n### 3.2 복잡도 분포\n\n"
        section += "| 복잡도 레벨 | 쿼리 수 | 비율 | 설명 |\n"
        section += "|-------------|---------|------|------|\n"
        
        level_desc = {
            'Simple': '기본 CRUD, 단순 조회',
            'Medium': 'JOIN, 집계 함수 포함',
            'Complex': '서브쿼리, 동적 SQL',
            'Very Complex': '다중 JOIN, 복잡한 로직'
        }
        
        for level in ['Simple', 'Medium', 'Complex', 'Very Complex']:
            count = distribution.get(level, 0)
            percentage = (count / total * 100) if total > 0 else 0
            section += f"| {level} | {count} | {percentage:.1f}% | {level_desc[level]} |\n"
    
    # Top Complex Queries
    details = complexity.get('details', [])
    if details:
        section += "\n### 3.3 고복잡도 쿼리 Top 10\n\n"
        section += "마이그레이션 시 우선적으로 검토가 필요한 고복잡도 쿼리 목록입니다.\n\n"
        section += "| 순위 | 파일 | Query ID | 타입 | 복잡도 | 레벨 |\n"
        section += "|------|------|----------|------|--------|------|\n"
        
        for idx, query in enumerate(details[:10], 1):
            section += f"| {idx} | {query['file']} | {query['id']} | {query['type']} | {query['score']} | {query['level']} |\n"
    
    # Oracle Pattern Usage
    oracle_patterns = complexity.get('oracle_patterns', [])
    if oracle_patterns:
        total_p = complexity.get('oracle_pattern_total', 0)
        section += f"\n### 3.4 Oracle 패턴 사용 현황 (총 {total_p}건)\n\n"
        section += "변환이 필요한 Oracle 고유 패턴의 사용 빈도입니다.\n\n"
        section += "| 패턴 | 사용 횟수 | 비율 | PostgreSQL 변환 |\n"
        section += "|------|----------|------|----------------|\n"
        
        for p in oracle_patterns:
            section += f"| {p['pattern']} | {p['count']} | {p['percentage']}% | {p['postgresql']} |\n"
    
    return section


def _generate_recommendations(data: Dict) -> str:
    complexity = data.get('complexity', {})
    mappers = data.get('mappers', {})
    
    section = """## 4. Recommendations

### 4.1 마이그레이션 전략"""
    
    recommendations = []
    
    # Based on complexity
    avg_complexity = complexity.get('average', 0)
    very_complex_count = complexity.get('distribution', {}).get('Very Complex', 0)
    
    if very_complex_count > 0:
        recommendations.append(f"- **고복잡도 쿼리 우선 처리**: {very_complex_count}개의 Very Complex 쿼리를 먼저 분석하고 변환 전략 수립")
    
    if avg_complexity > 10:
        recommendations.append("- **전문가 검토 필요**: 평균 복잡도가 높아 데이터베이스 전문가의 검토가 필요합니다")
    
    if mappers.get('empty', 0) > 0:
        recommendations.append(f"- **빈 Mapper 정리**: {mappers.get('empty', 0)}개의 빈 Mapper 파일을 마이그레이션 전에 정리 권장")
    
    recommendations.append("- **단계적 마이그레이션**: Simple → Medium → Complex → Very Complex 순서로 진행")
    recommendations.append("- **테스트 자동화**: 각 쿼리별 결과 비교를 위한 자동화 테스트 구축")
    
    section += "\n\n" + "\n".join(recommendations)
    
    section += """

### 4.2 예상 작업 일정"""
    
    effort = _estimate_effort(complexity)
    section += f"""

| 단계 | 작업 내용 | 예상 기간 |
|------|-----------|-----------|
| 1단계 | Simple 쿼리 변환 | {int(effort * 0.2)}인일 |
| 2단계 | Medium 쿼리 변환 | {int(effort * 0.3)}인일 |
| 3단계 | Complex 쿼리 변환 | {int(effort * 0.3)}인일 |
| 4단계 | Very Complex 쿼리 변환 | {int(effort * 0.2)}인일 |
| **합계** | | **{effort}인일** |

*위 일정은 예상치이며, 실제 작업 시 변동될 수 있습니다.*

### 4.3 리스크 관리

- **기술적 리스크**: 복잡한 쿼리의 성능 저하 가능성
- **일정 리스크**: 예상보다 복잡도가 높은 쿼리 발견 시 지연 가능
- **품질 리스크**: 변환 후 결과 불일치 가능성

**대응 방안:**
1. 충분한 테스트 기간 확보
2. 단계별 검증 프로세스 수립
3. 롤백 계획 사전 준비"""
    
    return section


def _estimate_effort(complexity: Dict) -> int:
    """Estimate effort in person-days"""
    distribution = complexity.get('distribution', {})
    
    simple = distribution.get('Simple', 0) * 0.1
    medium = distribution.get('Medium', 0) * 0.3
    complex_q = distribution.get('Complex', 0) * 0.5
    very_complex = distribution.get('Very Complex', 0) * 1.0
    
    total = simple + medium + complex_q + very_complex
    return max(int(total), 1)


def _assess_risk(complexity: Dict) -> str:
    """Assess migration risk level"""
    avg = complexity.get('average', 0)
    very_complex = complexity.get('distribution', {}).get('Very Complex', 0)
    
    if avg > 10 or very_complex > 10:
        return "**High** - 고복잡도 쿼리 다수, 상세 검토 필수"
    elif avg > 7 or very_complex > 5:
        return "**Medium** - 일부 복잡한 쿼리 존재, 주의 필요"
    else:
        return "**Low** - 대부분 단순 쿼리, 마이그레이션 용이"


def _calculate_std_dev(complexity: Dict) -> float:
    """Calculate standard deviation using all scores"""
    scores = complexity.get('all_scores', [])
    if not scores:
        return 0.0

    avg = sum(scores) / len(scores)
    variance = sum((x - avg) ** 2 for x in scores) / len(scores)
    return variance ** 0.5


def _generate_strategy_section() -> str:
    """Generate migration strategy section from output/strategy/transform_strategy.md"""
    from pathlib import Path
    
    section = """## 3.5 Migration Strategy

### 3.5.1 일반 변환 규칙 (정적)

모든 Oracle → PostgreSQL 마이그레이션에 공통으로 적용되는 규칙입니다.

**4-Phase 변환 프로세스:**

1. **Phase 1: Structural Processing** (구조 정리)
   - 스키마 제거, Oracle Hint 제거, DUAL 제거, DB Link 제거

2. **Phase 2: Syntax Conversions** (구문 변환)
   - Comma JOIN → Explicit JOIN
   - `(+)` → `LEFT/RIGHT JOIN`
   - 서브쿼리 별칭 추가

3. **Phase 3: Functions & Operators** (함수 및 연산자)
   - `||` → `CONCAT()`, `NVL()` → `COALESCE()`
   - `DECODE()` → `CASE WHEN`, `SYSDATE` → `CURRENT_TIMESTAMP`
   - 날짜/시간 함수, 시퀀스 함수 등

4. **Phase 4: Advanced Patterns** (고급 패턴)
   - `CONNECT BY` → `WITH RECURSIVE`
   - `MERGE INTO` → `INSERT ... ON CONFLICT`
   - `ROWNUM` → `LIMIT/OFFSET`

**참조 규칙** (각 Phase에서 적용): Parameter Casting, XML 특수 문자 처리

**상세 규칙:** `src/reference/oracle_to_postgresql_rules.md`

---

### 3.5.2 프로젝트별 변환 전략 (동적)

"""
    
    strategy_file = Path(__file__).parent.parent.parent.parent.parent / "output" / "strategy" / "transform_strategy.md"
    
    if not strategy_file.exists():
        section += "*전략 문서가 아직 생성되지 않았습니다. Analyze 단계 완료 후 자동 생성됩니다.*"
        return section
    
    try:
        strategy_content = strategy_file.read_text(encoding='utf-8')
        
        section += "이 프로젝트의 SQL 패턴을 분석하여 생성된 맞춤형 변환 규칙입니다.\n\n"
        
        # Extract project characteristics
        if "## 프로젝트 특성 분석" in strategy_content:
            section += "**프로젝트 특성:**\n"
            # Extract statistics section
            import re
            stats_match = re.search(r'### SQL 패턴 통계\n(.+?)(?=###|\n##|\Z)', strategy_content, re.DOTALL)
            if stats_match:
                stats = stats_match.group(1).strip()
                # Format as bullet points
                for line in stats.split('\n'):
                    if line.strip() and not line.startswith('#'):
                        section += f"- {line.strip()}\n"
        
        # Extract rule count
        rule_count = strategy_content.count('### 규칙')
        if rule_count > 0:
            section += f"\n**프로젝트 특화 규칙:** {rule_count}개 생성\n\n"
            
            # Extract rules as table
            import re
            rules = re.findall(r'### 규칙 \d+: (.+?)\n\*\*발견\*\*: (.+?)\n\*\*빈도\*\*: (.+?)\n', strategy_content, re.DOTALL)
            
            if rules:
                section += "| 규칙 | 발견 패턴 | 빈도 |\n"
                section += "|------|-----------|------|\n"
                for idx, (rule_name, pattern, frequency) in enumerate(rules[:5], 1):
                    rule_name = rule_name.strip()
                    pattern = pattern.strip().replace('\n', ' ')[:50] + '...' if len(pattern.strip()) > 50 else pattern.strip()
                    frequency = frequency.strip()
                    section += f"| {rule_name} | {pattern} | {frequency} |\n"
                
                if len(rules) > 5:
                    section += f"\n*... 외 {len(rules) - 5}개 규칙*\n"
        
        section += f"\n**전략 문서:** `output/strategy/transform_strategy.md`\n"
        section += "\n**적용 우선순위:** 일반 규칙 > 프로젝트 전략 (프로젝트 전략은 일반 규칙의 보충)\n"
        
        return section
        
    except Exception as e:
        return section + f"\n*전략 문서 읽기 실패: {e}*"

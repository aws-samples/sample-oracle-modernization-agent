"""Framework and technology stack analyzer"""
from pathlib import Path
from typing import Dict
import defusedxml.ElementTree as ET
from strands import tool


@tool
def analyze_framework(source_folder: str) -> Dict:
    """Analyze project framework and dependencies.
    
    Args:
        source_folder: Root folder of the project
        
    Returns:
        Framework information including name, version, dependencies
    """
    source_path = Path(source_folder)
    result = {
        'name': 'Unknown',
        'version': 'Unknown',
        'build_tool': 'Unknown',
        'type': [],
        'dependencies': []
    }
    
    # Check for pom.xml (Maven)
    pom_path = source_path.parent / "pom.xml"
    if pom_path.exists():
        result.update(_analyze_maven(pom_path))
    
    # Check for build.gradle (Gradle)
    gradle_path = source_path.parent / "build.gradle"
    if gradle_path.exists():
        result['build_tool'] = 'Gradle'
    
    # Detect framework patterns in source code
    result['type'] = _detect_framework_patterns(source_path)

    # Detect MyBatis version and DOCTYPE usage
    result['mybatis_info'] = _detect_mybatis_info(source_path, result.get('dependencies', []))

    return result


def _analyze_maven(pom_path: Path) -> Dict:
    """Analyze Maven pom.xml"""
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
        
        deps = []
        for dep in root.findall('.//m:dependency', ns):
            group = dep.find('m:groupId', ns)
            artifact = dep.find('m:artifactId', ns)
            version = dep.find('m:version', ns)
            
            if group is not None and artifact is not None:
                deps.append({
                    'group': group.text,
                    'artifact': artifact.text,
                    'version': version.text if version is not None else 'N/A'
                })
        
        # Detect framework from dependencies
        framework_name = 'Unknown'
        for dep in deps:
            if 'spring' in dep['artifact'].lower():
                framework_name = 'Spring Framework'
                break
            elif 'struts' in dep['artifact'].lower():
                framework_name = 'Struts'
                break
        
        return {
            'name': framework_name,
            'build_tool': 'Maven',
            'dependencies': deps
        }
    except Exception:
        return {'build_tool': 'Maven'}


def _detect_mybatis_info(source_path: Path, dependencies: list) -> dict:
    """Detect MyBatis version from dependencies and DOCTYPE usage from mapper XMLs."""
    info = {'version': None, 'doctype_found': False, 'doctype_removable': False}

    # Get version from dependencies
    for dep in dependencies:
        if 'mybatis' in dep.get('artifact', '').lower():
            info['version'] = dep.get('version')
            break

    # Sample mapper XMLs for DOCTYPE
    xml_files = list(source_path.rglob("*.xml"))[:20]
    for xml_file in xml_files:
        try:
            first_lines = xml_file.read_text(encoding='utf-8', errors='ignore')[:300]
            if '<!DOCTYPE mapper' in first_lines or '<!DOCTYPE configuration' in first_lines:
                info['doctype_found'] = True
                break
        except Exception:
            continue

    # MyBatis 3.x+ supports DOCTYPE-free operation
    if info['doctype_found']:
        version = info.get('version') or ''
        major = int(version.split('.')[0]) if version and version[0].isdigit() else 3
        info['doctype_removable'] = major >= 3
        info['note'] = (
            f"MyBatis {version or '3.x'} 감지: DOCTYPE 제거 적용 "
            "(3.x+는 DOCTYPE 없이 정상 동작, XXE 취약점 원천 차단)"
            if info['doctype_removable']
            else "MyBatis 2.x 감지: DOCTYPE 제거 불가"
        )

    return info


def _detect_framework_patterns(source_path: Path) -> list:
    """Detect framework patterns in Java files"""
    patterns = set()
    java_files = list(source_path.rglob("*.java"))[:50]  # Sample 50 files
    
    for java_file in java_files:
        try:
            content = java_file.read_text(encoding='utf-8', errors='ignore')
            
            if '@Controller' in content or '@RestController' in content:
                patterns.add('Spring MVC')
            if '@Service' in content or '@Component' in content:
                patterns.add('Spring Core')
            if '@Entity' in content or '@Table' in content:
                patterns.add('JPA')
            if 'extends HttpServlet' in content:
                patterns.add('Servlet')
        except Exception:
            continue

    return list(patterns)

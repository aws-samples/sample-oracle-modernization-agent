"""File scanner tool for MyBatis XML and Java files"""
from pathlib import Path
from typing import List, Dict
import defusedxml.ElementTree as ET
from strands import tool


@tool
def scan_mybatis_mappers(source_folder: str) -> Dict:
    """Scan and identify MyBatis Mapper XML files.
    
    Args:
        source_folder: Root folder to scan for XML files
        
    Returns:
        Dictionary with mapper files list and statistics
    """
    source_path = Path(source_folder)
    mappers = []
    
    # Find all XML files
    xml_files = list(source_path.rglob("*.xml"))
    
    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Check if it's a MyBatis mapper
            if root.tag == 'mapper' or 'mapper' in root.tag:
                namespace = root.get('namespace', 'Unknown')
                
                # Count SQL statements
                sql_count = len(root.findall('.//*[@id]'))
                
                mappers.append({
                    'path': str(xml_file),
                    'name': xml_file.name,
                    'relative': str(xml_file.relative_to(source_path)),
                    'namespace': namespace,
                    'sql_count': sql_count
                })
        except Exception:
            continue

    return {
        'total': len(mappers),
        'valid': len([m for m in mappers if m['sql_count'] > 0]),
        'empty': len([m for m in mappers if m['sql_count'] == 0]),
        'mappers': mappers
    }


@tool
def scan_java_files(source_folder: str, pattern: str = None) -> Dict:
    """Scan Java files for specific patterns.
    
    Args:
        source_folder: Root folder to scan
        pattern: Optional regex pattern to search for
        
    Returns:
        Dictionary with Java files and match statistics
    """
    source_path = Path(source_folder)
    java_files = list(source_path.rglob("*.java"))
    
    results = {
        'total': len(java_files),
        'files': [str(f) for f in java_files[:100]]  # Limit to 100 for performance
    }
    
    if pattern:
        import re
        matches = []
        for java_file in java_files:
            try:
                content = java_file.read_text(encoding='utf-8', errors='ignore')
                if re.search(pattern, content, re.IGNORECASE):
                    matches.append(str(java_file))
            except Exception:
                continue
        results['matches'] = matches
        results['match_count'] = len(matches)
    
    return results

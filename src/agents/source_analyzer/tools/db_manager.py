"""Database manager tool for SQLite operations"""
import sqlite3
from typing import List, Dict
from strands import tool
import sys
from pathlib import Path

# Add src to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils.project_paths import DB_PATH


@tool
def save_xml_list(xml_files: str) -> str:
    """Save XML file list to database.
    
    Args:
        xml_files: JSON string of XML file list or scan result.
                  Accepts both formats:
                  - JSON array: [{'path': '...', 'name': '...', 'relative': '...'}]
                  - JSON object: {'total': 11, 'mappers': [...]}
        
    Returns:
        Success message with count
    """
    import json
    
    # Parse JSON string
    try:
        xml_files = json.loads(xml_files)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: xml_files must be a valid JSON string. Got error: {e}"
    # Auto-detect format and extract mapper list
    if isinstance(xml_files, dict):
        if 'mappers' in xml_files:
            xml_files = xml_files['mappers']
        else:
            raise ValueError(f"If dict is provided, it must have 'mappers' key. Got keys: {list(xml_files.keys())}")
    
    if not isinstance(xml_files, list):
        raise ValueError(f"xml_files must be a list or dict, got {type(xml_files)}")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Drop and recreate table for clean reset
    cursor.execute("DROP TABLE IF EXISTS source_xml_list")
    cursor.execute("""
        CREATE TABLE source_xml_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            relative_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert data
    for xml_file in xml_files:
        cursor.execute("""
            INSERT INTO source_xml_list (file_path, file_name, relative_path)
            VALUES (?, ?, ?)
        """, (xml_file['path'], xml_file['name'], xml_file['relative']))
    
    conn.commit()
    count = len(xml_files)
    conn.close()
    
    return f"Saved {count} XML files to database"


@tool
def get_java_source_folder() -> str:
    """Get JAVA_SOURCE_FOLDER from database.
    
    Returns:
        Path to Java source folder
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM properties WHERE key = 'JAVA_SOURCE_FOLDER'")
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        raise ValueError("JAVA_SOURCE_FOLDER not found in properties table")
    
    return result[0]

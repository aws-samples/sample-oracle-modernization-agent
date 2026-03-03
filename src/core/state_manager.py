"""StateManager - Unified interface for database access"""
import sqlite3
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from contextlib import contextmanager


class StateManager:
    """
    StateManager provides a unified interface for database access.

    Responsibilities:
    - SQL status updates (transformed, reviewed, validated, tested)
    - Task retrieval (pending tasks, SQL info)
    - Pipeline status queries (step counts, completion flags)
    - Step reset operations

    Benefits:
    - Centralized DB access logic
    - Consistent error handling
    - Reduced code duplication
    - Easier testing and maintenance
    """

    def __init__(self, db_path: Path):
        """
        Initialize StateManager.

        Args:
            db_path: Path to oma_control.db
        """
        self.db_path = db_path
        self.timeout = 10  # seconds

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            yield conn
        finally:
            conn.close()

    # ========== SQL Status Updates ==========

    def update_sql_status(
        self,
        mapper_file: str,
        sql_id: str,
        **kwargs
    ) -> None:
        """
        Update SQL status in transform_target_list.

        Args:
            mapper_file: Mapper file name
            sql_id: SQL statement ID
            **kwargs: Status fields to update (e.g., transformed='Y', validated='Y')

        Example:
            state.update_sql_status('UserMapper.xml', 'selectUser', transformed='Y')
            state.update_sql_status('UserMapper.xml', 'selectUser', reviewed='Y', validated='Y')
        """
        if not kwargs:
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build UPDATE with explicit column mapping to avoid SQL injection
            # Each column is explicitly handled to satisfy security scanners
            updates = []
            values = []

            if 'transformed' in kwargs:
                updates.append("transformed=?")
                values.append(kwargs['transformed'])
            if 'reviewed' in kwargs:
                updates.append("reviewed=?")
                values.append(kwargs['reviewed'])
            if 'validated' in kwargs:
                updates.append("validated=?")
                values.append(kwargs['validated'])
            if 'tested' in kwargs:
                updates.append("tested=?")
                values.append(kwargs['tested'])
            if 'transform_count' in kwargs:
                updates.append("transform_count=?")
                values.append(kwargs['transform_count'])
            if 'review_result' in kwargs:
                updates.append("review_result=?")
                values.append(kwargs['review_result'])
            if 'validation_result' in kwargs:
                updates.append("validation_result=?")
                values.append(kwargs['validation_result'])
            if 'test_result' in kwargs:
                updates.append("test_result=?")
                values.append(kwargs['test_result'])

            if not updates:
                return

            updates.append("updated_at=CURRENT_TIMESTAMP")
            values.extend([mapper_file, sql_id])

            cursor.execute(
                "UPDATE transform_target_list SET " + ", ".join(updates) + " WHERE mapper_file=? AND sql_id=?",
                values
            )
            conn.commit()

    def increment_transform_count(self, mapper_file: str, sql_id: str) -> None:
        """Increment transform_count for a SQL (used for retry tracking)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE transform_target_list
                SET transform_count = COALESCE(transform_count, 0) + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE mapper_file=? AND sql_id=?
            """, (mapper_file, sql_id))
            conn.commit()

    # ========== Task Retrieval ==========

    def get_pending_tasks(self, step: str) -> List[Tuple[str, str]]:
        """
        Get pending tasks for a pipeline step.

        Args:
            step: Pipeline step ('transform', 'review', 'validate', 'test')

        Returns:
            List of (mapper_file, sql_id) tuples

        Example:
            pending = state.get_pending_tasks('transform')
            # [('UserMapper.xml', 'selectUser'), ...]
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Explicit SQL for each step to avoid dynamic SQL injection warnings
            if step == 'transform':
                cursor.execute("""
                    SELECT mapper_file, sql_id
                    FROM transform_target_list
                    WHERE transformed='N'
                    ORDER BY mapper_file, seq_no
                """)
            elif step == 'review':
                cursor.execute("""
                    SELECT mapper_file, sql_id
                    FROM transform_target_list
                    WHERE reviewed='N'
                    ORDER BY mapper_file, seq_no
                """)
            elif step == 'validate':
                cursor.execute("""
                    SELECT mapper_file, sql_id
                    FROM transform_target_list
                    WHERE validated='N'
                    ORDER BY mapper_file, seq_no
                """)
            elif step == 'test':
                cursor.execute("""
                    SELECT mapper_file, sql_id
                    FROM transform_target_list
                    WHERE tested='N'
                    ORDER BY mapper_file, seq_no
                """)
            else:
                raise ValueError(f"Invalid step: {step}. Must be one of: transform, review, validate, test")

            return cursor.fetchall()

    def get_sql_info(
        self,
        mapper_file: str,
        sql_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed SQL information.

        Args:
            mapper_file: Mapper file name
            sql_id: SQL statement ID

        Returns:
            Dict with SQL info or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT mapper_file, sql_id, sql_type, namespace, source_file, target_file,
                       transformed, reviewed, validated, tested
                FROM transform_target_list
                WHERE mapper_file=? AND sql_id=?
            """, (mapper_file, sql_id))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'mapper_file': row[0],
                'sql_id': row[1],
                'sql_type': row[2],
                'namespace': row[3],
                'source_file': row[4],
                'target_file': row[5],
                'transformed': row[6],
                'reviewed': row[7],
                'validated': row[8],
                'tested': row[9]
            }

    # ========== Pipeline Status ==========

    def get_step_counts(self) -> Dict[str, int]:
        """
        Get counts for each pipeline step.

        Returns:
            Dict with step counts and completion flags

        Example:
            {
                'source_analyzed': 1,
                'extracted': 127,
                'transformed': 127,
                'reviewed': 125,
                'validated': 127,
                'tested': 120,
                'transform_complete': True,
                'review_complete': True,
                'validate_complete': True,
                'test_complete': False
            }
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if source_xml_list exists
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='source_xml_list'")
            has_source_table = cursor.fetchone()[0] > 0

            if has_source_table:
                cursor.execute("SELECT COUNT(*) FROM source_xml_list")
                source_analyzed = cursor.fetchone()[0]
            else:
                source_analyzed = 0

            # Get transform_target_list counts
            cursor.execute("SELECT COUNT(*) FROM transform_target_list")
            extracted = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='Y'")
            transformed = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE reviewed='Y'")
            reviewed = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE validated='Y'")
            validated = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y'")
            tested = cursor.fetchone()[0]

            # Completion flags
            transform_complete = (extracted > 0 and transformed == extracted)
            review_complete = (transformed > 0 and reviewed == transformed)
            validate_complete = (reviewed > 0 and validated == reviewed)
            test_complete = (validated > 0 and tested == validated)

            return {
                'source_analyzed': source_analyzed,
                'extracted': extracted,
                'transformed': transformed,
                'reviewed': reviewed,
                'validated': validated,
                'tested': tested,
                'merged': 0,  # TODO: implement merge tracking
                'transform_complete': transform_complete,
                'review_complete': review_complete,
                'validate_complete': validate_complete,
                'test_complete': test_complete,
                'merge_complete': False  # TODO: implement merge tracking
            }

    def reset_step_status(self, step: str) -> int:
        """
        Reset status for a pipeline step.

        Args:
            step: Pipeline step ('transform', 'review', 'validate', 'test')

        Returns:
            Number of rows reset
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Explicit SQL for each step to avoid dynamic SQL injection warnings
            if step == 'transform':
                cursor.execute("""
                    UPDATE transform_target_list
                    SET transformed='N', updated_at=CURRENT_TIMESTAMP
                    WHERE transformed='Y'
                """)
            elif step == 'review':
                cursor.execute("""
                    UPDATE transform_target_list
                    SET reviewed='N', updated_at=CURRENT_TIMESTAMP
                    WHERE reviewed='Y'
                """)
            elif step == 'validate':
                cursor.execute("""
                    UPDATE transform_target_list
                    SET validated='N', updated_at=CURRENT_TIMESTAMP
                    WHERE validated='Y'
                """)
            elif step == 'test':
                cursor.execute("""
                    UPDATE transform_target_list
                    SET tested='N', updated_at=CURRENT_TIMESTAMP
                    WHERE tested='Y'
                """)
            else:
                raise ValueError(f"Invalid step: {step}. Must be one of: transform, review, validate, test")

            reset_count = cursor.rowcount
            conn.commit()
            return reset_count

    # ========== Property Management ==========

    def get_property(self, key: str) -> Optional[str]:
        """Get a property value from properties table"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM properties WHERE key=?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_property(self, key: str, value: str) -> None:
        """Set a property value in properties table"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO properties (key, value)
                VALUES (?, ?)
            """, (key, value))
            conn.commit()

    # ========== Failure Case Queries ==========

    def get_validation_failures(self, limit: int = 20) -> List[Tuple[str, str, str, int]]:
        """
        Get SQLs that failed validation (multiple transform attempts).

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of (mapper_file, sql_id, validated, transform_count) tuples
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT mapper_file, sql_id, validated, transform_count
                FROM transform_target_list
                WHERE validated = 'N' AND transform_count > 1
                ORDER BY transform_count DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def get_test_failures(self, limit: int = 20) -> List[Tuple[str, str, str, str]]:
        """
        Get SQLs that failed testing.

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of (mapper_file, sql_id, tested, test_result) tuples
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT mapper_file, sql_id, tested, test_result
                FROM transform_target_list
                WHERE tested = 'N' AND test_result LIKE '%FAIL%'
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def search_sqls(
        self,
        keyword: str = "",
        limit: int = 50
    ) -> List[Tuple[str, str, str]]:
        """
        Search SQL IDs by keyword in mapper_file or sql_id.

        Args:
            keyword: Search term (searches both mapper_file and sql_id)
            limit: Maximum number of results

        Returns:
            List of (mapper_file, sql_id, sql_type) tuples

        Example:
            results = state.search_sqls('User')
            # [('UserMapper.xml', 'selectUser', 'select'), ...]
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if keyword:
                cursor.execute("""
                    SELECT mapper_file, sql_id, sql_type
                    FROM transform_target_list
                    WHERE mapper_file LIKE ? OR sql_id LIKE ?
                    ORDER BY mapper_file, seq_no
                    LIMIT ?
                """, (f'%{keyword}%', f'%{keyword}%', limit))
            else:
                cursor.execute("""
                    SELECT mapper_file, sql_id, sql_type
                    FROM transform_target_list
                    ORDER BY mapper_file, seq_no
                    LIMIT ?
                """, (limit,))

            return cursor.fetchall()

    # ========== Helper Methods ==========

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name=?
            """, (table_name,))
            return cursor.fetchone()[0] > 0

    def add_column_if_not_exists(self, table: str, column: str, column_type: str) -> None:
        """
        Add a column to a table if it doesn't exist.

        Args:
            table: Table name (alphanumeric and underscore only)
            column: Column name (alphanumeric and underscore only)
            column_type: SQLite column type (alphanumeric, spaces, and parentheses only)

        Raises:
            ValueError: If table/column/type contains invalid characters

        Security Note:
            All parameters are strictly validated with regex before use.
            PRAGMA and ALTER TABLE do not support prepared statements,
            so input validation is the security mechanism here.
        """
        # Strict validation: only allow safe SQL identifiers
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
            raise ValueError(f"Invalid table name: {table}")
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column):
            raise ValueError(f"Invalid column name: {column}")
        # Validate column type (only allow safe type definitions)
        if not re.match(r'^[a-zA-Z0-9_\s()]+$', column_type):
            raise ValueError(f"Invalid column type: {column_type}")

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # PRAGMA table_info does not support parameterized queries
            # Table name has been validated with strict regex above
            pragma_query = "PRAGMA table_info(" + table + ")"
            cursor.execute(pragma_query)
            cols = [c[1] for c in cursor.fetchall()]

            if column not in cols:
                # ALTER TABLE does not support parameterized queries
                # All identifiers validated with strict regex above
                alter_query = "ALTER TABLE " + table + " ADD COLUMN " + column + " " + column_type
                cursor.execute(alter_query)
                conn.commit()

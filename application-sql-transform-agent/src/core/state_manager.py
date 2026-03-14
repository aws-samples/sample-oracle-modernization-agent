"""StateManager - Unified interface for database access using SQLAlchemy ORM

Security: All database operations use SQLAlchemy ORM to prevent SQL injection.
No raw SQL string concatenation is used.
"""
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from contextlib import contextmanager
from sqlalchemy import create_engine, inspect, select, update as sql_update, func, or_
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    TransformTargetList,
    Properties,
    SourceXmlList
)


class StateManager:
    """
    StateManager provides a unified interface for database access using SQLAlchemy ORM.

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
    - SQL injection prevention via ORM
    """

    def __init__(self, db_path: Path):
        """
        Initialize StateManager with SQLAlchemy engine.

        Args:
            db_path: Path to oma_control.db
        """
        self.db_path = db_path
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            connect_args={"timeout": 10},
            echo=False
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def _get_session(self) -> Session:
        """Context manager for database sessions"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ========== SQL Status Updates ==========

    def update_sql_status(
        self,
        mapper_file: str,
        sql_id: str,
        **kwargs
    ) -> None:
        """
        Update SQL status in transform_target_list using SQLAlchemy ORM.

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

        # Security: whitelist of allowed columns to prevent invalid updates
        ALLOWED_COLUMNS = {
            'transformed', 'reviewed', 'validated', 'tested',
            'transform_count', 'review_result', 'validation_result', 'test_result'
        }

        # Validate all keys are in whitelist
        invalid_keys = set(kwargs.keys()) - ALLOWED_COLUMNS
        if invalid_keys:
            raise ValueError(f"Invalid column names: {invalid_keys}. Allowed: {ALLOWED_COLUMNS}")

        with self._get_session() as session:
            # Use SQLAlchemy ORM update - completely prevents SQL injection
            stmt = (
                sql_update(TransformTargetList)
                .where(
                    TransformTargetList.mapper_file == mapper_file,
                    TransformTargetList.sql_id == sql_id
                )
                .values(**kwargs, updated_at=func.current_timestamp())
            )
            session.execute(stmt)

    def increment_transform_count(self, mapper_file: str, sql_id: str) -> None:
        """Increment transform_count for a SQL (used for retry tracking)"""
        with self._get_session() as session:
            stmt = (
                sql_update(TransformTargetList)
                .where(
                    TransformTargetList.mapper_file == mapper_file,
                    TransformTargetList.sql_id == sql_id
                )
                .values(
                    transform_count=func.coalesce(TransformTargetList.transform_count, 0) + 1,
                    updated_at=func.current_timestamp()
                )
            )
            session.execute(stmt)

    # ========== Task Retrieval ==========

    def get_pending_tasks(self, step: str) -> List[Tuple[str, str]]:
        """
        Get pending tasks for a pipeline step using SQLAlchemy ORM.

        Args:
            step: Pipeline step ('transform', 'review', 'validate', 'test')

        Returns:
            List of (mapper_file, sql_id) tuples

        Example:
            pending = state.get_pending_tasks('transform')
            # [('UserMapper.xml', 'selectUser'), ...]
        """
        # Map step to column attribute - type-safe ORM access
        step_column_map = {
            'transform': TransformTargetList.transformed,
            'review': TransformTargetList.reviewed,
            'validate': TransformTargetList.validated,
            'test': TransformTargetList.tested
        }

        if step not in step_column_map:
            raise ValueError(f"Invalid step: {step}. Must be one of: transform, review, validate, test")

        with self._get_session() as session:
            column = step_column_map[step]
            stmt = (
                select(TransformTargetList.mapper_file, TransformTargetList.sql_id)
                .where(column == 'N')
                .order_by(TransformTargetList.mapper_file, TransformTargetList.seq_no)
            )
            results = session.execute(stmt).all()
            return [(row[0], row[1]) for row in results]

    def get_sql_info(
        self,
        mapper_file: str,
        sql_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed SQL information using SQLAlchemy ORM.

        Args:
            mapper_file: Mapper file name
            sql_id: SQL statement ID

        Returns:
            Dict with SQL info or None if not found
        """
        with self._get_session() as session:
            stmt = (
                select(TransformTargetList)
                .where(
                    TransformTargetList.mapper_file == mapper_file,
                    TransformTargetList.sql_id == sql_id
                )
            )
            result = session.execute(stmt).scalar_one_or_none()

            if not result:
                return None

            return {
                'mapper_file': result.mapper_file,
                'sql_id': result.sql_id,
                'sql_type': result.sql_type,
                'namespace': result.namespace,
                'source_file': result.source_file,
                'target_file': result.target_file,
                'transformed': result.transformed,
                'reviewed': result.reviewed,
                'validated': result.validated,
                'tested': result.tested
            }

    # ========== Pipeline Status ==========

    def get_step_counts(self) -> Dict[str, int]:
        """
        Get counts for each pipeline step using SQLAlchemy ORM.

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
        with self._get_session() as session:
            # Check if source_xml_list table exists
            inspector = inspect(self.engine)
            has_source_table = 'source_xml_list' in inspector.get_table_names()

            if has_source_table:
                source_analyzed = session.query(func.count(SourceXmlList.id)).scalar()
            else:
                source_analyzed = 0

            # Get transform_target_list counts using ORM
            extracted = session.query(func.count(TransformTargetList.id)).scalar()

            transformed = session.query(func.count(TransformTargetList.id))\
                .filter(TransformTargetList.transformed == 'Y').scalar()

            reviewed = session.query(func.count(TransformTargetList.id))\
                .filter(TransformTargetList.reviewed == 'Y').scalar()

            review_failed = session.query(func.count(TransformTargetList.id))\
                .filter(TransformTargetList.reviewed == 'F').scalar()

            validated = session.query(func.count(TransformTargetList.id))\
                .filter(TransformTargetList.validated == 'Y').scalar()

            tested = session.query(func.count(TransformTargetList.id))\
                .filter(TransformTargetList.tested == 'Y').scalar()

            # Completion flags: step is complete when no 'N' remains
            # (all items are either 'Y' or 'F')
            transform_complete = (extracted > 0 and transformed == extracted)
            review_complete = (transformed > 0 and (reviewed + review_failed) == transformed)
            validate_complete = (reviewed > 0 and validated == reviewed)
            test_complete = (validated > 0 and tested == validated)

            return {
                'source_analyzed': source_analyzed,
                'extracted': extracted,
                'transformed': transformed,
                'reviewed': reviewed,
                'review_failed': review_failed,
                'validated': validated,
                'tested': tested,
                'merged': self._count_merge_files(),
                'transform_complete': transform_complete,
                'review_complete': review_complete,
                'validate_complete': validate_complete,
                'test_complete': test_complete,
                'merge_complete': self._count_merge_files() > 0,
            }

    @staticmethod
    def _count_merge_files() -> int:
        from utils.project_paths import MERGE_DIR
        if MERGE_DIR.exists():
            return len(list(MERGE_DIR.rglob("*.xml")))
        return 0

    def reset_step_status(self, step: str) -> int:
        """
        Reset status for a pipeline step using SQLAlchemy ORM.

        Args:
            step: Pipeline step ('transform', 'review', 'validate', 'test')

        Returns:
            Number of rows reset
        """
        # Map step to column attribute - type-safe ORM access
        step_column_map = {
            'transform': 'transformed',
            'review': 'reviewed',
            'validate': 'validated',
            'test': 'tested'
        }

        if step not in step_column_map:
            raise ValueError(f"Invalid step: {step}. Must be one of: transform, review, validate, test")

        column_name = step_column_map[step]

        with self._get_session() as session:
            # Get column attribute dynamically but safely (no SQL injection risk with ORM)
            column_attr = getattr(TransformTargetList, column_name)

            # Reset both 'Y' and 'F' (review FAIL) back to 'N'
            stmt = (
                sql_update(TransformTargetList)
                .where(column_attr.in_(['Y', 'F']))
                .values(**{column_name: 'N', 'updated_at': func.current_timestamp()})
            )
            result = session.execute(stmt)
            return result.rowcount

    # ========== Property Management ==========

    def get_property(self, key: str) -> Optional[str]:
        """Get a property value from properties table using ORM"""
        with self._get_session() as session:
            stmt = select(Properties.value).where(Properties.key == key)
            result = session.execute(stmt).scalar_one_or_none()
            return result

    def set_property(self, key: str, value: str) -> None:
        """Set a property value in properties table using ORM"""
        with self._get_session() as session:
            # Check if property exists
            existing = session.query(Properties).filter(Properties.key == key).first()

            if existing:
                # Update existing
                existing.value = value
                existing.updated_at = func.current_timestamp()
            else:
                # Insert new
                new_prop = Properties(key=key, value=value)
                session.add(new_prop)

    # ========== Failure Case Queries ==========

    def get_validation_failures(self, limit: int = 20) -> List[Tuple[str, str, str, int]]:
        """
        Get SQLs that failed validation (multiple transform attempts) using ORM.

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of (mapper_file, sql_id, validated, transform_count) tuples
        """
        with self._get_session() as session:
            stmt = (
                select(
                    TransformTargetList.mapper_file,
                    TransformTargetList.sql_id,
                    TransformTargetList.validated,
                    TransformTargetList.transform_count
                )
                .where(
                    TransformTargetList.validated == 'N',
                    TransformTargetList.transform_count > 1
                )
                .order_by(TransformTargetList.transform_count.desc())
                .limit(limit)
            )
            results = session.execute(stmt).all()
            return [(row[0], row[1], row[2], row[3]) for row in results]

    def get_test_failures(self, limit: int = 20) -> List[Tuple[str, str, str, str]]:
        """
        Get SQLs that failed testing using ORM.

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of (mapper_file, sql_id, tested, test_result) tuples
        """
        with self._get_session() as session:
            stmt = (
                select(
                    TransformTargetList.mapper_file,
                    TransformTargetList.sql_id,
                    TransformTargetList.tested,
                    TransformTargetList.test_result
                )
                .where(
                    TransformTargetList.tested == 'N',
                    TransformTargetList.test_result.like('%FAIL%')
                )
                .limit(limit)
            )
            results = session.execute(stmt).all()
            return [(row[0], row[1], row[2], row[3]) for row in results]

    def search_sqls(
        self,
        keyword: str = "",
        limit: int = 50
    ) -> List[Tuple[str, str, str]]:
        """
        Search SQL IDs by keyword in mapper_file or sql_id using ORM.

        Args:
            keyword: Search term (searches both mapper_file and sql_id)
            limit: Maximum number of results

        Returns:
            List of (mapper_file, sql_id, sql_type) tuples

        Example:
            results = state.search_sqls('User')
            # [('UserMapper.xml', 'selectUser', 'select'), ...]
        """
        with self._get_session() as session:
            stmt = select(
                TransformTargetList.mapper_file,
                TransformTargetList.sql_id,
                TransformTargetList.sql_type
            ).order_by(TransformTargetList.mapper_file, TransformTargetList.seq_no)

            if keyword:
                search_pattern = f'%{keyword}%'
                stmt = stmt.where(
                    or_(
                        TransformTargetList.mapper_file.like(search_pattern),
                        TransformTargetList.sql_id.like(search_pattern)
                    )
                )

            stmt = stmt.limit(limit)
            results = session.execute(stmt).all()
            return [(row[0], row[1], row[2]) for row in results]

    # ========== Helper Methods ==========

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists using SQLAlchemy inspector"""
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

"""SQLAlchemy ORM Models for OMA Database

This module defines database models using SQLAlchemy ORM to prevent SQL injection
and provide type-safe database access.
"""
from sqlalchemy import Column, Index, Integer, Text, DateTime, UniqueConstraint, create_engine
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy.sql import func

Base = declarative_base()


class TransformTargetList(Base):
    """Transform target SQL list - main tracking table (20 columns)

    Full schema is created at setup time via run_setup.py (Base.metadata.create_all).
    split_mapper.py also creates this table with CREATE TABLE IF NOT EXISTS as a fallback.
    """
    __tablename__ = 'transform_target_list'

    # Identity
    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    sql_type = Column(Text, nullable=False)
    seq_no = Column(Integer, nullable=False)
    namespace = Column(Text)
    source_file = Column(Text, nullable=False)
    target_file = Column(Text)

    # Pipeline status flags (server_default ensures SQL-level DEFAULT for raw INSERT)
    transformed = Column(Text, default='N', server_default='N')
    reviewed = Column(Text, default='N', server_default='N')
    validated = Column(Text, default='N', server_default='N')
    tested = Column(Text, default='N', server_default='N')
    completed = Column(Text, default='N', server_default='N')

    # Timestamps
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp())

    # Extended columns
    review_notes = Column(Text)        # Human review notes (ReviewManager)
    transform_count = Column(Integer)  # Retry count
    review_result = Column(Text)       # Multi-perspective review feedback JSON
    validation_result = Column(Text)   # Validation result details
    test_result = Column(Text)         # Test result: PASS, FAIL, SKIP, FIXED
    test_notes = Column(Text)          # Skip reason or error details
    current_step = Column(Text, default='pending', server_default='pending')

    def __repr__(self):
        return f"<TransformTargetList(mapper_file={self.mapper_file}, sql_id={self.sql_id}, status=T:{self.transformed}/R:{self.reviewed}/V:{self.validated}/T:{self.tested})>"


class Properties(Base):
    """Configuration properties table"""
    __tablename__ = 'properties'

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp())

    def __repr__(self):
        return f"<Property(key={self.key}, value={self.value})>"


class SourceXmlList(Base):
    """Source XML mapper file list"""
    __tablename__ = 'source_xml_list'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(Text, nullable=False)
    file_name = Column(Text, nullable=False)
    relative_path = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())

    def __repr__(self):
        return f"<SourceXmlList(file_name={self.file_name})>"


class TargetMetadata(Base):
    """Target DB column metadata cache (PostgreSQL or MySQL)"""
    __tablename__ = 'target_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_schema = Column(Text, nullable=False)
    table_name = Column(Text, nullable=False)
    column_name = Column(Text, nullable=False)
    data_type = Column(Text, nullable=False)

    __table_args__ = (
        Index('idx_target_meta_col', 'table_name', 'column_name'),
    )

    def __repr__(self):
        return f"<TargetMetadata(table={self.table_name}, column={self.column_name}, type={self.data_type})>"


# =============================================================================
# History tables (append-only — retain every attempt across pipeline stages)
#
# Conventions:
#   - mapper_path : project-root-relative XML path (e.g. "src/main/.../UserMapper.xml")
#   - mapper_file : legacy column kept for join compatibility with transform_target_list
#   - created_at  : UTC timestamp
#   - *_sql fields hold the exact SQL body at that stage (not the XML fragment)
# =============================================================================

class ExtractRecord(Base):
    """SQL extraction master record (Source Analyzer output).

    Unlike the append-only *_history tables, this is a master record — one row
    per (mapper_file, sql_id). Re-extracting the same SQL updates the existing
    row via INSERT OR REPLACE (UPSERT), so the table reflects current state.
    """
    __tablename__ = 'extract_record'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_path = Column(Text)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    sql_type = Column(Text)
    namespace = Column(Text)
    seq_no = Column(Integer)
    original_sql = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('mapper_file', 'sql_id', name='uq_extract_record_sql'),
        Index('idx_extract_record_sql', 'mapper_file', 'sql_id'),
    )


class TransformHistory(Base):
    """Transform attempt history (one row per retry)"""
    __tablename__ = 'transform_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_path = Column(Text)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    attempt_no = Column(Integer)
    original_sql = Column(Text)
    transformed_sql = Column(Text)
    transform_log = Column(Text)        # agent reasoning/decision text
    model_id = Column(Text)
    status = Column(Text)               # success | failure
    error_message = Column(Text)
    duration_ms = Column(Integer)
    # Legacy column retained for backward compatibility
    transform_count = Column(Integer)
    created_at = Column(DateTime, default=func.current_timestamp())

    __table_args__ = (
        Index('idx_transform_hist_sql', 'mapper_file', 'sql_id'),
    )


class DiffRecord(Base):
    """Diff record for review"""
    __tablename__ = 'diff_record'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    diff_content = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())


class ReviewHistory(Base):
    """Review round history (multi-perspective + facilitator)"""
    __tablename__ = 'review_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_path = Column(Text)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    round_no = Column(Integer)
    reviewed_sql = Column(Text)
    syntax_result = Column(Text)            # Syntax agent verdict
    equivalence_result = Column(Text)       # Equivalence agent verdict
    facilitator_verdict = Column(Text)      # PASS | FAIL | FIXED
    review_log = Column(Text)               # consolidated discussion/rationale
    duration_ms = Column(Integer)
    # Legacy column retained for backward compatibility
    review_result = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())

    __table_args__ = (
        Index('idx_review_hist_sql', 'mapper_file', 'sql_id'),
    )


class ValidationHistory(Base):
    """Validation history (functional equivalence checks, static)"""
    __tablename__ = 'validation_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_path = Column(Text)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    round_no = Column(Integer)
    validated_sql = Column(Text)
    verdict = Column(Text)                  # PASS | FAIL
    validation_log = Column(Text)
    issues_found = Column(Text)             # JSON array of structured findings
    duration_ms = Column(Integer)
    # Legacy column retained for backward compatibility
    validation_result = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())

    __table_args__ = (
        Index('idx_validation_hist_sql', 'mapper_file', 'sql_id'),
    )


class TestHistory(Base):
    """Test execution history (Phase 0 EXPLAIN / Phase 1 Java / Phase 2 fix)"""
    __tablename__ = 'test_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_path = Column(Text)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    phase = Column(Text)                    # phase0_explain | phase1_java | phase2_fix
    attempt_no = Column(Integer)
    tested_sql = Column(Text)
    bind_parameters = Column(Text)          # JSON {"userId": 123, "status": "ACTIVE"}
    test_result = Column(Text)              # PASS | FAIL | SKIP | FIXED
    execution_log = Column(Text)
    sql_state = Column(Text)                # JDBC SQLState (e.g. 42P01)
    error_message = Column(Text)
    stack_trace = Column(Text)
    execution_time_ms = Column(Integer)
    rows_affected = Column(Integer)
    created_at = Column(DateTime, default=func.current_timestamp())

    __table_args__ = (
        Index('idx_test_hist_sql', 'mapper_file', 'sql_id'),
    )


def create_session(db_path: str) -> Session:
    """Create a SQLAlchemy session for the given database path

    Args:
        db_path: Path to SQLite database file

    Returns:
        SQLAlchemy Session object
    """
    engine = create_engine(f'sqlite:///{db_path}', echo=False, connect_args={"timeout": 10})
    return Session(engine)

"""SQLAlchemy ORM Models for OMA Database

This module defines database models using SQLAlchemy ORM to prevent SQL injection
and provide type-safe database access.
"""
from sqlalchemy import Column, Index, Integer, Text, DateTime, create_engine
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

    # Pipeline status flags
    transformed = Column(Text, default='N')
    reviewed = Column(Text, default='N')
    validated = Column(Text, default='N')
    tested = Column(Text, default='N')
    completed = Column(Text, default='N')

    # Timestamps
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp())

    # Extended columns
    review_notes = Column(Text)        # Human review notes (ReviewManager)
    transform_count = Column(Integer)  # Retry count
    review_result = Column(Text)       # Multi-perspective review feedback JSON
    validation_result = Column(Text)   # Validation result details
    test_result = Column(Text)         # Test result details

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


class PgMetadata(Base):
    """PostgreSQL column metadata cache"""
    __tablename__ = 'pg_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_schema = Column(Text, nullable=False)
    table_name = Column(Text, nullable=False)
    column_name = Column(Text, nullable=False)
    data_type = Column(Text, nullable=False)

    __table_args__ = (
        Index('idx_pg_meta_col', 'table_name', 'column_name'),
    )

    def __repr__(self):
        return f"<PgMetadata(table={self.table_name}, column={self.column_name}, type={self.data_type})>"


# History tables (optional - can be added later if needed)
class TransformHistory(Base):
    """Transform operation history"""
    __tablename__ = 'transform_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    original_sql = Column(Text)
    transformed_sql = Column(Text)
    transform_count = Column(Integer)
    created_at = Column(DateTime, default=func.current_timestamp())


class DiffRecord(Base):
    """Diff record for review"""
    __tablename__ = 'diff_record'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    diff_content = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())


class ReviewHistory(Base):
    """Review operation history"""
    __tablename__ = 'review_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    review_result = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())


class ValidationHistory(Base):
    """Validation operation history"""
    __tablename__ = 'validation_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    validation_result = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())


class TestHistory(Base):
    """Test operation history"""
    __tablename__ = 'test_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mapper_file = Column(Text, nullable=False)
    sql_id = Column(Text, nullable=False)
    test_result = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())


def create_session(db_path: str) -> Session:
    """Create a SQLAlchemy session for the given database path

    Args:
        db_path: Path to SQLite database file

    Returns:
        SQLAlchemy Session object
    """
    engine = create_engine(f'sqlite:///{db_path}', echo=False, connect_args={"timeout": 10})
    return Session(engine)

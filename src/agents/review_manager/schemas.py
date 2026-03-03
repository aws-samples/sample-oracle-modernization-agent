"""TypedDict schemas for ReviewManager tool return values"""
from typing import TypedDict, List, Optional


class SqlCandidate(TypedDict):
    """Single SQL candidate for review"""
    mapper_file: str
    sql_id: str
    sql_type: str


class ReviewCandidatesResult(TypedDict):
    """Result from get_review_candidates()"""
    status: str  # 'success' | 'error'
    total: int
    candidates: List[SqlCandidate]
    filter_type: str


class SqlDiffResult(TypedDict):
    """Result from show_sql_diff()"""
    status: str  # 'success' | 'error'
    mapper_file: Optional[str]
    sql_id: Optional[str]
    diff: Optional[str]
    message: Optional[str]


class DiffReportResult(TypedDict):
    """Result from generate_diff_report()"""
    status: str  # 'success' | 'error'
    report_path: Optional[str]
    total_sqls: Optional[int]
    message: Optional[str]


class ApprovalResult(TypedDict):
    """Result from approve_conversion()"""
    status: str  # 'success' | 'error'
    message: str


class RevisionResult(TypedDict):
    """Result from suggest_revision()"""
    status: str  # 'success' | 'error'
    message: str
    reason: Optional[str]

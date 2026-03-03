"""TypedDict schemas for Orchestrator tool return values"""
from typing import TypedDict, List, Optional, Dict


class SetupCheckResult(TypedDict):
    """Result from check_setup()"""
    ready: bool
    missing: Optional[List[str]]
    values: Optional[Dict[str, str]]


class StepStatusResult(TypedDict):
    """Result from check_step_status()"""
    source_analyzed: int
    extracted: int
    transformed: int
    reviewed: int
    validated: int
    tested: int
    merged: int
    transform_complete: bool
    review_complete: bool
    validate_complete: bool
    test_complete: bool
    merge_complete: bool


class RunStepResult(TypedDict):
    """Result from run_step()"""
    status: str  # 'success' | 'error'
    details: str
    needs_merge: bool


class ResetStepResult(TypedDict):
    """Result from reset_step()"""
    status: str
    step: str
    reset_count: int


class SummaryResult(TypedDict):
    """Result from get_summary()"""
    total_sqls: int
    transformed: int
    reviewed: int
    validated: int
    tested: int
    merged: int
    output_files: Dict[str, str]
    completion_status: Dict[str, bool]


class SqlIdMatch(TypedDict):
    """Single SQL ID match"""
    sql_id: str
    sql_type: str


class SearchSqlResult(TypedDict):
    """Result from search_sql_ids()"""
    total: int
    mappers_count: int
    results: Dict[str, List[SqlIdMatch]]  # {mapper_file: [{sql_id, sql_type}]}


class StrategyGenerateResult(TypedDict):
    """Result from generate_project_strategy()"""
    status: str  # 'success' | 'failed'
    file_path: Optional[str]
    file_size_kb: Optional[float]
    pattern_count: Optional[int]
    needs_compression: Optional[bool]
    error: Optional[str]


class StrategyRefineResult(TypedDict):
    """Result from refine_project_strategy()"""
    status: str
    message: str
    feedback_count: int


class StrategyCompactResult(TypedDict):
    """Result from compact_strategy()"""
    status: str
    message: str
    before_size_kb: float
    after_size_kb: float
    reduction_percent: float

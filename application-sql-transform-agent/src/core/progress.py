"""Thread-safe progress queue for inter-thread communication.

Replaces signal file-based IPC which was vulnerable to race conditions
when multiple threads append/read/delete the same file concurrently.
"""
import queue

_progress_queue: queue.Queue = queue.Queue()


def emit_progress(mapper_file: str, sql_id: str, status: str, notes: str = "") -> None:
    """Emit a progress event from a tool (called within agent threads).

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        status: Completion status (e.g., 'DONE', 'PASS', 'FIXED', 'FAIL')
        notes: Additional notes
    """
    _progress_queue.put({
        "mapper_file": mapper_file,
        "sql_id": sql_id,
        "status": status,
        "notes": notes,
    })


def drain_progress() -> list[dict]:
    """Drain all pending progress events from the queue (non-blocking).

    Returns:
        List of progress event dicts
    """
    events = []
    while True:
        try:
            events.append(_progress_queue.get_nowait())
        except queue.Empty:
            break
    return events


def get_progress_queue() -> queue.Queue:
    """Get the raw queue for direct consumption (e.g., in monitor threads)."""
    return _progress_queue

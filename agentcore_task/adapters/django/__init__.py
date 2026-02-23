# Django adapter: full Django app for task execution tracking.
# Public API: import from here; exports re-exported from .services
# (lazy to avoid AppRegistryNotReady).

__all__ = [
    "TaskTracker",
    "register_task_execution",
    "get_task_stats",
    "list_task_executions",
    "acquire_task_lock",
    "release_task_lock",
    "is_task_locked",
    "prevent_duplicate_task",
    "TaskStatus",
    "TaskLogCollector",
    "cleanup_old_executions",
    "cleanup_old_task_executions",
    "mark_timed_out_executions",
    "mark_timed_out_task_executions",
    "get_cleanup_beat_schedule",
]


def __getattr__(name):
    from . import services
    if hasattr(services, name):
        return getattr(services, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
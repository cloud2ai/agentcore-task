"""
Task execution: stats (aggregate) and query detail (list) API.

- Stats: get_task_stats() — aggregate counts by status, module, task_name;
  used by dashboard and stats endpoint.
- Query detail: list_task_executions() — list executions with filters for
  list/my_tasks endpoints; single-task detail remains
  TaskTracker.get_task(task_id, sync=...).
"""
from typing import Any, Dict, Optional

from agentcore_task.adapters.django.models import TaskExecution
from agentcore_task.constants import TaskStatus


def _counts_for_queryset(qs) -> Dict[str, int]:
    """
    Return dict of status counts for a TaskExecution queryset.

    Keys: total, pending, started, success, failure, retry, revoked.
    Used by get_task_stats and internal stats by_module / by_task_name.
    """
    # Aggregate counts per status
    return {
        "total": qs.count(),
        "pending": qs.filter(status=TaskStatus.PENDING).count(),
        "started": qs.filter(status=TaskStatus.STARTED).count(),
        "success": qs.filter(status=TaskStatus.SUCCESS).count(),
        "failure": qs.filter(status=TaskStatus.FAILURE).count(),
        "retry": qs.filter(status=TaskStatus.RETRY).count(),
        "revoked": qs.filter(status=TaskStatus.REVOKED).count(),
    }


def _stats_by_module_and_task_name(queryset):
    """
    Build by_module and by_task_name dicts from queryset.

    Each key (module or task_name) maps to a count dict from
    _counts_for_queryset for the filtered subset.
    """
    by_module = {}
    # Group counts by module
    for mod in queryset.values_list("module", flat=True).distinct():
        q = queryset.filter(module=mod)
        by_module[mod] = _counts_for_queryset(q)
    by_task_name = {}
    # Group counts by task_name
    for name in queryset.values_list("task_name", flat=True).distinct():
        q = queryset.filter(task_name=name)
        by_task_name[name] = _counts_for_queryset(q)
    return by_module, by_task_name


def get_task_stats(
    module: Optional[str] = None,
    task_name: Optional[str] = None,
    created_by=None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregate counts by status and by module/task_name.

    Optional filters: module, task_name, created_by, start_date, end_date
    (YYYY-MM-DD; filter by created_at date). Returns total and per-status
    counts plus by_module and by_task_name breakdowns.
    """
    queryset = TaskExecution.objects.all()
    # Apply optional filters
    if module:
        queryset = queryset.filter(module=module)
    if task_name:
        queryset = queryset.filter(task_name=task_name)
    if created_by is not None:
        queryset = queryset.filter(created_by=created_by)
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)

    summary = _counts_for_queryset(queryset)
    by_module, by_task_name = _stats_by_module_and_task_name(queryset)
    return {
        **summary,
        "by_module": by_module,
        "by_task_name": by_task_name,
    }


def list_task_executions(
    *,
    module: Optional[str] = None,
    task_name: Optional[str] = None,
    status: Optional[str] = None,
    created_by=None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    order_by: str = "-created_at",
):
    """
    Query task execution list (query detail API).

    Optional filters: module, task_name, status, created_by, start_date,
    end_date. Returns a QuerySet with select_related("created_by") for
    list/detail views; caller may paginate or slice.
    """
    queryset = TaskExecution.objects.select_related("created_by").all()
    # Apply optional filters
    if module:
        queryset = queryset.filter(module=module)
    if task_name:
        queryset = queryset.filter(task_name=task_name)
    if status:
        queryset = queryset.filter(status=status)
    if created_by is not None:
        queryset = queryset.filter(created_by=created_by)
    if start_date:
        queryset = queryset.filter(created_at__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__lte=end_date)
    return queryset.order_by(order_by)

"""
Task recording and reporting: register tasks, update status, sync from Celery.

This module is the core of the task abstraction. It is designed for the
business layer: call register_task_execution when dispatching a task, and
update_task_status from inside the task (or let sync_task_from_celery pull
from Celery when status was not pushed).

Public API: import from agentcore_task.adapters.django.
Scheduled tasks (cleanup, mark_timeout) live in adapters.django.tasks.
"""
import logging
import traceback as tb
from typing import Any, Dict, Optional

from celery.result import AsyncResult
from django.utils import timezone

from agentcore_task.constants import TaskStatus
from agentcore_task.adapters.django.models import TaskExecution
from agentcore_task.adapters.django.services.task_stats import get_task_stats

logger = logging.getLogger(__name__)

# Task name constants used by scheduled tasks (cleanup, mark_timeout)
# and when they register themselves in TaskExecution.
TASK_SYNC_CELERY = "sync_task_from_celery"
TASK_CLEANUP = "cleanup_old_task_executions"
TASK_MARK_TIMEOUT = "mark_timed_out_task_executions"
MODULE_AGENTCORE_TASK = "agentcore_task"


def _extract_failure_result(async_result):
    """
    Return (result, error, traceback_str) from a failed AsyncResult.

    Used when syncing from Celery: we need to persist the exception message
    and traceback into TaskExecution for display and debugging.
    """
    result, error, traceback_str = None, None, None
    # Extract exception and traceback from failed result
    try:
        res = async_result.result
        if isinstance(res, Exception):
            error = str(res)
            if hasattr(res, "__traceback__") and res.__traceback__:
                traceback_str = "".join(tb.format_tb(res.__traceback__))
    except Exception as e:
        error = str(e)
    return result, error, traceback_str


def register_task_execution(
    task_id: str,
    task_name: str,
    module: str,
    task_args: Optional[list] = None,
    task_kwargs: Optional[dict] = None,
    created_by=None,
    metadata: Optional[dict] = None,
    initial_status: Optional[str] = None,
) -> TaskExecution:
    """
    Register a task execution when dispatching a Celery task.

    Call this right after task.delay(...); pass task.id as task_id.
    Creates one TaskExecution row keyed by task_id (get_or_create), so
    duplicate registration for the same task_id is safe.

    For periodic tasks that have no dispatcher, pass
    initial_status=TaskStatus.STARTED so the run is recorded as already
    started in one call (no separate update_task_status(STARTED) needed).
    """
    return TaskTracker.register_task(
        task_id=task_id,
        task_name=task_name,
        module=module,
        task_args=task_args,
        task_kwargs=task_kwargs,
        created_by=created_by,
        metadata=metadata,
        initial_status=initial_status,
    )


class TaskTracker:
    """
    Service for tracking and managing task executions.

    The abstraction is business-layer oriented: the task code should call
    update_task_status when it starts, finishes, or reports progress.
    sync_task_from_celery is a fallback when status was not pushed (e.g.
    legacy tasks or one-off sync from API).
    """

    @staticmethod
    def register_task(
        task_id: str,
        task_name: str,
        module: str,
        task_args: Optional[list] = None,
        task_kwargs: Optional[dict] = None,
        created_by=None,
        metadata: Optional[dict] = None,
        initial_status: Optional[str] = None,
    ) -> TaskExecution:
        """
        Create or get a TaskExecution row for this task_id.

        Uses get_or_create so that the same Celery task_id always maps to
        one record; repeated registration (e.g. retries) does not duplicate.
        If initial_status is STARTED, started_at is set so the task is
        recorded as already running without a separate update_task_status call.
        """
        # NOTE(Ray): initial_status lets periodic tasks register as STARTED in
        # one call since they have no dispatcher to register at dispatch time.
        status = initial_status if initial_status else TaskStatus.PENDING
        defaults = {
            "task_name": task_name,
            "module": module,
            "status": status,
            "task_args": task_args or [],
            "task_kwargs": task_kwargs or {},
            "created_by": created_by,
            "metadata": metadata or {},
        }
        # Set started_at when registering as already started
        if status == TaskStatus.STARTED:
            defaults["started_at"] = timezone.now()
        task_execution, created = TaskExecution.objects.get_or_create(
            task_id=task_id,
            defaults=defaults,
        )
        if created:
            logger.info(
                f"Registered new task task_id={task_id} "
                f"task_name={task_name} module={module}"
            )
        else:
            logger.debug(
                f"Task already registered task_id={task_id} "
                f"task_name={task_name}"
            )
        return task_execution

    @staticmethod
    def update_task_status(
        task_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        traceback: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[TaskExecution]:
        """
        Update status and optional result/error/traceback/metadata for a task.

        Preferred path: call this from inside the task (on start, progress,
        success, or failure). started_at is set on first STARTED;
        finished_at is set when status is SUCCESS/FAILURE/REVOKED.
        metadata is merged into existing; it is not replaced.
        """
        try:
            task_execution = TaskExecution.objects.get(task_id=task_id)
            old_status = task_execution.status
            task_execution.status = status
            # Set timestamps on first transition to STARTED or completed
            if status == TaskStatus.STARTED and not task_execution.started_at:
                task_execution.started_at = timezone.now()
            elif status in TaskStatus.get_completed_statuses():
                if not task_execution.finished_at:
                    task_execution.finished_at = timezone.now()
            # Apply optional result, error, traceback, metadata
            if result is not None:
                task_execution.result = result
            if error is not None:
                task_execution.error = error
            if traceback is not None:
                task_execution.traceback = traceback
            if metadata is not None:
                if task_execution.metadata is None:
                    task_execution.metadata = {}
                task_execution.metadata.update(metadata)
            # Persist and log when status changed
            task_execution.save()
            if old_status != status:
                logger.info(
                    f"Updated task status task_id={task_id} "
                    f"task_name={task_execution.task_name} "
                    f"{old_status} -> {status}"
                )
            return task_execution
        except TaskExecution.DoesNotExist:
            logger.warning(f"Task execution not found task_id={task_id}")
            return None

    @staticmethod
    def sync_task_from_celery(task_id: str) -> Optional[TaskExecution]:
        """
        Copy current status (and result/error/traceback) from Celery into DB.

        Used when the business layer did not push status (e.g. get_task with
        sync=True or the REST "sync" action). Reads AsyncResult(task_id),
        maps Celery status to our status, and calls update_task_status so the
        TaskExecution row is up to date. If status did not change, no write.
        """
        logger.info(f"Starting {TASK_SYNC_CELERY} task_id={task_id}")
        try:
            task_execution = TaskExecution.objects.get(task_id=task_id)
            async_result = AsyncResult(task_id)
            status_mapping = {
                "PENDING": TaskStatus.PENDING,
                "STARTED": TaskStatus.STARTED,
                "SUCCESS": TaskStatus.SUCCESS,
                "FAILURE": TaskStatus.FAILURE,
                "RETRY": TaskStatus.RETRY,
                "REVOKED": TaskStatus.REVOKED,
            }
            celery_status = async_result.status
            new_status = status_mapping.get(celery_status, TaskStatus.PENDING)
            # Update DB when Celery state differs from our record
            if task_execution.status != new_status:
                result, error, traceback_str = None, None, None
                if async_result.ready():
                    if celery_status == "SUCCESS":
                        result = async_result.result
                    elif celery_status == "FAILURE":
                        result, error, traceback_str = (
                            _extract_failure_result(async_result)
                        )
                out = TaskTracker.update_task_status(
                    task_id=task_id,
                    status=new_status,
                    result=result,
                    error=error,
                    traceback=traceback_str,
                )
                logger.info(
                    f"Finished {TASK_SYNC_CELERY} task_id={task_id}"
                )
                return out

            logger.info(
                f"Finished {TASK_SYNC_CELERY} task_id={task_id} (no change)"
            )
            return task_execution
        except TaskExecution.DoesNotExist:
            logger.warning(f"Task execution not found task_id={task_id}")
            return None
        except Exception as e:
            logger.error(
                f"Failed {TASK_SYNC_CELERY} task_id={task_id}: {e}"
            )
            return None

    @staticmethod
    def sync_all_unfinished_executions(
        max_sync: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Sync all non-finished TaskExecution rows from Celery, return counts.

        Queries PENDING, STARTED, RETRY; for each calls sync_task_from_celery.
        Use before mark_timed_out_executions so DB is up to date and we only
        timeout tasks still STARTED after sync. Optional max_sync caps how
        many to sync in one run (oldest first by created_at).
        """
        qs = TaskExecution.objects.filter(
            status__in=TaskStatus.get_running_statuses() + [TaskStatus.PENDING]
        ).order_by("created_at")
        if max_sync is not None and max_sync > 0:
            qs = qs[:max_sync]
        task_ids = list(qs.values_list("task_id", flat=True))
        synced_count = len(task_ids)
        updated_count = 0
        # Sync each unfinished task from Celery
        for tid in task_ids:
            out = TaskTracker.sync_task_from_celery(tid)
            if out is not None:
                updated_count += 1
        return {"synced_count": synced_count, "updated_count": updated_count}

    @staticmethod
    def get_task(task_id: str, sync: bool = True) -> Optional[TaskExecution]:
        """
        Load TaskExecution by task_id. If sync=True (default), refresh from
        Celery first so the returned row reflects current Celery state.
        """
        try:
            task_execution = TaskExecution.objects.get(task_id=task_id)
            if sync:
                TaskTracker.sync_task_from_celery(task_id)
                task_execution.refresh_from_db()
            return task_execution
        except TaskExecution.DoesNotExist:
            return None


TaskTracker.get_task_stats = get_task_stats

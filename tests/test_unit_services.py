"""
Unit tests for agentcore_task.adapters.django.services
(lock, log_collector, task_tracker).
"""
import pytest

from agentcore_task.adapters.django.services import (
    TaskLogCollector,
    TaskTracker,
    acquire_task_lock,
    is_task_locked,
    prevent_duplicate_task,
    register_task_execution,
    release_task_lock,
)
from agentcore_task.constants import TaskStatus


pytestmark = [pytest.mark.unit]


class TestLock:
    def test_acquire_release_and_check(self):
        name = "test_lock_acquire_release"
        assert not is_task_locked(name)
        assert acquire_task_lock(name, timeout=60) is True
        assert is_task_locked(name) is True
        assert acquire_task_lock(name, timeout=60) is False
        assert release_task_lock(name) is True
        assert not is_task_locked(name)

    def test_prevent_duplicate_task_decorator_runs_once(self):
        name = "test_prevent_dup_run"
        run_count = 0

        @prevent_duplicate_task(name, timeout=60)
        def counted():
            nonlocal run_count
            run_count += 1
            return {"success": True}

        out1 = counted()
        out2 = counted()
        assert run_count == 1
        assert out1 == {"success": True}
        assert out2.get("status") == "skipped"
        assert "task_already_running" in str(out2.get("reason", ""))

    def test_prevent_duplicate_task_with_lock_param(self):
        base = "test_prevent_dup_param"

        @prevent_duplicate_task(base, timeout=60, lock_param="x")
        def with_param(x):
            return {"value": x}

        assert with_param(1) == {"value": 1}
        out = with_param(1)
        assert out.get("status") == "skipped"
        assert with_param(2) == {"value": 2}


class TestTaskLogCollector:
    def test_info_warning_error_and_get_logs(self):
        c = TaskLogCollector(max_records=10)
        c.info("a")
        c.warning("b")
        c.error("c", exception="e1")
        logs = c.get_logs()
        assert len(logs) == 3
        assert logs[0]["level"] == "INFO" and logs[0]["message"] == "a"
        assert logs[1]["level"] == "WARNING"
        assert logs[2]["level"] == "ERROR" and logs[2].get("exception") == "e1"

    def test_get_warnings_and_errors(self):
        c = TaskLogCollector()
        c.info("i")
        c.warning("w")
        c.error("e")
        we = c.get_warnings_and_errors()
        assert len(we) == 2
        assert we[0]["level"] == "WARNING"
        assert we[1]["level"] == "ERROR"

    def test_get_summary(self):
        c = TaskLogCollector()
        c.info("a")
        c.info("b")
        c.warning("w")
        s = c.get_summary()
        assert s["total"] == 3
        assert s["by_level"]["INFO"] == 2
        assert s["by_level"]["WARNING"] == 1

    def test_clear(self):
        c = TaskLogCollector()
        c.info("x")
        c.clear()
        assert c.get_logs() == []

    def test_max_records_caps(self):
        c = TaskLogCollector(max_records=2)
        c.info("1")
        c.info("2")
        c.info("3")
        assert len(c.get_logs()) == 2
        assert c.get_logs()[0]["message"] == "2"
        assert c.get_logs()[1]["message"] == "3"


class TestTaskTrackerAndRegister:
    def test_register_task_execution(self, user, db):
        task_id = "celery-id-001"
        te = register_task_execution(
            task_id=task_id,
            task_name="myapp.tasks.job",
            module="myapp",
            task_kwargs={"a": 1},
            created_by=user,
            metadata={"source": "test"},
        )
        assert te.task_id == task_id
        assert te.task_name == "myapp.tasks.job"
        assert te.module == "myapp"
        assert te.status == TaskStatus.PENDING
        assert te.created_by_id == user.id
        assert te.metadata == {"source": "test"}
        te2 = register_task_execution(
            task_id=task_id,
            task_name="other",
            module="other",
        )
        assert te2.pk == te.pk
        assert te2.task_name == "myapp.tasks.job"

    def test_update_task_status(self, user, db):
        te = register_task_execution(
            task_id="tid-update",
            task_name="t",
            module="m",
            created_by=user,
        )
        updated = TaskTracker.update_task_status(
            te.task_id,
            status=TaskStatus.STARTED,
            metadata={"step": "running"},
        )
        assert updated is not None
        updated.refresh_from_db()
        assert updated.status == TaskStatus.STARTED
        assert updated.started_at is not None
        assert updated.metadata.get("step") == "running"

        TaskTracker.update_task_status(
            te.task_id,
            status=TaskStatus.SUCCESS,
            result={"done": True},
        )
        te.refresh_from_db()
        assert te.status == TaskStatus.SUCCESS
        assert te.finished_at is not None
        assert te.result == {"done": True}

    def test_get_task_not_found(self, db):
        assert TaskTracker.get_task("nonexistent-id", sync=False) is None

    def test_get_task_found(self, user, db):
        register_task_execution(
            task_id="tid-get",
            task_name="t",
            module="m",
            created_by=user,
        )
        found = TaskTracker.get_task("tid-get", sync=False)
        assert found is not None
        assert found.task_id == "tid-get"

    def test_get_task_stats(self, user, db):
        register_task_execution(
            task_id="s1",
            task_name="task_a",
            module="mod1",
            created_by=user,
        )
        register_task_execution(
            task_id="s2",
            task_name="task_a",
            module="mod1",
            created_by=user,
        )
        register_task_execution(
            task_id="s3",
            task_name="task_b",
            module="mod2",
            created_by=user,
        )
        stats = TaskTracker.get_task_stats()
        assert stats["total"] == 3
        assert stats["pending"] == 3
        assert "mod1" in stats["by_module"]
        assert stats["by_module"]["mod1"]["total"] == 2
        assert "task_a" in stats["by_task_name"]
        assert stats["by_task_name"]["task_a"]["total"] == 2

        stats_m1 = TaskTracker.get_task_stats(module="mod1")
        assert stats_m1["total"] == 2

        stats_user = TaskTracker.get_task_stats(created_by=user)
        assert stats_user["total"] == 3

"""Django app config for agentcore_task (task execution)."""
from django.apps import AppConfig


class AgentcoreTaskDjangoConfig(AppConfig):
    """App config for agentcore_task Django adapter."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agentcore_task.adapters.django"
    label = "agentcore_task_tracker"
    verbose_name = "Agentcore Task"

    def ready(self):
        # NOTE(Ray): Imports inside ready() are intentional. Django convention
        # is to do lazy imports here to avoid AppRegistryNotReady or circular
        # dependency when apps are loading. Do not treat as violation of
        # "all imports at top of file".
        from django.conf import settings as s

        from agentcore_task.adapters.django.conf import (
            get_cleanup_beat_schedule,
            get_cleanup_enabled,
            get_mark_timeout_beat_schedule,
            get_mark_timeout_enabled,
        )

        cur = getattr(s, "CELERY_BEAT_SCHEDULE", None) or {}
        if get_cleanup_enabled():
            cur = {**cur, **get_cleanup_beat_schedule()}
        if get_mark_timeout_enabled():
            cur = {**cur, **get_mark_timeout_beat_schedule()}
        s.CELERY_BEAT_SCHEDULE = cur

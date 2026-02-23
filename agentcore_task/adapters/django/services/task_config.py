"""
Read task config from TaskConfig model (global scope only for now).
Used by conf.get_retention_days() with fallback to settings.
"""
import logging
from typing import Any, Optional

from agentcore_task.adapters.django.models import TaskConfig

logger = logging.getLogger(__name__)


def get_global_task_config(key: str) -> Optional[Any]:
    """
    Return value for global config key from TaskConfig, or None if not set.
    """
    try:
        row = TaskConfig.objects.filter(
            scope=TaskConfig.SCOPE_GLOBAL,
            user__isnull=True,
            key=key,
        ).first()
        if row is not None and row.value is not None:
            return row.value
    except Exception as e:
        logger.debug(f"get_global_task_config({key}) failed: {e}")
    return None


def get_retention_days_from_config() -> Optional[int]:
    """
    Return global retention_days from TaskConfig if set and valid.
    Value may be int or dict with 'retention_days' key.
    """
    raw = get_global_task_config("retention_days")
    if raw is None:
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, dict):
        v = raw.get("retention_days")
        if isinstance(v, int) and v > 0:
            return v
    return None


def get_timeout_minutes_from_config() -> Optional[int]:
    """
    Return global task timeout (minutes) from TaskConfig if set and valid.
    Value may be int or dict with 'timeout_minutes' key.
    """
    raw = get_global_task_config("timeout_minutes")
    if raw is None:
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, dict):
        v = raw.get("timeout_minutes")
        if isinstance(v, int) and v > 0:
            return v
    return None

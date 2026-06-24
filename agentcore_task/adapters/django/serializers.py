"""Serializers for task execution API."""
from rest_framework import serializers

from agentcore_task.adapters.django.models import TaskExecution


def _filter_metadata(metadata, fields):
    """Return metadata filtered by field names when fields are provided."""

    metadata = metadata or {}
    if not fields:
        return metadata
    if isinstance(fields, str):
        fields = [
            field.strip()
            for field in fields.split(",")
            if field.strip()
        ]
    return {
        field: metadata[field]
        for field in fields
        if field in metadata
    }


def _include_metadata(context):
    """Return whether metadata should be included in serialized output."""

    include = context.get("include_metadata")
    request = context.get("request")
    if include is None and request is not None:
        include = request.query_params.get("include_metadata")
    if isinstance(include, str):
        return include.lower() not in {"0", "false", "no", "off"}
    if include is None:
        return True
    return bool(include)


def _get_metadata_fields(context):
    """Return metadata_fields from serializer context or request query."""

    fields = context.get("metadata_fields")
    request = context.get("request")
    if fields is None and request is not None:
        fields = request.query_params.get("metadata_fields")
    return fields


class TaskExecutionSerializer(serializers.ModelSerializer):
    """Full task execution detail for retrieve/sync/status endpoints."""

    duration = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    is_running = serializers.ReadOnlyField()
    metadata = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )
    created_by_id = serializers.IntegerField(
        source="created_by.id", read_only=True
    )

    def get_metadata(self, obj):
        """Return metadata filtered by metadata_fields when requested."""

        if not _include_metadata(self.context):
            return None
        return _filter_metadata(
            obj.metadata,
            _get_metadata_fields(self.context),
        )

    class Meta:
        model = TaskExecution
        fields = [
            "id",
            "task_id",
            "task_name",
            "module",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "task_args",
            "task_kwargs",
            "result",
            "error",
            "traceback",
            "created_by",
            "created_by_id",
            "created_by_username",
            "metadata",
            "duration",
            "is_completed",
            "is_running",
        ]
        read_only_fields = [
            "id",
            "task_id",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "result",
            "error",
            "traceback",
        ]


class TaskExecutionListSerializer(serializers.ModelSerializer):
    """Task execution list item for list/my_tasks endpoints."""

    duration = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    is_running = serializers.ReadOnlyField()
    metadata = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )
    created_by_id = serializers.IntegerField(
        source="created_by.id", read_only=True
    )

    def get_metadata(self, obj):
        """Return metadata filtered by metadata_fields when requested."""

        if not _include_metadata(self.context):
            return None
        return _filter_metadata(
            obj.metadata,
            _get_metadata_fields(self.context),
        )

    class Meta:
        model = TaskExecution
        fields = [
            "id",
            "task_id",
            "task_name",
            "module",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "metadata",
            "created_by_id",
            "created_by_username",
            "duration",
            "is_completed",
            "is_running",
        ]


class TaskStatsSerializer(serializers.Serializer):
    """
    Stats response: total, per-status counts, by_module, by_task_name;
    optional series.
    """

    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    started = serializers.IntegerField()
    success = serializers.IntegerField()
    failure = serializers.IntegerField()
    retry = serializers.IntegerField()
    revoked = serializers.IntegerField()
    by_module = serializers.DictField(child=serializers.DictField())
    by_task_name = serializers.DictField(child=serializers.DictField())
    series = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_null=True,
    )


class TaskConfigSerializer(serializers.Serializer):
    """Effective task config (GET response)."""

    timeout_minutes = serializers.IntegerField(min_value=1)
    retention_days = serializers.IntegerField(min_value=1)
    cleanup_crontab = serializers.CharField()
    mark_timeout_crontab = serializers.CharField()


class TaskConfigUpdateSerializer(serializers.Serializer):
    """Request body for PATCH config (optional fields)."""

    timeout_minutes = serializers.IntegerField(
        min_value=1, max_value=1440, required=False
    )
    retention_days = serializers.IntegerField(
        min_value=1, max_value=3650, required=False
    )
    cleanup_crontab = serializers.CharField(required=False, allow_blank=False)
    mark_timeout_crontab = serializers.CharField(
        required=False, allow_blank=False
    )

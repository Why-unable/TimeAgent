from rest_framework import serializers

from apps.events.serializers import CalendarEventSerializer
from apps.reminders.serializers import ReminderSerializer
from apps.tasks.serializers import TaskSerializer
from apps.today.schemas import ScheduleItemKind


class ScheduleItemSerializer(serializers.Serializer[object]):
    kind = serializers.ChoiceField(choices=[item.value for item in ScheduleItemKind])
    id = serializers.UUIDField()
    title = serializers.CharField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()


class ScheduleConflictSerializer(serializers.Serializer[object]):
    first = ScheduleItemSerializer()
    second = ScheduleItemSerializer()
    overlap_start_at = serializers.DateTimeField()
    overlap_end_at = serializers.DateTimeField()


class TodayExecutionItemSerializer(serializers.Serializer[object]):
    kind = serializers.ChoiceField(choices=[item.value for item in ScheduleItemKind])
    id = serializers.UUIDField()
    title = serializers.CharField()
    start_at = serializers.DateTimeField(allow_null=True)
    end_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    due_at = serializers.DateTimeField(allow_null=True)


class TodaySummarySerializer(serializers.Serializer[object]):
    date = serializers.DateField()
    timezone = serializers.CharField()
    generated_at = serializers.DateTimeField()
    day_start_at = serializers.DateTimeField()
    day_end_at = serializers.DateTimeField()
    events = CalendarEventSerializer(many=True)
    planned_tasks = TaskSerializer(many=True)
    due_tasks = TaskSerializer(many=True)
    overdue_tasks = TaskSerializer(many=True)
    unfinished_tasks = TaskSerializer(many=True)
    completed_tasks = TaskSerializer(many=True)
    pending_reminders = ReminderSerializer(many=True)
    conflicts = ScheduleConflictSerializer(many=True)
    next_event = CalendarEventSerializer(allow_null=True)
    minutes_until_next_event = serializers.IntegerField(allow_null=True, min_value=0)
    execution_now = TodayExecutionItemSerializer(many=True)
    execution_next = TodayExecutionItemSerializer(many=True)
    execution_later = TodayExecutionItemSerializer(many=True)

from django.core.management.base import BaseCommand

from apps.events.models import CalendarEvent
from apps.reminders.scheduling import ReminderScheduleService
from apps.tasks.models import Task


class Command(BaseCommand):
    help = "Reconcile automatic task and calendar-event reminders with the current schedule policy."

    def handle(self, *args: object, **options: object) -> None:
        task_count = 0
        for task in Task.objects.select_related("user").iterator():
            ReminderScheduleService.sync_task_reminders(task=task)
            task_count += 1

        event_count = 0
        for event in CalendarEvent.objects.select_related("user").iterator():
            ReminderScheduleService.sync_event_reminders(event=event)
            event_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciled automatic reminders for {task_count} tasks and {event_count} events."
            )
        )

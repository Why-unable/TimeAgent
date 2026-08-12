from celery import shared_task
from django.conf import settings

from apps.accounts.services import AccountService


@shared_task(name="accounts.cleanup_expired_guests")  # type: ignore[untyped-decorator]
def cleanup_expired_guests() -> int:
    return AccountService.cleanup_expired_guests(
        batch_size=int(getattr(settings, "GUEST_CLEANUP_BATCH_SIZE", 100))
    )

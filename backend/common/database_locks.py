from django.contrib.auth.models import User
from django.db import connection

SCHEDULE_WRITE_LOCK_NAMESPACE = 0x54494D45


def lock_user_schedule_writes(user: User) -> None:
    if user.pk is None:
        raise ValueError("Schedule write user must be persisted")
    if not connection.in_atomic_block:
        raise RuntimeError("Schedule write lock requires an active database transaction")
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s, %s)",
                [SCHEDULE_WRITE_LOCK_NAMESPACE, user.pk],
            )
        return
    User.objects.select_for_update().only("pk").get(pk=user.pk)

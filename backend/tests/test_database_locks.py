import pytest
from django.contrib.auth.models import User
from django.db import transaction

from common.database_locks import lock_user_schedule_writes


@pytest.mark.django_db
def test_schedule_write_lock_requires_a_persisted_user() -> None:
    with pytest.raises(ValueError, match="must be persisted"):
        lock_user_schedule_writes(User(username="unsaved"))


@pytest.mark.django_db(transaction=True)
def test_schedule_write_lock_requires_an_atomic_transaction() -> None:
    user = User.objects.create_user(username="lock-without-transaction")

    with pytest.raises(RuntimeError, match="active database transaction"):
        lock_user_schedule_writes(user)


@pytest.mark.django_db
def test_schedule_write_lock_can_be_reentered_in_one_transaction() -> None:
    user = User.objects.create_user(username="reentrant-schedule-lock")

    with transaction.atomic():
        lock_user_schedule_writes(user)
        lock_user_schedule_writes(user)

import builtins
from collections.abc import Sequence
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction

from apps.planning.models import AutomationPolicy
from apps.tasks.models import Task


class AutomationPolicyService:
    @staticmethod
    def list(*, user: User) -> list[AutomationPolicy]:
        return list(AutomationPolicy.objects.filter(user=user))

    @staticmethod
    def get(*, user: User, policy_id: UUID) -> AutomationPolicy:
        return AutomationPolicy.objects.get(user=user, pk=policy_id)

    @staticmethod
    @transaction.atomic
    def create_or_update(
        *,
        user: User,
        name: str,
        enabled: bool,
        allow_task_reschedule: bool,
        max_moves_per_run: int,
        requires_approval: bool,
        authorized_task_ids: Sequence[UUID] | None = None,
    ) -> AutomationPolicy:
        normalized_task_ids = AutomationPolicyService._authorized_task_ids(
            user=user,
            task_ids=authorized_task_ids or [],
        )
        policy, _ = AutomationPolicy.objects.select_for_update().get_or_create(
            user=user,
            name=name.strip(),
            defaults={
                "enabled": enabled,
                "allow_task_reschedule": allow_task_reschedule,
                "max_moves_per_run": max_moves_per_run,
                "requires_approval": requires_approval,
                "authorized_task_ids": normalized_task_ids,
            },
        )
        if (
            policy.enabled != enabled
            or policy.allow_task_reschedule != allow_task_reschedule
            or policy.max_moves_per_run != max_moves_per_run
            or policy.requires_approval != requires_approval
            or policy.authorized_task_ids != normalized_task_ids
        ):
            policy.enabled = enabled
            policy.allow_task_reschedule = allow_task_reschedule
            policy.max_moves_per_run = max_moves_per_run
            policy.requires_approval = requires_approval
            policy.authorized_task_ids = normalized_task_ids
            policy.full_clean()
            policy.save()
        policy.full_clean()
        return policy

    @staticmethod
    @transaction.atomic
    def update(
        *,
        user: User,
        policy_id: UUID,
        changes: dict[str, object],
    ) -> AutomationPolicy:
        allowed = {
            "name",
            "enabled",
            "allow_task_reschedule",
            "max_moves_per_run",
            "requires_approval",
            "authorized_task_ids",
        }
        if not changes or set(changes) - allowed:
            raise ValueError("Provide only supported automation policy fields")
        policy = AutomationPolicy.objects.select_for_update().get(pk=policy_id, user=user)
        if "authorized_task_ids" in changes:
            raw_task_ids = changes["authorized_task_ids"]
            if not isinstance(raw_task_ids, list):
                raise ValueError("authorized_task_ids must be a list")
            changes["authorized_task_ids"] = AutomationPolicyService._authorized_task_ids(
                user=user,
                task_ids=raw_task_ids,
            )
        for field, value in changes.items():
            setattr(policy, field, value)
        policy.full_clean()
        policy.save()
        return policy

    @staticmethod
    def _authorized_task_ids(
        *, user: User, task_ids: Sequence[object]
    ) -> builtins.list[str]:
        try:
            normalized = [UUID(str(task_id)) for task_id in task_ids]
        except ValueError as exc:
            raise ValueError("Every authorized task ID must be a UUID") from exc
        if len(set(normalized)) != len(normalized):
            raise ValueError("Authorized task IDs must be unique")
        if Task.objects.filter(user=user, pk__in=normalized).count() != len(normalized):
            raise ValueError("Every authorized task must belong to the current user")
        return [str(task_id) for task_id in normalized]

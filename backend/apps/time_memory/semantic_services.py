import hashlib
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.conversations.models import AgentRun
from apps.time_memory.models import (
    MemoryProposal,
    MemoryProposalOperation,
    MemoryProposalSource,
    MemoryProposalStatus,
    SemanticMemory,
    SemanticMemorySource,
    SemanticMemoryStatus,
)
from apps.time_memory.semantic_policy import MemoryPolicy
from apps.time_memory.semantic_schemas import MemoryProposalPayload


def _evidence_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProposalResult:
    proposal: MemoryProposal
    action: str


class SemanticMemoryService:
    @staticmethod
    def list_active(*, user: User) -> list[SemanticMemory]:
        now = timezone.now()
        return list(
            SemanticMemory.objects.filter(user=user, status=SemanticMemoryStatus.ACTIVE)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by("category", "key")
        )

    @staticmethod
    def list_for_context(*, user: User, limit: int = 12) -> list[SemanticMemory]:
        """Return active memories in a stable, bounded order for context injection."""
        return SemanticMemoryService.list_active(user=user)[: max(0, limit)]

    @staticmethod
    def search(
        *,
        user: User,
        query: str = "",
        category: str | None = None,
        limit: int = 10,
    ) -> list[SemanticMemory]:
        normalized_query = query.strip().casefold()
        normalized_category = category.strip() if category else None
        bounded_limit = min(max(limit, 1), 20)
        now = timezone.now()
        queryset = (
            SemanticMemory.objects.filter(user=user, status=SemanticMemoryStatus.ACTIVE)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by("category", "key")
        )
        if normalized_category:
            queryset = queryset.filter(category=normalized_category)
        memories = list(queryset[:200])
        if normalized_query:
            memories = [
                item
                for item in memories
                if normalized_query
                in f"{item.category} {item.key} {item.value}".casefold()
            ]
        return memories[:bounded_limit]

    @staticmethod
    def list_pending_proposals(*, user: User) -> list[MemoryProposal]:
        return list(
            MemoryProposal.objects.filter(user=user, status=MemoryProposalStatus.PENDING).order_by(
                "-created_at", "-id"
            )
        )

    @staticmethod
    def list_recent_direct_proposals(*, user: User, limit: int = 20) -> list[MemoryProposal]:
        since = timezone.now() - timedelta(days=7)
        return list(
            MemoryProposal.objects.filter(
                user=user,
                policy_reason="explicit_low_risk_direct_apply",
                status__in=[MemoryProposalStatus.APPLIED, MemoryProposalStatus.UNDONE],
                created_at__gte=since,
            )
            .select_related("applied_memory")
            .order_by("-created_at", "-id")[: min(max(limit, 1), 50)]
        )

    @staticmethod
    @transaction.atomic
    def create_proposal(
        *,
        user: User,
        payload: MemoryProposalPayload,
        source_run: AgentRun | None = None,
        model_alias: str = "",
        idempotency_key: str | None = None,
        source_type: str = MemoryProposalSource.BACKGROUND_EXTRACTION,
        target_memory: SemanticMemory | None = None,
        explicit_user_authorized: bool = False,
        direct_apply_mode: str = "confirm",
    ) -> ProposalResult:
        decision = MemoryPolicy.evaluate(
            payload,
            explicit_user_authorized=explicit_user_authorized,
            direct_apply_mode=direct_apply_mode,
        )
        if target_memory is not None and target_memory.user_id != user.pk:
            raise SemanticMemory.DoesNotExist
        if target_memory is None:
            target_memory = (
                SemanticMemory.objects.select_for_update()
                .filter(
                    user=user,
                    category=payload.category,
                    key=payload.key,
                    status=SemanticMemoryStatus.ACTIVE,
                )
                .first()
            )
        if payload.operation in {MemoryProposalOperation.UPDATE, MemoryProposalOperation.DELETE}:
            if target_memory is None:
                decision = decision.model_copy(
                    update={"action": "reject", "reason_code": "target_not_found"}
                )
        key = idempotency_key or SemanticMemoryService._default_idempotency_key(
            user=user, payload=payload, source_run=source_run
        )
        proposal, created = MemoryProposal.objects.get_or_create(
            user=user,
            idempotency_key=key,
            defaults={
                "source_run": source_run,
                "source_type": source_type,
                "target_memory": target_memory,
                "target_version": target_memory.version if target_memory is not None else None,
                "operation": payload.operation,
                "category": payload.category,
                "key": payload.key,
                "value": payload.value,
                "confidence": payload.confidence,
                "evidence_hash": _evidence_hash(payload.evidence_excerpt),
                "reason_code": payload.reason_code,
                "policy_reason": decision.reason_code,
                "model_alias": model_alias,
                "status": (
                    MemoryProposalStatus.PENDING
                    if decision.action in {"apply", "require_confirmation"}
                    else MemoryProposalStatus.REJECTED
                ),
            },
        )
        if not created:
            return ProposalResult(proposal=proposal, action="duplicate")
        if decision.action == "apply":
            proposal = SemanticMemoryService.decide_proposal(
                user=user,
                proposal_id=proposal.pk,
                approve=True,
            )
            return ProposalResult(proposal=proposal, action="applied")
        return ProposalResult(proposal=proposal, action=decision.action)

    @staticmethod
    @transaction.atomic
    def decide_proposal(*, user: User, proposal_id: UUID, approve: bool) -> MemoryProposal:
        proposal = MemoryProposal.objects.select_for_update().get(id=proposal_id, user=user)
        if proposal.status != MemoryProposalStatus.PENDING:
            return proposal
        if approve:
            current_target = (
                SemanticMemory.objects.select_for_update()
                .filter(
                    user=user,
                    category=proposal.category,
                    key=proposal.key,
                    status=SemanticMemoryStatus.ACTIVE,
                )
                .first()
            )
            target_conflicted = (
                current_target is None
                if proposal.target_memory_id is not None
                else current_target is not None
            ) or (
                current_target is not None
                and (
                    current_target.pk != proposal.target_memory_id
                    or current_target.version != proposal.target_version
                )
            )
            if target_conflicted:
                proposal.status = MemoryProposalStatus.CONFLICTED
                proposal.policy_reason = "target_version_conflict"
                proposal.decided_at = timezone.now()
                proposal.save(
                    update_fields=["status", "policy_reason", "decided_at", "updated_at"]
                )
                return proposal
        proposal.status = (
            MemoryProposalStatus.APPROVED if approve else MemoryProposalStatus.REJECTED
        )
        proposal.decided_at = timezone.now()
        proposal.save(update_fields=["status", "decided_at", "updated_at"])
        if approve:
            applied_memory, changed = SemanticMemoryService._apply_approved_proposal(proposal)
            proposal.status = MemoryProposalStatus.APPLIED
            proposal.applied_memory = applied_memory
            proposal.applied_memory_version = (
                applied_memory.version if applied_memory is not None else None
            )
            proposal.changed_business_state = changed
            proposal.save(
                update_fields=[
                    "status",
                    "applied_memory",
                    "applied_memory_version",
                    "changed_business_state",
                    "updated_at",
                ]
            )
            SemanticMemoryService._enqueue_projection(user.pk)
        return proposal

    @staticmethod
    @transaction.atomic
    def _apply_approved_proposal(
        proposal: MemoryProposal,
    ) -> tuple[SemanticMemory | None, bool]:
        current_query = SemanticMemory.objects.select_for_update().filter(
            user=proposal.user,
            status=SemanticMemoryStatus.ACTIVE,
        )
        current = (
            current_query.filter(pk=proposal.target_memory_id).first()
            if proposal.target_memory_id is not None
            else current_query.filter(category=proposal.category, key=proposal.key).first()
        )
        now = timezone.now()
        if proposal.operation == MemoryProposalOperation.DELETE:
            if current is not None:
                current.status = SemanticMemoryStatus.DELETED
                current.deleted_at = now
                current.version += 1
                current.save(update_fields=["status", "deleted_at", "version", "updated_at"])
                return current, True
            return None, False
        if (
            proposal.operation in {MemoryProposalOperation.CREATE, MemoryProposalOperation.UPDATE}
            and current is not None
        ):
            if current.value == proposal.value:
                return current, False
            current.status = SemanticMemoryStatus.SUPERSEDED
            current.save(update_fields=["status", "updated_at"])
        created = SemanticMemory.objects.create(
            user=proposal.user,
            category=proposal.category,
            key=proposal.key,
            value=proposal.value,
            status=SemanticMemoryStatus.ACTIVE,
            source_type=(
                SemanticMemorySource.EXPLICIT_USER
                if proposal.source_type == MemoryProposalSource.AGENT_TOOL
                else SemanticMemorySource.BACKGROUND_EXTRACTION
            ),
            source_run=proposal.source_run,
            confidence=proposal.confidence,
            evidence_hash=proposal.evidence_hash,
            version=(current.version + 1 if current is not None else 1),
            valid_from=now,
        )
        return created, True

    @staticmethod
    @transaction.atomic
    def undo_proposal(*, user: User, proposal_id: UUID) -> MemoryProposal:
        proposal = (
            MemoryProposal.objects.select_for_update()
            .select_related("target_memory", "applied_memory")
            .get(pk=proposal_id, user=user)
        )
        if proposal.status == MemoryProposalStatus.UNDONE:
            return proposal
        if proposal.status != MemoryProposalStatus.APPLIED or not proposal.changed_business_state:
            raise ValueError("This memory proposal has no reversible applied change")
        if proposal.applied_memory_id is None or proposal.applied_memory_version is None:
            raise ValueError("Applied memory audit data is incomplete")
        applied = SemanticMemory.objects.select_for_update().get(
            pk=proposal.applied_memory_id,
            user=user,
        )
        if applied.version != proposal.applied_memory_version:
            raise ValueError("Memory changed after this proposal was applied")
        now = timezone.now()
        if proposal.operation == MemoryProposalOperation.DELETE:
            if applied.status != SemanticMemoryStatus.DELETED:
                raise ValueError("Deleted memory is no longer in the expected state")
            if SemanticMemory.objects.select_for_update().filter(
                user=user,
                category=proposal.category,
                key=proposal.key,
                status=SemanticMemoryStatus.ACTIVE,
            ).exists():
                raise ValueError("A newer active memory already exists")
            applied.status = SemanticMemoryStatus.ACTIVE
            applied.deleted_at = None
            applied.valid_from = now
            applied.version += 1
            applied.save(
                update_fields=[
                    "status",
                    "deleted_at",
                    "valid_from",
                    "version",
                    "updated_at",
                ]
            )
        elif proposal.target_memory_id is None:
            if applied.status != SemanticMemoryStatus.ACTIVE:
                raise ValueError("Applied memory is no longer active")
            applied.status = SemanticMemoryStatus.DELETED
            applied.deleted_at = now
            applied.version += 1
            applied.save(update_fields=["status", "deleted_at", "version", "updated_at"])
        else:
            if applied.status != SemanticMemoryStatus.ACTIVE:
                raise ValueError("Applied memory is no longer active")
            target = SemanticMemory.objects.select_for_update().get(
                pk=proposal.target_memory_id,
                user=user,
                status=SemanticMemoryStatus.SUPERSEDED,
            )
            if target.version != proposal.target_version:
                raise ValueError("Previous memory changed after this proposal was applied")
            applied.status = SemanticMemoryStatus.SUPERSEDED
            applied.version += 1
            applied.save(update_fields=["status", "version", "updated_at"])
            target.status = SemanticMemoryStatus.ACTIVE
            target.deleted_at = None
            target.valid_from = now
            target.version = max(target.version, applied.version) + 1
            target.save(
                update_fields=[
                    "status",
                    "deleted_at",
                    "valid_from",
                    "version",
                    "updated_at",
                ]
            )
        proposal.status = MemoryProposalStatus.UNDONE
        proposal.undone_at = now
        proposal.save(update_fields=["status", "undone_at", "updated_at"])
        SemanticMemoryService._enqueue_projection(user.pk)
        return proposal

    @staticmethod
    def _enqueue_projection(user_id: int) -> None:
        def enqueue_projection() -> None:
            try:
                from apps.time_memory.tasks import rebuild_semantic_memory_projection

                rebuild_semantic_memory_projection.delay(str(user_id))
            except Exception:
                # The Store is a disposable projection; approval remains authoritative.
                import logging

                logging.getLogger(__name__).warning(
                    "semantic_memory_projection_enqueue_failed user_id=%s",
                    user_id,
                    exc_info=True,
                )

        transaction.on_commit(enqueue_projection)

    @staticmethod
    def _default_idempotency_key(
        *, user: User, payload: MemoryProposalPayload, source_run: AgentRun | None
    ) -> str:
        source = str(source_run.pk) if source_run else "manual"
        digest = hashlib.sha256(
            f"{user.pk}:{source}:{payload.operation}:{payload.category}:{payload.key}:{payload.value}".encode()
        ).hexdigest()[:32]
        return f"memory-v1:{source}:{digest}"

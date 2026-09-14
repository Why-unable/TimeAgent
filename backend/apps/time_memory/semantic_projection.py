from typing import Any

from django.contrib.auth.models import User
from langgraph.store.base import BaseStore

from apps.time_memory.semantic_services import SemanticMemoryService

PROJECTION_KEY = "collection"


class SemanticMemoryProjection:
    """Rebuildable LangGraph Store projection of PostgreSQL semantic memories."""

    @staticmethod
    def namespace(user_id: str) -> tuple[str, str, str]:
        return ("users", user_id, "semantic_memory")

    @classmethod
    def rebuild(cls, *, store: BaseStore, user: User) -> int:
        memories = SemanticMemoryService.list_for_context(user=user, limit=10_000)
        if not memories:
            store.delete(cls.namespace(str(user.pk)), PROJECTION_KEY)
            return 0
        payload: list[dict[str, Any]] = [
            {
                "id": str(memory.pk),
                "category": memory.category,
                "key": memory.key,
                "value": memory.value,
                "confidence": memory.confidence,
                "version": memory.version,
            }
            for memory in memories
        ]
        store.put(cls.namespace(str(user.pk)), PROJECTION_KEY, {"memories": payload})
        return len(payload)

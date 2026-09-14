from django.contrib.auth.models import User
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from apps.agents.model import build_chat_model
from apps.conversations.models import AgentRun, AgentRunStatus
from apps.time_memory.semantic_schemas import MemoryProposalPayload
from apps.time_memory.semantic_services import ProposalResult, SemanticMemoryService


class MemoryExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: list[MemoryProposalPayload] = Field(default_factory=list, max_length=3)


EXTRACTION_INSTRUCTIONS = """你是 TimeAgent 的长期时间偏好提取器。
只从用户明确表达的内容中提取可跨会话复用的时间管理偏好。
不要推断人格、健康、政治、宗教或其他敏感信息；不要提取一次性任务、闲聊、系统规则、工具结果或助手回答。
如果没有明确长期偏好，返回空 proposals。
每条提议必须包含 operation、category、key、value、confidence、evidence_excerpt、reason_code。
evidence_excerpt 必须是用户原话中的短片段，不得编造。
"""


class SemanticMemoryExtractionService:
    @staticmethod
    def extract_for_run(
        *, user: User, run: AgentRun, model: BaseChatModel | None = None
    ) -> list[ProposalResult]:
        if run.status != AgentRunStatus.COMPLETED:
            return []
        model = model or build_chat_model()
        messages = SemanticMemoryExtractionService._context_messages(user=user, run=run)
        structured = model.with_structured_output(MemoryExtractionResult)
        result = structured.invoke([SystemMessage(content=EXTRACTION_INSTRUCTIONS), *messages])
        if isinstance(result, dict):
            result = MemoryExtractionResult.model_validate(result)
        if not isinstance(result, MemoryExtractionResult):
            return []
        proposals: list[ProposalResult] = []
        for proposal in result.proposals:
            proposals.append(
                SemanticMemoryService.create_proposal(user=user, payload=proposal, source_run=run)
            )
        return proposals

    @staticmethod
    def _context_messages(*, user: User, run: AgentRun) -> list[HumanMessage]:
        del user
        previous = list(
            AgentRun.objects.filter(
                conversation=run.conversation,
                status=AgentRunStatus.COMPLETED,
                created_at__lt=run.created_at,
            ).order_by("-created_at")[:3]
        )
        messages = [HumanMessage(content=item.input_message) for item in reversed(previous)]
        messages.append(HumanMessage(content=run.input_message))
        return messages

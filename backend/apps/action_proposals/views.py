from uuid import UUID, uuid4

from django.contrib.auth.models import User
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.action_proposals.models import ActionProposal, ActionProposalStatus
from apps.action_proposals.serializers import (
    ActionProposalSerializer,
    ProposalDecisionResponseSerializer,
    ProposalDecisionSerializer,
    ProposalEditDecisionSerializer,
)
from apps.action_proposals.services import (
    ActionProposalService,
    ProposalConflictError,
    ProposalDecision,
    ProposalExpiredError,
)
from apps.conversations.services import AgentRunService
from apps.conversations.tasks import resume_agent_run_task


class AgentQueueUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The agent execution queue is unavailable"
    default_code = "agent_queue_unavailable"


def _user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user


class ActionProposalListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[OpenApiParameter("status", str, required=False)],
        responses=ActionProposalSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        status_filter = request.query_params.get("status")
        if status_filter and status_filter not in ActionProposalStatus.values:
            return Response({"detail": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)
        proposals = ActionProposalService.list(user=_user(request), status=status_filter)
        return Response(ActionProposalSerializer(proposals, many=True).data)


class ActionProposalDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ActionProposalSerializer)
    def get(self, request: Request, proposal_id: UUID) -> Response:
        try:
            proposal = ActionProposalService.get(user=_user(request), proposal_id=proposal_id)
        except ActionProposal.DoesNotExist as exc:
            raise Http404 from exc
        return Response(ActionProposalSerializer(proposal).data)


class ProposalDecisionView(APIView):
    permission_classes = [IsAuthenticated]
    decision: str

    def serializer_class(self) -> type[ProposalDecisionSerializer]:
        return (
            ProposalEditDecisionSerializer
            if self.decision == "edit"
            else ProposalDecisionSerializer
        )

    @extend_schema(
        request=ProposalDecisionSerializer,
        responses={
            202: ProposalDecisionResponseSerializer,
            200: ProposalDecisionResponseSerializer,
            409: OpenApiResponse(),
        },
    )
    def post(self, request: Request, proposal_id: UUID) -> Response:
        serializer = self.serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            result = ActionProposalService.decide(
                user=_user(request),
                proposal_id=proposal_id,
                expected_version=values["expected_version"],
                decision=self.decision,  # type: ignore[arg-type]
                decision_idempotency_key=values["operation_id"],
                edited_payload=values.get("action_payload"),
                reason=values.get("reason", ""),
            )
        except ActionProposal.DoesNotExist as exc:
            raise Http404 from exc
        except (ProposalConflictError, ProposalExpiredError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        if result.proposal.status == ActionProposalStatus.EXPIRED:
            return Response(
                {"detail": "Action proposal has expired"},
                status=status.HTTP_409_CONFLICT,
            )

        response_status: int = status.HTTP_200_OK
        if result.resume_ready:
            self._queue_resume(result)
            response_status = status.HTTP_202_ACCEPTED
        return Response(
            {
                "proposal": ActionProposalSerializer(result.proposal).data,
                "resume_queued": result.resume_ready,
            },
            status=response_status,
        )

    @staticmethod
    def _queue_resume(result: ProposalDecision) -> None:
        run = result.proposal.agent_run
        task_id = str(uuid4())
        if not AgentRunService.reserve_resume_task(run, task_id):
            return
        try:
            resume_agent_run_task.apply_async(args=[str(run.pk)], task_id=task_id)
        except Exception as exc:
            AgentRunService.release_resume_task(run, task_id)
            raise AgentQueueUnavailable from exc


class ProposalApproveView(ProposalDecisionView):
    decision = "approve"


class ProposalEditView(ProposalDecisionView):
    decision = "edit"

    @extend_schema(
        request=ProposalEditDecisionSerializer,
        responses={
            202: ProposalDecisionResponseSerializer,
            200: ProposalDecisionResponseSerializer,
            409: OpenApiResponse(),
        },
    )
    def post(self, request: Request, proposal_id: UUID) -> Response:
        return super().post(request, proposal_id)


class ProposalRejectView(ProposalDecisionView):
    decision = "reject"

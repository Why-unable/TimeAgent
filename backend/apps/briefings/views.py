from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.briefings.models import BriefingDefinition, BriefingRun
from apps.briefings.serializers import (
    BriefingDefinitionSerializer,
    BriefingRunSerializer,
    LaunchBriefingResponseSerializer,
    LaunchBriefingSerializer,
)
from apps.briefings.services import BriefingDefinitionService
from apps.conversations.models import AgentRun, ConversationKind
from apps.conversations.serializers import AgentRunSerializer, ConversationSerializer
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.conversations.tasks import execute_agent_run_task
from apps.preferences.services import UserPreferenceService
from common.time import get_timezone


class BriefingQueueUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The briefing execution queue is unavailable"
    default_code = "briefing_queue_unavailable"


def _user(request: Request) -> User:
    if not isinstance(request.user, User):
        raise Http404
    return request.user


class BriefingDefinitionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=BriefingDefinitionSerializer(many=True))
    def get(self, request: Request) -> Response:
        items = BriefingDefinitionService.list_definitions(user=_user(request))
        return Response(BriefingDefinitionSerializer(items, many=True).data)

    @extend_schema(
        request=BriefingDefinitionSerializer,
        responses={201: BriefingDefinitionSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = BriefingDefinitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = BriefingDefinitionService.save(
            user=_user(request),
            name=serializer.validated_data["name"],
            enabled_sections=serializer.validated_data["enabled_sections"],
            locale=serializer.validated_data.get("locale", ""),
            timezone_name=serializer.validated_data.get("timezone", ""),
            style=serializer.validated_data.get("style", "balanced"),
            include_empty_sections=serializer.validated_data.get("include_empty_sections", False),
        )
        return Response(BriefingDefinitionSerializer(item).data, status=status.HTTP_201_CREATED)


class BriefingDefinitionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request: Request, definition_id: UUID) -> BriefingDefinition:
        try:
            return BriefingDefinitionService.get(user=_user(request), definition_id=definition_id)
        except BriefingDefinition.DoesNotExist as exc:
            raise Http404 from exc

    @extend_schema(responses=BriefingDefinitionSerializer)
    def get(self, request: Request, definition_id: UUID) -> Response:
        return Response(BriefingDefinitionSerializer(self._get(request, definition_id)).data)

    @extend_schema(request=BriefingDefinitionSerializer, responses=BriefingDefinitionSerializer)
    def patch(self, request: Request, definition_id: UUID) -> Response:
        item = self._get(request, definition_id)
        serializer = BriefingDefinitionSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = {
            "name": item.name,
            "enabled_sections": item.enabled_sections,
            "locale": item.locale,
            "timezone": item.timezone,
            "style": item.style,
            "include_empty_sections": item.include_empty_sections,
            **serializer.validated_data,
        }
        updated = BriefingDefinitionService.save(
            user=_user(request),
            definition=item,
            name=values["name"],
            enabled_sections=values["enabled_sections"],
            locale=values["locale"],
            timezone_name=values["timezone"],
            style=values["style"],
            include_empty_sections=values["include_empty_sections"],
        )
        if "is_active" in serializer.validated_data:
            updated.is_active = serializer.validated_data["is_active"]
            updated.save(update_fields=["is_active", "updated_at"])
        return Response(BriefingDefinitionSerializer(updated).data)


class BriefingRunListLaunchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=BriefingRunSerializer(many=True))
    def get(self, request: Request) -> Response:
        runs = BriefingRun.objects.filter(user=_user(request)).prefetch_related("section_runs")
        return Response(BriefingRunSerializer(runs, many=True).data)

    @extend_schema(
        request=LaunchBriefingSerializer,
        responses={202: LaunchBriefingResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = LaunchBriefingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        user = _user(request)
        definition_id = values.get("definition_id")
        definition = (
            BriefingDefinitionService.get(user=user, definition_id=definition_id)
            if definition_id
            else BriefingDefinitionService.default_for_user(user)
        )
        preference = UserPreferenceService.get_for_user(user)
        timezone_name = definition.timezone or (
            preference.timezone if preference else settings.DEFAULT_USER_TIMEZONE
        )
        target_date = (
            values.get("target_date")
            or timezone.now().astimezone(get_timezone(timezone_name)).date()
        )
        title = f"{target_date.isoformat()} · {definition.name}"
        operation_id = values.get("operation_id", uuid4())
        message = f"手动生成 {target_date.isoformat()} 的{definition.name}"
        trigger_payload = {
            "briefing_definition_id": str(definition.pk),
            "target_date": target_date.isoformat(),
            "request": "用户从简报页面手动触发。",
        }
        run = (
            AgentRun.objects.select_related("conversation")
            .filter(operation_id=operation_id)
            .first()
        )
        if run is not None:
            if (
                run.conversation.user_id != user.pk
                or run.conversation.kind != ConversationKind.MANUAL_BRIEFING
                or run.input_message != message
                or run.trigger_type != "manual_briefing"
                or run.trigger_payload != trigger_payload
                or not run.synthetic_input
            ):
                raise ValidationError(
                    {"operation_id": "operation_id already belongs to a different request"}
                )
            conversation = run.conversation
        else:
            conversation = ConversationService.create(
                user=user,
                title=title,
                kind=ConversationKind.MANUAL_BRIEFING,
            )
            run = AgentRunService.start(
                StartRunCommand(
                    conversation=conversation,
                    operation_id=operation_id,
                    request_id=request.headers.get("X-Request-ID", str(uuid4())),
                    message=message,
                    trigger_type="manual_briefing",
                    trigger_payload=trigger_payload,
                    synthetic_input=True,
                )
            )
        task_id = str(uuid4())
        if AgentRunService.reserve_execution_task(run, task_id):
            try:
                execute_agent_run_task.apply_async(args=[str(run.pk)], task_id=task_id)
            except Exception as exc:
                AgentRunService.release_execution_task(run, task_id)
                raise BriefingQueueUnavailable from exc
            run.refresh_from_db()
        return Response(
            {
                "conversation": ConversationSerializer(conversation).data,
                "agent_run": AgentRunSerializer(run).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class BriefingRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=BriefingRunSerializer)
    def get(self, request: Request, run_id: UUID) -> Response:
        try:
            run = BriefingRun.objects.prefetch_related("section_runs").get(
                pk=run_id, user=_user(request)
            )
        except BriefingRun.DoesNotExist as exc:
            raise Http404 from exc
        return Response(BriefingRunSerializer(run).data)

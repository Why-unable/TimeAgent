from __future__ import annotations

import builtins
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.utils import timezone
from pydantic import TypeAdapter, ValidationError

from apps.action_proposals.models import ActionProposal, ActionProposalStatus
from apps.action_proposals.risk_policy import policy_for_tool
from apps.conversations.models import AgentRun
from apps.events.series_services import EventSeriesService
from apps.events.services import EventService
from apps.events.temporal_services import EventTemporalResolutionService
from apps.planning.adaptive import AdaptivePlanningService
from apps.planning.automation import AutomationPolicyService
from apps.planning.models import SchedulePlanStatus
from apps.planning.services import PlanningService
from apps.reminders.services import ReminderService
from apps.tasks.services import TaskService

DATETIME_ADAPTER = TypeAdapter(datetime)

ACTION_TITLES = {
    "mutate_events": "调整多项日程",
    "create_task_batch": "创建多项任务",
    "create_recurring_event": "创建重复日程",
    "apply_schedule_plan": "应用任务计划",
    "apply_local_replan": "调整受影响的任务安排",
    "change_task_batch_state": "更新多项任务状态",
    "reschedule_task": "调整任务时间",
    "update_reminder": "修改提醒",
    "set_reminder_target": "更改提醒关联对象",
    "cancel_reminder": "取消提醒",
    "cancel_task": "取消任务",
    "remember_time_preference": "保存时间偏好",
    "update_time_preference": "修改时间偏好",
    "forget_time_preference": "删除时间偏好",
    "create_event": "创建日程",
    "create_event_batch": "创建多项日程",
    "update_event": "修改日程",
    "cancel_event": "取消日程",
}

CONFLICT_ACTION_LABELS = {
    "create_event": "创建",
    "create_event_batch": "创建",
    "create_recurring_event": "创建",
    "update_event": "调整",
    "mutate_events": "继续",
    "apply_schedule_plan": "应用",
    "apply_local_replan": "调整",
    "reschedule_task": "调整",
}

TASK_STATUS_LABELS = {
    "pending": "待处理",
    "in_progress": "进行中",
    "completed": "已完成",
    "cancelled": "已取消",
}

TASK_PRIORITY_LABELS = {"low": "低", "medium": "普通", "high": "高", "urgent": "紧急"}
REMINDER_CHANNEL_LABELS = {
    "console": "站内",
    "email": "邮件",
    "telegram": "Telegram",
    "browser": "浏览器",
}
REMINDER_STATUS_LABELS = {
    "pending": "等待提醒",
    "queued": "已排队",
    "sending": "正在发送",
    "sent": "已发送",
    "failed": "发送失败",
    "cancelled": "已取消",
    "missed": "已错过",
}
MEMORY_CATEGORY_LABELS = {
    "work_hours": "工作时间",
    "preferred_work_period": "偏好时段",
    "communication_style": "沟通方式",
    "break_preference": "休息偏好",
    "planning_preference": "安排偏好",
}


class ProposalConflictError(ValueError):
    pass


class ProposalExpiredError(ValueError):
    pass


def _is_actionable_review_context(display_context: dict[str, Any]) -> bool:
    review_items = display_context.get("review_items")
    return (
        display_context.get("review_complete") is True
        and isinstance(review_items, list)
        and bool(review_items)
        and (
            "conflict_check" not in display_context
            or (
                display_context.get("conflict_check") == "completed"
                and not display_context.get("conflicts")
            )
        )
    )


def _refresh_target_versions(
    *,
    tool_name: str,
    args: dict[str, Any],
    display_context: dict[str, Any],
) -> dict[str, Any] | None:
    stale_targets = display_context.get("stale_targets")
    if not isinstance(stale_targets, list) or not stale_targets:
        return None

    refreshed_args = dict(args)
    if tool_name in {"update_event", "apply_schedule_plan"}:
        current_version = stale_targets[0].get("current_version")
        if isinstance(current_version, int):
            refreshed_args["expected_version"] = current_version
        return refreshed_args if refreshed_args != args else None

    if tool_name != "mutate_events":
        return None
    operations = args.get("operations")
    if not isinstance(operations, list):
        return None
    refreshed_operations = [
        dict(operation) if isinstance(operation, dict) else operation for operation in operations
    ]
    changed = False
    for stale_target in stale_targets:
        if not isinstance(stale_target, dict):
            continue
        index = stale_target.get("operation_index")
        current_version = stale_target.get("current_version")
        if (
            isinstance(index, int)
            and 0 <= index < len(refreshed_operations)
            and isinstance(refreshed_operations[index], dict)
            and isinstance(current_version, int)
        ):
            refreshed_operations[index]["expected_version"] = current_version
            changed = True
    if not changed:
        return None
    refreshed_args["operations"] = refreshed_operations
    return refreshed_args


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    proposal: ActionProposal
    resume_ready: bool


class ActionProposalService:
    @staticmethod
    @transaction.atomic
    def create_from_interrupt(
        *,
        run: AgentRun,
        interrupt_value: Any,
        interrupt_id: str | None = None,
    ) -> list[ActionProposal]:
        if not isinstance(interrupt_value, dict):
            raise ValueError("HITL interrupt payload must be an object")
        actions = interrupt_value.get("action_requests")
        configs = interrupt_value.get("review_configs")
        if (
            not isinstance(actions, list)
            or not isinstance(configs, list)
            or len(actions) != len(configs)
        ):
            raise ValueError("HITL interrupt payload is malformed")

        expires_at = timezone.now() + timedelta(
            seconds=getattr(settings, "ACTION_PROPOSAL_TTL_SECONDS", 86400)
        )
        proposals: list[ActionProposal] = []
        for index, (action, config) in enumerate(zip(actions, configs, strict=True)):
            if not isinstance(action, dict) or not isinstance(config, dict):
                raise ValueError("HITL action and review config must be objects")
            tool_name = str(action.get("name", ""))
            args = action.get("args")
            policy = policy_for_tool(tool_name)
            if policy is None or not isinstance(args, dict):
                raise ValueError("HITL action is not an approved high-risk tool")
            if config.get("action_name", tool_name) != tool_name:
                raise ValueError("HITL review config does not match its action")
            allowed_decisions = config.get("allowed_decisions")
            if allowed_decisions != list(policy.allowed_decisions):
                raise ValueError("HITL review decisions do not match the server risk policy")
            tool_call_id = f"pending:{interrupt_id or run.pk}:{index}"
            proposal, _ = ActionProposal.objects.get_or_create(
                agent_run=run,
                tool_call_id=tool_call_id,
                defaults={
                    "user": run.conversation.user,
                    "conversation": run.conversation,
                    "original_request": run.input_message,
                    "explanation": str(action.get("description", policy.description)),
                    "action_type": tool_name,
                    "action_payload": args,
                    "original_payload": args,
                    "display_context": ActionProposalService._display_context(
                        run=run,
                        tool_name=tool_name,
                        args=args,
                        allowed_decisions=allowed_decisions,
                        position=index,
                    ),
                    "risk_level": policy.risk_level,
                    "expires_at": expires_at,
                    "idempotency_key": f"{run.pk}:{tool_call_id}",
                },
            )
            proposals.append(proposal)
        return proposals

    @staticmethod
    @transaction.atomic
    def bind_tool_call(
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ActionProposal | None:
        resolved_run_id = UUID(run_id)
        existing = ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
        ).first()
        if existing is not None:
            return existing
        proposal = (
            ActionProposal.objects.select_for_update()
            .filter(
                agent_run_id=resolved_run_id,
                action_type=tool_name,
                action_payload=arguments,
                status=ActionProposalStatus.APPROVED,
                resumed_at__isnull=False,
                tool_call_id__startswith="pending:",
            )
            .order_by("created_at", "id")
            .first()
        )
        if proposal is None:
            return None
        proposal.tool_call_id = tool_call_id
        proposal.save(update_fields=["tool_call_id", "updated_at"])
        return proposal

    @staticmethod
    def get_approved_tool_execution(
        *,
        user: User,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ActionProposal:
        """Return the resumed approval proving this exact tool call may execute."""

        return ActionProposal.objects.get(
            user=user,
            agent_run_id=UUID(run_id),
            tool_call_id=tool_call_id,
            action_type=tool_name,
            action_payload=arguments,
            status=ActionProposalStatus.EXECUTING,
            decision_type="approve",
            approved_at__isnull=False,
            resumed_at__isnull=False,
        )

    @staticmethod
    def _display_value(value: Any) -> str:
        if value is None or value == "":
            return "未提供"
        if isinstance(value, dict | list):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    @staticmethod
    def _review_item(
        *,
        title: str,
        detail: str = "",
        time_label: str = "",
        proposed_time_label: str = "",
        start_at: Any = None,
        end_at: Any = None,
        due_at: Any = None,
        proposed_start_at: Any = None,
        proposed_end_at: Any = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {"title": title}
        if detail:
            item["detail"] = detail
        if time_label:
            item["time_label"] = time_label
        if proposed_time_label:
            item["proposed_time_label"] = proposed_time_label
        for key, value in {
            "start_at": start_at,
            "end_at": end_at,
            "due_at": due_at,
            "proposed_start_at": proposed_start_at,
            "proposed_end_at": proposed_end_at,
        }.items():
            if value is not None:
                item[key] = value.isoformat() if isinstance(value, datetime) else str(value)
        return item

    @staticmethod
    def _action_review_context(
        *,
        user: User,
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        title = str(args.get("title", "")).strip()
        if tool_name == "create_task_batch":
            tasks = args.get("tasks")
            task_items = tasks if isinstance(tasks, list) else []
            previews = []
            for index, item in enumerate(task_items, start=1):
                if not isinstance(item, dict):
                    continue
                task_title = str(item.get("title", "")).strip() or f"第 {index} 项任务"
                details = []
                project = str(item.get("project", "")).strip()
                if project:
                    details.append(f"项目：{project}")
                priority = str(item.get("priority", "medium"))
                details.append(f"优先级：{TASK_PRIORITY_LABELS.get(priority, priority)}")
                if item.get("estimated_minutes") is not None:
                    details.append(f"预计用时：{item['estimated_minutes']} 分钟")
                if item.get("tags"):
                    details.append(f"标签：{ActionProposalService._display_value(item['tags'])}")
                previews.append(
                    ActionProposalService._review_item(
                        title=task_title,
                        detail="；".join(details),
                        proposed_time_label="计划安排",
                        proposed_start_at=item.get("planned_start_at"),
                        proposed_end_at=item.get("planned_end_at"),
                        due_at=item.get("due_at"),
                    )
                )
            result.update(
                {
                    "action_summary": f"将创建 {len(task_items)} 个任务。",
                    "review_items": previews,
                    "review_complete": len(previews) == len(task_items) and bool(task_items),
                }
            )
        elif tool_name == "change_task_batch_state":
            raw_items = args.get("items")
            task_items = raw_items if isinstance(raw_items, list) else []
            target_status = str(args.get("status", ""))
            previews = []
            task_details_complete = True
            for item in task_items:
                if not isinstance(item, dict):
                    continue
                try:
                    task = TaskService.get_task(
                        user=user, task_id=UUID(str(item.get("task_id", "")))
                    )
                except (ObjectDoesNotExist, TypeError, ValueError):
                    task_details_complete = False
                    previews.append(
                        ActionProposalService._review_item(
                            title="任务详情暂不可用",
                            detail=(
                                f"目标状态：{TASK_STATUS_LABELS.get(target_status, target_status)}"
                            ),
                        )
                    )
                    continue
                previews.append(
                    ActionProposalService._review_item(
                        title=task.title,
                        detail=(
                            f"状态：{TASK_STATUS_LABELS.get(task.status, task.status)} → "
                            f"{TASK_STATUS_LABELS.get(target_status, target_status)}"
                        ),
                        start_at=task.planned_start_at,
                        end_at=task.planned_end_at,
                        due_at=task.due_at,
                    )
                )
            result.update(
                {
                    "action_summary": (
                        f"将更新 {len(task_items)} 个任务的状态为 "
                        f"{TASK_STATUS_LABELS.get(target_status, target_status)}。"
                    ),
                    "review_items": previews,
                    "review_complete": (
                        task_details_complete
                        and bool(task_items)
                        and len(previews) == len(task_items)
                    ),
                }
            )
        elif tool_name == "apply_schedule_plan":
            try:
                plan = PlanningService.get_schedule_plan(
                    user=user,
                    plan_id=UUID(str(args.get("plan_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                result["action_summary"] = "将应用已保存的任务计划；计划详情暂不可用。"
                result["review_complete"] = False
            else:
                expected_version = args.get("expected_version")
                result["stale_targets"] = (
                    [
                        {
                            "expected_version": expected_version,
                            "current_version": plan.version,
                        }
                    ]
                    if expected_version != plan.version
                    else []
                )
                if plan.status != SchedulePlanStatus.DRAFT:
                    result["review_notice"] = (
                        "这份计划已不再是可应用的草案，请重新生成后再提交审批。"
                    )
                elif plan.expires_at <= timezone.now():
                    result["review_notice"] = "这份计划已过期，请重新生成后再提交审批。"
                plan_items = [
                    item
                    for item in plan.items
                    if isinstance(item, dict)
                    and item.get("kind") != "plan_evidence"
                    and item.get("task_id")
                ]
                previews = []
                task_details_complete = True
                affected_task_ids = {
                    str(item.get("task_id")) for item in plan_items if item.get("task_id")
                }
                for item in plan_items:
                    try:
                        task = TaskService.get_task(user=user, task_id=UUID(str(item["task_id"])))
                        task_title = task.title
                    except (ObjectDoesNotExist, TypeError, ValueError):
                        task_title = "任务详情暂不可用"
                        task_details_complete = False
                    state = str(item.get("state", "placed"))
                    if state == "placed":
                        detail = "计划安排时间"
                    else:
                        reason_labels = {
                            "deadline_before_range": "截止时间早于计划范围",
                            "planning_decision_window_empty": "指定条件下没有可安排时间",
                            "planning_predecessor_unavailable": "前置任务尚未安排",
                            "exact_start_outside_allowed_window": "指定时间超出可安排时段",
                            "exact_start_unavailable": "指定时间与现有安排冲突",
                            "insufficient_free_capacity": "当前可用时间不足",
                            "task_planning_locked": "任务当前已锁定",
                        }
                        raw_reasons = item.get("reason_codes")
                        labels = []
                        if isinstance(raw_reasons, list):
                            labels = [
                                reason_labels[code]
                                for code in raw_reasons
                                if isinstance(code, str) and code in reason_labels
                            ]
                        detail = " · ".join(labels) or "计划暂未安排时间"
                    previews.append(
                        ActionProposalService._review_item(
                            title=task_title,
                            detail=detail,
                            time_label="当前安排",
                            proposed_time_label="计划安排",
                            start_at=task.planned_start_at
                            if task_title != "任务详情暂不可用"
                            else None,
                            end_at=task.planned_end_at
                            if task_title != "任务详情暂不可用"
                            else None,
                            proposed_start_at=item.get("start_at") if state == "placed" else None,
                            proposed_end_at=item.get("end_at") if state == "placed" else None,
                        )
                    )
                result.update(
                    {
                        "action_summary": (
                            f"将应用这份任务计划，涉及 {len(affected_task_ids)} 个任务。"
                        ),
                        "review_items": previews,
                        "review_complete": (
                            task_details_complete
                            and len(previews) == len(plan_items)
                            and plan.status == SchedulePlanStatus.DRAFT
                            and plan.expires_at > timezone.now()
                        ),
                    }
                )
        elif tool_name == "apply_local_replan":
            try:
                policy = AutomationPolicyService.get(
                    user=user,
                    policy_id=UUID(str(args.get("policy_id", ""))),
                )
                raw_ids = args.get("movable_task_ids")
                task_ids = (
                    [UUID(str(value)) for value in raw_ids] if isinstance(raw_ids, list) else []
                )
                preview = AdaptivePlanningService.preview_local_replan(
                    user=user,
                    blocked_start=DATETIME_ADAPTER.validate_python(args.get("blocked_start")),
                    blocked_end=DATETIME_ADAPTER.validate_python(args.get("blocked_end")),
                    movable_task_ids=task_ids,
                    horizon_end=DATETIME_ADAPTER.validate_python(args.get("horizon_end")),
                )
            except (ObjectDoesNotExist, TypeError, ValueError, ValidationError):
                result["action_summary"] = "将尝试重新安排所选任务；具体安排暂时无法预览。"
                result["review_complete"] = False
            else:
                previews = []
                task_details_complete = True
                for item in preview.moved_items:
                    try:
                        task = TaskService.get_task(user=user, task_id=UUID(str(item["task_id"])))
                        task_title = task.title
                    except (ObjectDoesNotExist, KeyError, TypeError, ValueError):
                        task_title = "任务详情暂不可用"
                        task_details_complete = False
                    moved = item.get("state") == "moved"
                    previews.append(
                        ActionProposalService._review_item(
                            title=task_title,
                            detail="将调整时间" if moved else "暂时找不到合适时段",
                            time_label="原计划时间",
                            start_at=item.get("from_start_at"),
                            end_at=item.get("from_end_at"),
                            proposed_start_at=item.get("to_start_at") if moved else None,
                            proposed_end_at=item.get("to_end_at") if moved else None,
                        )
                    )
                moved_count = int(preview.stability_cost["moved_count"])
                result.update(
                    {
                        "action_summary": (
                            f"按「{policy.name}」检查后，可调整 {moved_count} 个任务；"
                            f"{int(preview.stability_cost['unplaced_count'])} 个任务暂时"
                            "找不到合适时段。"
                        ),
                        "review_items": [
                            ActionProposalService._review_item(
                                title="受影响时段",
                                detail="这段时间内的任务需要重新安排",
                                time_label="受影响时段",
                                start_at=preview.blocked_start,
                                end_at=preview.blocked_end,
                            ),
                            *previews,
                        ],
                        "blocked_start_at": preview.blocked_start.isoformat(),
                        "blocked_end_at": preview.blocked_end.isoformat(),
                        "review_complete": task_details_complete,
                    }
                )
        elif tool_name == "reschedule_task":
            try:
                task = TaskService.get_task(user=user, task_id=UUID(str(args.get("task_id", ""))))
            except (ObjectDoesNotExist, TypeError, ValueError):
                result["action_summary"] = "将调整一项任务的时间；任务详情暂不可用。"
            else:
                result.update(
                    {
                        "action_summary": f"将调整任务「{task.title}」的计划时间。",
                        "review_items": [
                            ActionProposalService._review_item(
                                title=task.title,
                                detail="原计划时间 → 新计划时间",
                                time_label="原计划时间",
                                start_at=task.planned_start_at,
                                end_at=task.planned_end_at,
                                proposed_start_at=args.get("planned_start_at"),
                                proposed_end_at=args.get("planned_end_at"),
                            )
                        ],
                        "review_complete": True,
                    }
                )
        elif tool_name in {"update_reminder", "set_reminder_target", "cancel_reminder"}:
            try:
                reminder = ReminderService.get_reminder(
                    user=user,
                    reminder_id=UUID(str(args.get("reminder_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                if tool_name != "cancel_reminder":
                    result["action_summary"] = "将修改一项提醒；提醒详情暂不可用。"
                result["review_complete"] = False
            else:
                detail_parts = [
                    f"当前状态：{REMINDER_STATUS_LABELS.get(reminder.status, reminder.status)}"
                ]
                start_at = reminder.trigger_at
                proposed_start_at = None
                review_complete = True
                if tool_name == "update_reminder":
                    current_title = reminder.title
                    proposed_title = str(args.get("title") or current_title)
                    if proposed_title != current_title:
                        detail_parts.append(f"标题：{current_title} → {proposed_title}")
                        result["action_summary"] = f"将修改提醒「{current_title}」。"
                    if args.get("trigger_at") is not None:
                        detail_parts.append("提醒时间将调整")
                        proposed_start_at = args["trigger_at"]
                    if args.get("timezone") is not None:
                        detail_parts.append(f"时区：{reminder.timezone} → {args['timezone']}")
                    if args.get("channel") is not None:
                        old_channel = REMINDER_CHANNEL_LABELS.get(
                            reminder.channel, reminder.channel
                        )
                        new_channel = REMINDER_CHANNEL_LABELS.get(
                            str(args["channel"]), str(args["channel"])
                        )
                        detail_parts.append(f"通知方式：{old_channel} → {new_channel}")
                    result.setdefault("action_summary", f"将修改提醒「{current_title}」。")
                    result["review_items"] = [
                        ActionProposalService._review_item(
                            title=proposed_title,
                            detail="；".join(detail_parts),
                            time_label="当前提醒时间",
                            proposed_time_label="调整为",
                            start_at=start_at,
                            proposed_start_at=proposed_start_at,
                        )
                    ]
                    review_complete = bool(
                        args.get("title") is not None
                        or args.get("trigger_at") is not None
                        or args.get("timezone") is not None
                        or args.get("channel") is not None
                    )
                elif tool_name == "set_reminder_target":
                    target_names = {
                        "custom": "独立提醒",
                        "calendar_event": "日程",
                        "task": "任务",
                    }
                    proposed_target_type = str(args.get("target_type", reminder.target_type))

                    def target_description(target_type: str, target_id: Any) -> tuple[str, bool]:
                        label = target_names.get(target_type, "关联对象")
                        if target_type == "custom" and target_id is None:
                            return "独立提醒", True
                        if target_id is None:
                            return f"{label}（详情暂不可用）", False
                        try:
                            if target_type == "task":
                                target_title = TaskService.get_task(
                                    user=user, task_id=UUID(str(target_id))
                                ).title
                            else:
                                target_title = EventService.get_event(
                                    user=user, event_id=UUID(str(target_id))
                                ).title
                            return f"{label}「{target_title}」", True
                        except (ObjectDoesNotExist, TypeError, ValueError):
                            return f"{label}（详情暂不可用）", False

                    current_target, current_target_complete = target_description(
                        reminder.target_type, reminder.target_id
                    )
                    proposed_target_id = (
                        None
                        if proposed_target_type == "custom"
                        else args.get("target_id", reminder.target_id)
                    )
                    proposed_target, proposed_target_complete = target_description(
                        proposed_target_type,
                        proposed_target_id,
                    )
                    detail_parts.append(f"关联对象：{current_target} → {proposed_target}")
                    result["action_summary"] = f"将更改提醒「{reminder.title}」关联的对象。"
                    result["review_items"] = [
                        ActionProposalService._review_item(
                            title=reminder.title,
                            detail="；".join(detail_parts),
                            time_label="当前提醒时间",
                            start_at=start_at,
                        )
                    ]
                    review_complete = current_target_complete and proposed_target_complete
                else:
                    result["action_summary"] = (
                        f"将取消提醒「{reminder.title}」，之后不再按计划通知。"
                    )
                    result["review_items"] = [
                        ActionProposalService._review_item(
                            title=reminder.title,
                            detail="；".join(detail_parts),
                            time_label="当前提醒时间",
                            start_at=start_at,
                            proposed_start_at=proposed_start_at,
                        )
                    ]
                    result["review_complete"] = True
                if tool_name != "cancel_reminder":
                    result["review_complete"] = review_complete
        elif tool_name in {
            "remember_time_preference",
            "update_time_preference",
            "forget_time_preference",
        }:
            result["action_summary"] = "将更新一项已选定的时间偏好。"
        elif tool_name == "create_event":
            result["action_summary"] = f"将创建日程「{title or '未命名日程'}」。"
        elif tool_name == "create_recurring_event":
            result["action_summary"] = (
                f"将创建 {args.get('occurrence_count', '多')} 次重复日程"
                f"「{title or '未命名日程'}」。"
            )
        elif tool_name == "create_event_batch":
            operations = args.get("operations")
            count = len(operations) if isinstance(operations, list) else 0
            result["action_summary"] = f"将创建 {count} 项日程。"
        elif tool_name == "mutate_events":
            operations = args.get("operations")
            count = len(operations) if isinstance(operations, list) else 0
            result["action_summary"] = f"将批量处理 {count} 项日程变更。"
        elif tool_name == "update_event":
            result["action_summary"] = "将修改一项已有日程。"
        elif tool_name == "cancel_event":
            result["action_summary"] = "将取消一项已有日程。"
        return result

    @staticmethod
    def _display_context(
        *,
        run: AgentRun,
        tool_name: str,
        args: dict[str, Any],
        allowed_decisions: Any,
        position: int,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "allowed_decisions": allowed_decisions,
            "position": position,
            "action_title": ACTION_TITLES.get(tool_name, "需要你确认的操作"),
            "action_summary": "请核对下方显示的变化，再决定是否继续。",
            "conflict_action": CONFLICT_ACTION_LABELS.get(tool_name, "继续"),
            "review_items": [],
            "review_complete": False,
            "object_name": str(args.get("title", "")),
            "impact_scope": "One high-risk operation",
            "proposed_start_at": args.get("start_at"),
            "proposed_end_at": args.get("end_at"),
            "is_recurring": bool(args.get("recurrence_rule")),
            "participants": args.get("participants", []),
            "reminder_settings": args.get("reminders", []),
            "conflicts": [],
            "run_anchor_at": run.anchor_at.isoformat(),
            "run_timezone": run.anchor_timezone,
        }
        context.update(
            ActionProposalService._action_review_context(
                user=run.conversation.user,
                tool_name=tool_name,
                args=args,
            )
        )
        if tool_name in {
            "remember_time_preference",
            "update_time_preference",
            "forget_time_preference",
        }:
            from apps.time_memory.models import SemanticMemory, SemanticMemoryStatus

            target = None
            if tool_name == "remember_time_preference":
                category = str(args.get("category", ""))
                key = "_".join(str(args.get("key", "")).strip().casefold().split())
                target = SemanticMemory.objects.filter(
                    user=run.conversation.user,
                    category=category,
                    key=key,
                    status=SemanticMemoryStatus.ACTIVE,
                ).first()
            else:
                try:
                    memory_id = UUID(str(args.get("memory_id", "")))
                except ValueError:
                    memory_id = None
                if memory_id is not None:
                    target = SemanticMemory.objects.filter(
                        pk=memory_id,
                        user=run.conversation.user,
                        status=SemanticMemoryStatus.ACTIVE,
                    ).first()
            context.update(
                {
                    "impact_scope": "One long-term time preference",
                    "object_name": target.key if target is not None else str(args.get("key", "")),
                    "memory_category": target.category
                    if target is not None
                    else str(args.get("category", "")),
                    "memory_target_id": str(target.pk) if target is not None else None,
                    "memory_target_version": target.version if target is not None else None,
                    "memory_target_value": target.value if target is not None else None,
                    "proposed_memory_value": args.get("value"),
                }
            )
            category = context["memory_category"]
            key = str(context["object_name"] or "未命名偏好")
            category_label = MEMORY_CATEGORY_LABELS.get(str(category), "时间偏好")
            current_value = context.get("memory_target_value")
            proposed_value = context.get("proposed_memory_value")
            if tool_name == "remember_time_preference":
                context["action_summary"] = (
                    f"将保存一项{category_label}「{key}」，供之后的安排参考。"
                )
                detail = f"准备保存：{ActionProposalService._display_value(proposed_value)}"
            elif tool_name == "update_time_preference":
                context["action_summary"] = f"将修改{category_label}「{key}」，供之后的安排参考。"
                detail = (
                    f"当前：{ActionProposalService._display_value(current_value)}；"
                    f"修改为：{ActionProposalService._display_value(proposed_value)}"
                )
            else:
                context["action_summary"] = (
                    f"将删除{category_label}「{key}」，之后的安排不再参考它。"
                )
                detail = f"当前保存：{ActionProposalService._display_value(current_value)}"
            context["review_items"] = [{"title": key, "detail": detail}]
            context["review_complete"] = (
                tool_name == "remember_time_preference" or target is not None
            )
            return context
        if tool_name == "cancel_event":
            try:
                event = EventService.get_event(
                    user=run.conversation.user,
                    event_id=UUID(str(args.get("event_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                context["target_lookup"] = "unavailable"
                return context
            context.update(
                {
                    "target_lookup": "completed",
                    "object_name": event.title,
                    "impact_scope": "Cancels one existing calendar event",
                    "proposed_start_at": event.start_at.isoformat(),
                    "proposed_end_at": event.end_at.isoformat(),
                    "current_status": event.status,
                    "current_version": event.version,
                    "is_recurring": bool(event.recurrence_rule),
                    "action_summary": f"将取消日程「{event.title}」，并保留其历史记录。",
                    "review_items": [
                        {
                            "title": event.title,
                            "detail": "当前日程",
                            "time_label": "日程时间",
                            "start_at": event.start_at.isoformat(),
                            "end_at": event.end_at.isoformat(),
                        }
                    ],
                    "review_complete": True,
                }
            )
            return context
        if tool_name == "cancel_reminder":
            try:
                reminder = ReminderService.get_reminder(
                    user=run.conversation.user,
                    reminder_id=UUID(str(args.get("reminder_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                context["target_lookup"] = "unavailable"
                return context
            context.update(
                {
                    "target_lookup": "completed",
                    "object_name": reminder.title,
                    "impact_scope": "Cancels one pending reminder",
                    "proposed_start_at": reminder.trigger_at.isoformat(),
                    "current_status": reminder.status,
                    "action_summary": f"将取消提醒「{reminder.title}」，之后不再按计划通知。",
                    "review_items": [
                        {
                            "title": reminder.title,
                            "detail": (
                                "当前状态："
                                f"{REMINDER_STATUS_LABELS.get(reminder.status, reminder.status)}"
                            ),
                            "time_label": "提醒时间",
                            "start_at": reminder.trigger_at.isoformat(),
                        }
                    ],
                    "review_complete": True,
                }
            )
            return context
        if tool_name == "cancel_task":
            try:
                task = TaskService.get_task(
                    user=run.conversation.user,
                    task_id=UUID(str(args.get("task_id", ""))),
                )
            except (ObjectDoesNotExist, TypeError, ValueError):
                context["target_lookup"] = "unavailable"
                return context
            context.update(
                {
                    "target_lookup": "completed",
                    "object_name": task.title,
                    "impact_scope": "Cancels one active task without deleting it",
                    "proposed_start_at": (
                        task.planned_start_at.isoformat() if task.planned_start_at else None
                    ),
                    "proposed_end_at": (
                        task.planned_end_at.isoformat() if task.planned_end_at else None
                    ),
                    "due_at": task.due_at.isoformat() if task.due_at else None,
                    "current_status": task.status,
                    "action_summary": f"将取消任务「{task.title}」，任务记录会保留。",
                    "review_items": [
                        {
                            "title": task.title,
                            "detail": (
                                f"当前状态：{TASK_STATUS_LABELS.get(task.status, task.status)}"
                            ),
                            "time_label": "任务安排",
                            "start_at": task.planned_start_at.isoformat()
                            if task.planned_start_at
                            else None,
                            "end_at": task.planned_end_at.isoformat()
                            if task.planned_end_at
                            else None,
                            "due_at": task.due_at.isoformat() if task.due_at else None,
                        }
                    ],
                    "review_complete": True,
                }
            )
            return context
        if tool_name == "apply_local_replan":
            movable_ids = args.get("movable_task_ids", [])
            context.update(
                {
                    "impact_scope": f"Moves up to {len(movable_ids)} explicitly selected tasks",
                    "blocked_start_at": args.get("blocked_start"),
                    "blocked_end_at": args.get("blocked_end"),
                    "movable_task_ids": movable_ids,
                    "automation_policy_id": args.get("policy_id"),
                    "operation_id": args.get("operation_id"),
                }
            )
            return context
        if tool_name == "create_recurring_event":
            return ActionProposalService._recurring_event_display_context(
                context=context,
                user=run.conversation.user,
                args=args,
            )
        if tool_name not in {"create_event", "update_event", "create_event_batch", "mutate_events"}:
            return context
        if tool_name == "mutate_events":
            return ActionProposalService._mutation_event_display_context(
                context=context,
                user=run.conversation.user,
                args=args,
            )
        if tool_name == "create_event_batch":
            return ActionProposalService._batch_event_display_context(
                context=context,
                user=run.conversation.user,
                args=args,
            )
        if tool_name == "update_event":
            return ActionProposalService._update_event_display_context(
                context=context,
                user=run.conversation.user,
                args=args,
            )
        context["impact_scope"] = "Creates one confirmed event on the user's local calendar"
        try:
            start_at = DATETIME_ADAPTER.validate_python(args.get("start_at"))
            end_at = DATETIME_ADAPTER.validate_python(args.get("end_at"))
            preview = EventService.preview_event_change(
                user=run.conversation.user,
                start_at=start_at,
                end_at=end_at,
            )
        except (ValidationError, ValueError, TypeError):
            context["conflict_check"] = "unavailable_until_arguments_are_valid"
            return context
        context["conflict_check"] = "completed"
        context["conflicts"] = [conflict.as_dict() for conflict in preview.conflicts]
        context["action_summary"] = f"将创建日程「{args.get('title') or '未命名日程'}」。"
        context["review_items"] = [
            ActionProposalService._review_item(
                title=str(args.get("title") or "未命名日程"),
                detail="新日程",
                proposed_time_label="日程时间",
                proposed_start_at=start_at,
                proposed_end_at=end_at,
            )
        ]
        context["review_complete"] = bool(args.get("title"))
        return context

    @staticmethod
    def _resolve_event_time(
        *,
        context: dict[str, Any],
        value: object,
    ) -> Any:
        return EventTemporalResolutionService.resolve_value(
            anchor_at=DATETIME_ADAPTER.validate_python(context.get("run_anchor_at")),
            timezone=str(context.get("run_timezone")),
            value=value,
        )

    @staticmethod
    def _recurring_event_display_context(
        *,
        context: dict[str, Any],
        user: User,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            raw_occurrence_count = args.get("occurrence_count")
            if not isinstance(raw_occurrence_count, int | str):
                raise TypeError
            resolution = ActionProposalService._resolve_event_time(
                context=context,
                value=args.get("time"),
            )
            windows = EventSeriesService.preview_occurrence_windows(
                start_at=resolution.start_at,
                end_at=resolution.end_at,
                frequency=str(args.get("frequency")),
                interval=int(args.get("interval", 1)),
                occurrence_count=int(raw_occurrence_count),
            )
        except (ValidationError, ValueError, TypeError):
            context["conflict_check"] = "unavailable_until_arguments_are_valid"
            return context

        conflicts: list[dict[str, Any]] = []
        occurrences: list[dict[str, Any]] = []
        for index, (start_at, end_at) in enumerate(windows, start=1):
            preview = EventService.preview_event_change(
                user=user,
                start_at=start_at,
                end_at=end_at,
            )
            occurrence_conflicts = [item.as_dict() for item in preview.conflicts]
            occurrences.append(
                {
                    "index": index,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "conflicts": occurrence_conflicts,
                }
            )
            conflicts.extend({"occurrence_index": index, **item} for item in occurrence_conflicts)
        context.update(
            {
                "object_name": str(args.get("title", "")),
                "impact_scope": f"Creates {len(occurrences)} recurring calendar events",
                "is_recurring": True,
                "occurrences": occurrences,
                "conflict_check": "completed",
                "conflicts": conflicts,
                "action_summary": (
                    f"将创建 {len(occurrences)} 次重复日程「{args.get('title') or '未命名日程'}」。"
                ),
                "review_items": [
                    ActionProposalService._review_item(
                        title=str(args.get("title") or "未命名日程"),
                        detail="首次日程",
                        proposed_time_label="首次安排",
                        proposed_start_at=occurrences[0]["start_at"] if occurrences else None,
                        proposed_end_at=occurrences[0]["end_at"] if occurrences else None,
                    )
                ]
                if occurrences
                else [],
                "review_complete": bool(occurrences and args.get("title")),
            }
        )
        if occurrences:
            context["proposed_start_at"] = occurrences[0]["start_at"]
            context["proposed_end_at"] = occurrences[0]["end_at"]
        return context

    @staticmethod
    def _update_event_display_context(
        *,
        context: dict[str, Any],
        user: User,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            event = EventService.get_event(user=user, event_id=UUID(str(args.get("event_id", ""))))
            start_at = DATETIME_ADAPTER.validate_python(args.get("start_at") or event.start_at)
            end_at = DATETIME_ADAPTER.validate_python(args.get("end_at") or event.end_at)
            preview = EventService.preview_event_change(
                user=user,
                start_at=start_at,
                end_at=end_at,
                exclude_event_id=event.pk,
            )
        except (ObjectDoesNotExist, ValidationError, ValueError, TypeError):
            context["conflict_check"] = "unavailable_until_target_and_arguments_are_valid"
            return context
        context.update(
            {
                "target_lookup": "completed",
                "object_name": str(args.get("title") or event.title),
                "impact_scope": "Updates one existing calendar event",
                "proposed_start_at": start_at.isoformat(),
                "proposed_end_at": end_at.isoformat(),
                "current_version": event.version,
                "stale_targets": (
                    [
                        {
                            "event_id": str(event.pk),
                            "expected_version": args.get("expected_version"),
                            "current_version": event.version,
                            "title": event.title,
                        }
                    ]
                    if args.get("expected_version") != event.version
                    else []
                ),
                "conflict_check": "completed",
                "conflicts": [conflict.as_dict() for conflict in preview.conflicts],
                "action_summary": f"将把日程「{event.title}」调整到新时间。",
                "review_items": [
                    ActionProposalService._review_item(
                        title=str(args.get("title") or event.title),
                        detail="查看原安排与调整后的时间",
                        time_label="原安排",
                        proposed_time_label="调整为",
                        start_at=event.start_at,
                        end_at=event.end_at,
                        proposed_start_at=start_at,
                        proposed_end_at=end_at,
                    )
                ],
                "review_complete": True,
            }
        )
        return context

    @staticmethod
    def _batch_event_display_context(
        *,
        context: dict[str, Any],
        user: User,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        events = args.get("events")
        if not isinstance(events, list) or not events:
            context["conflict_check"] = "unavailable_until_arguments_are_valid"
            return context
        all_conflicts: list[dict[str, Any]] = []
        try:
            for index, event in enumerate(events):
                if not isinstance(event, dict):
                    raise ValueError("event must be an object")
                preview = EventService.preview_event_change(
                    user=user,
                    start_at=DATETIME_ADAPTER.validate_python(event.get("start_at")),
                    end_at=DATETIME_ADAPTER.validate_python(event.get("end_at")),
                )
                all_conflicts.extend(
                    {"batch_index": index, **conflict.as_dict()} for conflict in preview.conflicts
                )
        except (ValidationError, ValueError, TypeError):
            context["conflict_check"] = "unavailable_until_arguments_are_valid"
            return context
        context.update(
            {
                "object_name": f"{len(events)} calendar events",
                "impact_scope": "Creates a finite batch of calendar events atomically",
                "conflict_check": "completed",
                "conflicts": all_conflicts,
                "action_summary": f"将创建 {len(events)} 项日程。",
                "review_items": [
                    ActionProposalService._review_item(
                        title=str(event.get("title") or "未命名日程"),
                        detail="新日程",
                        proposed_time_label="日程时间",
                        proposed_start_at=event.get("start_at"),
                        proposed_end_at=event.get("end_at"),
                    )
                    for event in events
                ],
                "review_complete": all(
                    isinstance(event, dict)
                    and bool(event.get("title"))
                    and event.get("start_at") is not None
                    and event.get("end_at") is not None
                    for event in events
                ),
            }
        )
        return context

    @staticmethod
    def _mutation_event_display_context(
        *,
        context: dict[str, Any],
        user: User,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        operations = args.get("operations")
        if not isinstance(operations, list) or not operations:
            context["conflict_check"] = "unavailable_until_arguments_are_valid"
            return context
        conflicts: list[dict[str, Any]] = []
        stale_targets: list[dict[str, Any]] = []
        planned_intervals: list[tuple[int, datetime, datetime, str]] = []
        resolved_operations: list[dict[str, Any]] = []
        action_labels = {
            "create": "新增",
            "update": "调整",
            "cancel": "取消",
            "link_task": "关联任务",
        }
        try:
            for index, operation in enumerate(operations):
                if not isinstance(operation, dict):
                    raise TypeError
                action = str(operation.get("action", ""))
                if action not in {"create", "update"}:
                    resolved_operation = dict(operation)
                    if action in {"cancel", "link_task"}:
                        existing_target = EventService.get_event(
                            user=user,
                            event_id=UUID(str(operation.get("event_id", ""))),
                        )
                        expected_version = operation.get("expected_version")
                        if expected_version is None:
                            raise ValueError("Event mutation requires expected_version")
                        version_stale = expected_version != existing_target.version
                        resolved_operation.update(
                            {
                                "expected_version": existing_target.version,
                                "current_version": existing_target.version,
                                "version_stale": version_stale,
                            }
                        )
                        if version_stale:
                            stale_targets.append(
                                {
                                    "operation_index": index,
                                    "event_id": str(existing_target.pk),
                                    "expected_version": expected_version,
                                    "current_version": existing_target.version,
                                    "title": existing_target.title,
                                }
                            )
                        resolved_operation["display_title"] = existing_target.title
                        resolved_operation["existing_start_at"] = (
                            existing_target.start_at.isoformat()
                        )
                        resolved_operation["existing_end_at"] = existing_target.end_at.isoformat()
                        if action == "link_task" and operation.get("task_id"):
                            task = TaskService.get_task(
                                user=user,
                                task_id=UUID(str(operation["task_id"])),
                            )
                            resolved_operation["display_task_title"] = task.title
                    resolved_operations.append(resolved_operation)
                    continue
                event_id = operation.get("event_id")
                existing_event = (
                    EventService.get_event(user=user, event_id=UUID(str(event_id)))
                    if operation.get("action") == "update"
                    else None
                )
                if action == "update":
                    expected_version = operation.get("expected_version")
                    if expected_version is None or existing_event is None:
                        raise ValueError("Event update requires event_id and expected_version")
                    version_stale = expected_version != existing_event.version
                    if version_stale:
                        stale_targets.append(
                            {
                                "operation_index": index,
                                "event_id": str(existing_event.pk),
                                "expected_version": expected_version,
                                "current_version": existing_event.version,
                                "title": existing_event.title,
                            }
                        )
                if operation.get("time") is None:
                    resolved_operation = dict(operation)
                    resolved_operation["display_title"] = str(
                        operation.get("title") or (existing_event.title if existing_event else "")
                    )
                    if existing_event is not None:
                        resolved_operation.update(
                            {
                                "expected_version": existing_event.version,
                                "current_version": existing_event.version,
                                "version_stale": version_stale,
                            }
                        )
                        resolved_operation["existing_start_at"] = (
                            existing_event.start_at.isoformat()
                        )
                        resolved_operation["existing_end_at"] = existing_event.end_at.isoformat()
                    resolved_operations.append(resolved_operation)
                    continue
                resolution = ActionProposalService._resolve_event_time(
                    context=context,
                    value=operation.get("time"),
                )
                start_at = resolution.start_at
                end_at = resolution.end_at
                resolved_operation = dict(operation)
                if existing_event is not None:
                    resolved_operation.update(
                        {
                            "expected_version": existing_event.version,
                            "current_version": existing_event.version,
                            "version_stale": version_stale,
                        }
                    )
                    resolved_operation["display_title"] = str(
                        operation.get("title") or existing_event.title
                    )
                    resolved_operation["existing_start_at"] = existing_event.start_at.isoformat()
                    resolved_operation["existing_end_at"] = existing_event.end_at.isoformat()
                else:
                    resolved_operation["display_title"] = str(operation.get("title") or "")
                resolved_operation["time"] = {
                    "kind": "absolute",
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                }
                resolved_operations.append(resolved_operation)
                preview = EventService.preview_event_change(
                    user=user,
                    start_at=start_at,
                    end_at=end_at,
                    exclude_event_id=existing_event.pk if existing_event else None,
                )
                cancelled_ids = {
                    str(previous.get("event_id"))
                    for previous in operations[:index]
                    if isinstance(previous, dict) and previous.get("action") == "cancel"
                }
                conflicts.extend(
                    {"operation_index": index, **item.as_dict()}
                    for item in preview.conflicts
                    if str(item.event_id) not in cancelled_ids
                )
                for prior_index, prior_start, prior_end, prior_title in planned_intervals:
                    if prior_start < end_at and prior_end > start_at:
                        conflicts.append(
                            {
                                "operation_index": index,
                                "conflicting_operation_index": prior_index,
                                "title": prior_title,
                                "start_at": prior_start.isoformat(),
                                "end_at": prior_end.isoformat(),
                                "overlap_start_at": max(start_at, prior_start).isoformat(),
                                "overlap_end_at": min(end_at, prior_end).isoformat(),
                                "source": "same_mutation_batch",
                            }
                        )
                planned_intervals.append(
                    (
                        index,
                        start_at,
                        end_at,
                        str(
                            operation.get("title")
                            or (existing_event.title if existing_event else "Untitled event")
                        ),
                    )
                )
        except (ObjectDoesNotExist, ValidationError, ValueError, TypeError):
            context["conflict_check"] = "unavailable_until_arguments_are_valid"
            return context
        context.update(
            {
                "object_name": f"{len(operations)} calendar operations",
                "impact_scope": "Applies a calendar mutation batch atomically",
                "conflict_check": "completed",
                "conflicts": conflicts,
                "stale_targets": stale_targets,
                "resolved_operations": resolved_operations,
                "action_summary": f"将批量处理 {len(operations)} 项日程变更。",
                "review_items": [
                    ActionProposalService._review_item(
                        title=str(
                            operation.get("display_title")
                            or operation.get("title")
                            or "日程详情暂不可用"
                        ),
                        detail=(
                            f"{action_labels.get(str(operation.get('action')), '调整')}"
                            + (
                                f"到任务「{operation['display_task_title']}」"
                                if operation.get("display_task_title")
                                else ""
                            )
                        ),
                        time_label="原安排",
                        proposed_time_label="调整为",
                        start_at=operation.get("existing_start_at"),
                        end_at=operation.get("existing_end_at"),
                        proposed_start_at=(
                            operation.get("time", {}).get("start_at")
                            if isinstance(operation.get("time"), dict)
                            else None
                        ),
                        proposed_end_at=(
                            operation.get("time", {}).get("end_at")
                            if isinstance(operation.get("time"), dict)
                            else None
                        ),
                    )
                    for operation in resolved_operations
                ],
                "review_complete": len(resolved_operations) == len(operations)
                and all(bool(operation.get("display_title")) for operation in resolved_operations),
            }
        )
        first_time = next(
            (
                operation.get("time")
                for operation in resolved_operations
                if isinstance(operation.get("time"), dict)
            ),
            None,
        )
        if isinstance(first_time, dict):
            context["proposed_start_at"] = first_time["start_at"]
            context["proposed_end_at"] = first_time["end_at"]
        return context

    @staticmethod
    def list(*, user: User, status: str | None = None) -> list[ActionProposal]:
        ActionProposalService.expire_due(user=user)
        queryset = ActionProposal.objects.filter(user=user).select_related(
            "conversation", "agent_run"
        )
        if status:
            queryset = queryset.filter(status=status)
        return list(queryset)

    @staticmethod
    def get(*, user: User, proposal_id: UUID) -> ActionProposal:
        ActionProposalService.expire_due(user=user, proposal_id=proposal_id)
        return ActionProposal.objects.select_related("conversation", "agent_run").get(
            pk=proposal_id,
            user=user,
        )

    @staticmethod
    @transaction.atomic
    def decide(
        *,
        user: User,
        proposal_id: UUID,
        expected_version: int,
        decision: Literal["approve", "edit", "reject"],
        decision_idempotency_key: UUID,
        edited_payload: dict[str, Any] | None = None,
        reason: str = "",
    ) -> ProposalDecision:
        replay = ActionProposal.objects.filter(
            decision_idempotency_key=decision_idempotency_key,
            user=user,
        ).first()
        if replay is not None:
            if replay.pk != proposal_id or replay.decision_type != decision:
                raise ProposalConflictError("Decision idempotency key is already in use")
            return ProposalDecision(replay, ActionProposalService.resume_ready(replay.agent_run_id))

        proposal = ActionProposal.objects.select_for_update().get(pk=proposal_id, user=user)
        now = timezone.now()
        if proposal.status == ActionProposalStatus.AWAITING_APPROVAL and proposal.expires_at <= now:
            proposal.status = ActionProposalStatus.EXPIRED
            proposal.version += 1
            proposal.save(update_fields=["status", "version", "updated_at"])
            return ProposalDecision(proposal, False)
        if proposal.status != ActionProposalStatus.AWAITING_APPROVAL:
            raise ProposalConflictError("Action proposal is no longer awaiting approval")
        if proposal.version != expected_version:
            raise ProposalConflictError(
                "Action proposal version conflict: "
                f"expected {expected_version}, current {proposal.version}"
            )

        allowed = proposal.display_context.get("allowed_decisions", [])
        if decision not in allowed:
            raise ProposalConflictError(f"Decision {decision} is not allowed")

        def keep_pending_for_review(
            refreshed_context: dict[str, Any],
            *,
            refreshed_payload: dict[str, Any] | None = None,
        ) -> ProposalDecision:
            proposal.display_context = refreshed_context
            proposal.decision_type = decision
            proposal.decision_reason = reason.strip()
            proposal.decision_idempotency_key = decision_idempotency_key
            if refreshed_payload is not None:
                proposal.action_payload = refreshed_payload
            proposal.version += 1
            update_fields = [
                "display_context",
                "decision_type",
                "decision_reason",
                "decision_idempotency_key",
                "version",
                "updated_at",
            ]
            if refreshed_payload is not None:
                update_fields.append("action_payload")
            proposal.save(update_fields=update_fields)
            return ProposalDecision(proposal, False)

        if decision == "approve":
            refreshed_display_context = ActionProposalService._display_context(
                run=proposal.agent_run,
                tool_name=proposal.action_type,
                args=proposal.action_payload,
                allowed_decisions=allowed,
                position=int(proposal.display_context.get("position", 0)),
            )
            if not _is_actionable_review_context(refreshed_display_context):
                return keep_pending_for_review(refreshed_display_context)
            refreshed_payload = _refresh_target_versions(
                tool_name=proposal.action_type,
                args=proposal.action_payload,
                display_context=refreshed_display_context,
            )
            if refreshed_payload is not None:
                refreshed_display_context["review_notice"] = (
                    "计划在提出审批后已有更新。已载入当前版本，请重新核对后再次确认。"
                    if proposal.action_type == "apply_schedule_plan"
                    else "这项日程在提出审批后已有更新。已载入最新安排，请重新核对后再次确认。"
                )
                return keep_pending_for_review(
                    refreshed_display_context,
                    refreshed_payload=refreshed_payload,
                )
            proposal.display_context = refreshed_display_context
        if decision == "edit":
            if not isinstance(edited_payload, dict) or not edited_payload:
                raise ValueError("edited_payload is required for edit decisions")
            refreshed_display_context = ActionProposalService._display_context(
                run=proposal.agent_run,
                tool_name=proposal.action_type,
                args=edited_payload,
                allowed_decisions=allowed,
                position=int(proposal.display_context.get("position", 0)),
            )
            if refreshed_display_context.get("conflicts"):
                return keep_pending_for_review(refreshed_display_context)
            if not _is_actionable_review_context(refreshed_display_context):
                return keep_pending_for_review(refreshed_display_context)
            refreshed_payload = _refresh_target_versions(
                tool_name=proposal.action_type,
                args=edited_payload,
                display_context=refreshed_display_context,
            )
            if refreshed_payload is not None:
                refreshed_display_context["review_notice"] = (
                    "这项日程在编辑期间已有更新。已载入最新安排，请再次核对并调整。"
                )
                return keep_pending_for_review(
                    refreshed_display_context,
                    refreshed_payload=refreshed_payload,
                )
            proposal.action_payload = edited_payload
            proposal.display_context = refreshed_display_context
        proposal.status = (
            ActionProposalStatus.REJECTED if decision == "reject" else ActionProposalStatus.APPROVED
        )
        proposal.decision_type = decision
        proposal.decision_reason = reason.strip()
        proposal.decision_idempotency_key = decision_idempotency_key
        proposal.decided_at = now
        proposal.approved_at = now if decision != "reject" else None
        proposal.version += 1
        proposal.save()
        return ProposalDecision(proposal, ActionProposalService.resume_ready(proposal.agent_run_id))

    @staticmethod
    def resume_ready(run_id: UUID) -> bool:
        statuses = set(
            ActionProposal.objects.filter(agent_run_id=run_id, resumed_at__isnull=True).values_list(
                "status", flat=True
            )
        )
        return bool(statuses) and ActionProposalStatus.AWAITING_APPROVAL not in statuses

    @staticmethod
    def resume_payload(run_id: UUID) -> dict[str, builtins.list[dict[str, Any]]]:
        proposals = builtins.list(
            ActionProposal.objects.filter(agent_run_id=run_id, resumed_at__isnull=True).order_by(
                "created_at", "id"
            )
        )
        if not proposals or any(
            proposal.status == ActionProposalStatus.AWAITING_APPROVAL for proposal in proposals
        ):
            raise ProposalConflictError("Not all pending actions have decisions")
        decisions: builtins.list[dict[str, Any]] = []
        for proposal in proposals:
            if proposal.status == ActionProposalStatus.EXPIRED:
                decisions.append({"type": "reject", "message": "Approval expired before execution"})
            elif proposal.decision_type == "edit":
                decisions.append(
                    {
                        "type": "edit",
                        "edited_action": {
                            "name": proposal.action_type,
                            "args": proposal.action_payload,
                        },
                    }
                )
            elif proposal.decision_type == "reject":
                decisions.append(
                    {
                        "type": "reject",
                        "message": proposal.decision_reason or "User rejected this action",
                    }
                )
            else:
                decisions.append({"type": "approve"})
        return {"decisions": decisions}

    @staticmethod
    def mark_resumed(run_id: UUID) -> None:
        ActionProposal.objects.filter(
            agent_run_id=run_id,
            resumed_at__isnull=True,
        ).exclude(status=ActionProposalStatus.AWAITING_APPROVAL).update(
            resumed_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def mark_executing(*, run_id: str, tool_call_id: str) -> None:
        resolved_run_id = UUID(run_id)
        ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
            status=ActionProposalStatus.APPROVED,
        ).update(status=ActionProposalStatus.EXECUTING, updated_at=timezone.now())

    @staticmethod
    @transaction.atomic
    def mark_executed(*, run_id: str, tool_call_id: str, result: Any) -> None:
        resolved_run_id = UUID(run_id)
        ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
            status__in=[ActionProposalStatus.APPROVED, ActionProposalStatus.EXECUTING],
        ).update(
            status=ActionProposalStatus.EXECUTED,
            execution_result=result,
            executed_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def mark_failed(*, run_id: str, tool_call_id: str, error: Exception) -> None:
        resolved_run_id = UUID(run_id)
        ActionProposal.objects.filter(
            agent_run_id=resolved_run_id,
            tool_call_id=tool_call_id,
            status__in=[ActionProposalStatus.APPROVED, ActionProposalStatus.EXECUTING],
        ).update(
            status=ActionProposalStatus.FAILED,
            error=f"{type(error).__name__}: {error}"[:4000],
            updated_at=timezone.now(),
        )

    @staticmethod
    def expire_due(*, user: User, proposal_id: UUID | None = None) -> int:
        queryset = ActionProposal.objects.filter(
            user=user,
            status=ActionProposalStatus.AWAITING_APPROVAL,
            expires_at__lte=timezone.now(),
        )
        if proposal_id is not None:
            queryset = queryset.filter(pk=proposal_id)
        return queryset.update(
            status=ActionProposalStatus.EXPIRED,
            version=models.F("version") + 1,
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def expire_due_runs(*, now: datetime | None = None) -> set[UUID]:
        current_time = now or timezone.now()
        due = list(
            ActionProposal.objects.select_for_update()
            .filter(
                status=ActionProposalStatus.AWAITING_APPROVAL,
                expires_at__lte=current_time,
            )
            .values_list("pk", "agent_run_id")
        )
        if not due:
            return set()
        ActionProposal.objects.filter(pk__in=[proposal_id for proposal_id, _ in due]).update(
            status=ActionProposalStatus.EXPIRED,
            version=models.F("version") + 1,
            updated_at=current_time,
        )
        return {run_id for _, run_id in due}

from apps.agents.tool_routing import select_tool_names


def test_replan_intent_exposes_free_slot_context_tool() -> None:
    tools = select_tool_names("新增会议与已排任务冲突，请重排受影响的任务并尽量减少移动。")

    assert tools is not None
    assert "detect_schedule_disruptions" in tools
    assert "get_planning_context" in tools
    assert "get_task" in tools
    assert "reschedule_task" in tools
    assert "list_automation_policies" not in tools
    assert "apply_local_replan" not in tools


def test_automation_replan_intent_exposes_policy_tools() -> None:
    tools = select_tool_names("请使用自动化重排策略调整受影响的任务。")

    assert tools is not None
    assert "list_automation_policies" in tools
    assert "apply_local_replan" in tools

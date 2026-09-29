from apps.agents.tool_routing import select_tool_names, should_limit_to_read_tools


def test_replan_intent_exposes_free_slot_context_tool() -> None:
    tools = select_tool_names("新增会议与已排任务冲突，请重排受影响的任务并尽量减少移动。")

    assert tools is not None
    assert "detect_schedule_disruptions" in tools
    assert "get_planning_context" in tools
    assert "get_task" in tools
    assert "reschedule_task" in tools
    assert "get_current_datetime" not in tools
    assert "list_automation_policies" not in tools
    assert "apply_local_replan" not in tools


def test_automation_replan_intent_exposes_policy_tools() -> None:
    tools = select_tool_names("请使用自动化重排策略调整受影响的任务。")

    assert tools is not None
    assert "list_automation_policies" in tools
    assert "apply_local_replan" in tools


def test_explicit_task_reschedule_intent_exposes_approved_write_tool() -> None:
    tools = select_tool_names("把 Prepare review 任务改到 7 月 22 日上午十点")

    assert tools is not None
    assert "reschedule_task" in tools


def test_descriptive_calendar_create_intent_exposes_event_write_tool() -> None:
    prompts = (
        "一天后上午八点添加一个标题为八点基线的日程。",
        "两天后上午十点添加一个标题为十点新锚点的日程。",
        "下周一上午十点到十一点，帮我创建一个标题为项目周会的日程。",
    )

    for prompt in prompts:
        tools = select_tool_names(prompt)
        assert tools is not None
        assert "mutate_events" in tools


def test_explicit_memory_preference_write_intents_expose_approved_tools() -> None:
    remember_tools = select_tool_names("请记住以后周五下午不要安排会议")
    update_tools = select_tool_names("把我的专注时间改成下午")

    assert remember_tools is not None
    assert "remember_time_preference" in remember_tools
    assert not should_limit_to_read_tools("请记住以后周五下午不要安排会议")

    assert update_tools is not None
    assert "update_time_preference" in update_tools
    assert not should_limit_to_read_tools("把我的专注时间改成下午")


def test_schedule_constraints_do_not_turn_a_write_request_into_read_only() -> None:
    assert not should_limit_to_read_tools(
        "请为东京出差安排任务，不要移动已经确认的会议，也不要排周末。"
    )
    assert should_limit_to_read_tools("同步状态")
    assert should_limit_to_read_tools("只给建议，不修改日程。")


def test_planning_preview_route_matches_longer_natural_schedule_requests() -> None:
    for prompt in (
        "本周任务负荷过高，帮我把任务分散到未来两周，已有会议不动。",
        "未来三周的工作项目请按阶段安排到日程里。",
        "下周有几项任务需要计划一下，不要占用周末。",
    ):
        tools = select_tool_names(prompt)

        assert tools is not None
        assert "get_planning_context" in tools
        assert "propose_schedule_plan" in tools


def test_ordered_workflow_with_daily_constraints_is_schedule_intent() -> None:
    prompt = (
        "我想把作品集更新好再申请几个设计岗位。先挑选最近的案例，"
        "整理每个案例的过程图，再写简短说明，最后请同事给反馈。"
        "每天最多 4 小时，至少分 4 天，不排周末；案例选择后再整理过程图。"
    )

    assert not should_limit_to_read_tools(prompt)
    tools = select_tool_names(prompt)
    assert tools is not None
    assert "get_planning_context" in tools
    assert "propose_schedule_plan" in tools
    assert "list_tasks" not in tools
    assert "list_events" not in tools

    for prompt in (
        "需要完成季度预算准备：收集数据，核对差异，再整理摘要。每天最多 3 小时，至少分 3 天。",
        (
            "我报名了考试，想分几次准备口语：选好话题，录回答，再听录音。"
            "每天最多 3 小时，至少分 3 个工作日。"
        ),
    ):
        assert not should_limit_to_read_tools(prompt)
        tools = select_tool_names(prompt)
        assert tools is not None
        assert "get_planning_context" in tools
        assert "propose_schedule_plan" in tools


def test_simple_schedule_hides_optional_analysis_tools_but_keeps_them_on_intent() -> None:
    simple = select_tool_names("请帮我安排下周的课程复习计划。")
    compare = select_tool_names("请比较两种安排方案：早上学习和晚上学习，告诉我各自的优缺点。")
    estimate = select_tool_names("请帮我安排这几项任务，并先估算每项大概需要多长时间。")
    capacity = select_tool_names("请安排下周的工作，并告诉我这周还有多少可用容量。")

    assert simple is not None
    assert "propose_schedule_plan" in simple
    assert "validate_schedule_plan" in simple
    assert "compare_schedule_plans" not in simple
    assert "recommend_task_duration" not in simple
    assert "get_capacity_forecast" not in simple

    assert compare is not None
    assert "compare_schedule_plans" in compare
    assert estimate is not None
    assert "recommend_task_duration" in estimate
    assert capacity is not None
    assert "get_capacity_forecast" in capacity


def test_runtime_anchor_replaces_clock_tool_for_planning_but_keeps_explicit_clock_intent() -> None:
    planning = select_tool_names("请帮我安排下周的课程复习计划。")
    overview = select_tool_names("今天有什么安排？")
    exact_clock = select_tool_names("现在几点了？")

    assert planning is not None
    assert "get_current_datetime" not in planning
    assert overview is not None
    assert {"list_events", "list_tasks"}.issubset(overview)
    assert "get_current_datetime" not in overview
    assert exact_clock == frozenset({"get_current_datetime"})


def test_duration_and_fit_question_routes_capacity_without_unrelated_integrations() -> None:
    tools = select_tool_names("How long will this take, and can it fit today?")

    assert tools is not None
    assert "recommend_task_duration" in tools
    assert "get_capacity_forecast" in tools
    assert "get_task_execution_summary" in tools
    assert "list_calendar_sync_status" not in tools

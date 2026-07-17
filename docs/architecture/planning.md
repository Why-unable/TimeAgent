# 冲突检测与空闲时间搜索

时间区间统一采用半开语义 `[start_at, end_at)`，因此一个安排在另一个安排结束时开始不算
冲突。冲突检测按用户隔离，只考虑 tentative/confirmed 日程，并可排除正在编辑的事件。

`PlanningService.find_free_slots()` 返回长度严格等于请求时长的 UTC 候选区间。搜索过程：

1. 校验查询区间为带时区 datetime 并转换为 UTC；
2. 读取用户 IANA 时区和默认工作时段，允许通过 `PlanningConstraints` 覆盖；
3. 按用户本地日期建立每日搜索窗口，正确处理 DST 日长度变化；
4. 合并重叠或相邻的忙碌区间；
5. 扣除未取消日程，以及可选的 pending/in-progress 计划任务；
6. 按确定的候选步长生成结果，并可限制星期和最大结果数。

取消日程和 completed/cancelled 任务不占用候选时间。候选评分、计划提案、REST API 和
Agent Tool 不属于 T026。

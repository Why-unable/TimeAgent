import re
from dataclasses import dataclass

from apps.tasks.models import Task

CLASSIFIER_VERSION = "deterministic-task-taxonomy-v1"

_CATEGORY_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "coding",
        (
            "code",
            "coding",
            "implement",
            "debug",
            "bug",
            "api",
            "refactor",
            "开发",
            "编码",
            "实现",
            "修复",
            "调试",
            "接口",
            "重构",
        ),
    ),
    (
        "writing",
        (
            "write",
            "draft",
            "report",
            "document",
            "proposal",
            "文档",
            "报告",
            "写作",
            "撰写",
            "总结",
            "方案",
        ),
    ),
    (
        "analysis",
        (
            "analyze",
            "analysis",
            "research",
            "investigate",
            "data",
            "分析",
            "调研",
            "研究",
            "排查",
            "数据",
        ),
    ),
    (
        "communication",
        (
            "email",
            "reply",
            "message",
            "call",
            "邮件",
            "回复",
            "沟通",
            "电话",
            "消息",
        ),
    ),
    (
        "meeting",
        (
            "meeting",
            "standup",
            "sync",
            "review meeting",
            "会议",
            "例会",
            "同步会",
            "评审会",
            "复盘会",
        ),
    ),
    (
        "planning",
        (
            "plan",
            "planning",
            "schedule",
            "roadmap",
            "计划",
            "规划",
            "排期",
            "路线图",
        ),
    ),
    (
        "administration",
        (
            "expense",
            "invoice",
            "reimburse",
            "form",
            "报销",
            "发票",
            "审批",
            "表单",
            "行政",
        ),
    ),
    (
        "learning",
        (
            "learn",
            "study",
            "read",
            "course",
            "学习",
            "阅读",
            "课程",
            "练习",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class TaskClassification:
    category: str
    confidence: float
    source: str
    matched_signals: tuple[str, ...]

    @property
    def segment(self) -> str:
        return f"semantic:{self.category}"

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "source": self.source,
            "matched_signals": list(self.matched_signals),
        }


def classify_task(task: Task) -> TaskClassification:
    """Classify task text with a fixed, auditable baseline and honest ambiguity fallback."""

    text = " ".join((task.title, task.description)).casefold()
    matches: list[tuple[str, tuple[str, ...]]] = []
    for category, markers in _CATEGORY_MARKERS:
        hit = tuple(marker for marker in markers if _contains_marker(text, marker))
        if hit:
            matches.append((category, hit))
    if not matches:
        return TaskClassification(
            category="unclassified",
            confidence=0.0,
            source=CLASSIFIER_VERSION,
            matched_signals=(),
        )
    best_count = max(len(markers) for _, markers in matches)
    best = [(category, markers) for category, markers in matches if len(markers) == best_count]
    if len(best) != 1:
        return TaskClassification(
            category="unclassified",
            confidence=0.0,
            source=f"{CLASSIFIER_VERSION}:ambiguous",
            matched_signals=tuple(marker for _, markers in best for marker in markers)[:6],
        )
    category, markers = best[0]
    return TaskClassification(
        category=category,
        confidence=min(0.85, 0.55 + 0.1 * (len(markers) - 1)),
        source=CLASSIFIER_VERSION,
        matched_signals=markers[:6],
    )


def _contains_marker(text: str, marker: str) -> bool:
    if marker.isascii():
        return re.search(rf"\b{re.escape(marker)}\b", text) is not None
    return marker in text

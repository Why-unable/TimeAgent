import re
from re import Pattern

from apps.time_memory.models import MemoryProposalOperation

_NEGATED_MEMORY_COMMAND = re.compile(
    r"(?:不要|别|无需|不用|禁止).{0,6}(?:记住|记下|记录|保存|修改|更新|删除|忘记)"
    r"|\b(?:do\s+not|don't|never)\s+(?:remember|save|update|delete|forget)\b",
    re.IGNORECASE,
)
_CREATE_COMMAND = re.compile(
    r"(?:请|帮我|替我|给我)?\s*(?:记住|记下|记一下|记录下|保存这个?偏好)"
    r"|\b(?:please\s+)?(?:remember|save)\b",
    re.IGNORECASE,
)
_UPDATE_COMMAND = re.compile(
    r"(?:修改|更新|调整).{0,16}(?:偏好|习惯|记忆|时间)"
    r"|(?:把|将).{0,20}(?:偏好|习惯|记忆|时间).{0,8}(?:改成|改为|更新为|调整为)"
    r"|\b(?:update|change|revise).{0,24}(?:preference|memory|habit)\b",
    re.IGNORECASE,
)
_DELETE_COMMAND = re.compile(
    r"(?:忘记|删除|移除|清除).{0,16}(?:偏好|习惯|记忆|这条|那条|这个|那个)"
    r"|\b(?:forget|delete|remove).{0,24}(?:preference|memory|fact)\b",
    re.IGNORECASE,
)


class ExplicitMemoryIntent:
    """Conservative proof that the current user explicitly requested memory CRUD."""

    @staticmethod
    def authorizes(*, operation: str, user_message: str) -> bool:
        message = " ".join(user_message.strip().split())
        if not message or _NEGATED_MEMORY_COMMAND.search(message):
            return False
        patterns: dict[str, Pattern[str]] = {
            MemoryProposalOperation.CREATE: _CREATE_COMMAND,
            MemoryProposalOperation.UPDATE: _UPDATE_COMMAND,
            MemoryProposalOperation.DELETE: _DELETE_COMMAND,
        }
        pattern = patterns.get(operation)
        return bool(pattern and pattern.search(message))

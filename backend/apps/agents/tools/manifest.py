"""Build the runtime tool registry from tools and declarative policy metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_core.tools import BaseTool

from apps.agents.tool_metadata import (
    DERIVE_TOOL_NAMES,
    DRAFT_TOOL_NAMES,
    HANDOFF_TOOL_NAMES,
    HITL_POLICY_METADATA,
    PACK_TOOL_NAMES,
    ToolEffect,
)

RunMode = Literal["read", "write"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool: BaseTool
    domain: str
    effect: ToolEffect
    packs: frozenset[str]
    run_modes: frozenset[RunMode]
    requires_approval: bool
    retry_safe: bool
    audit_risk_level: Literal["read", "low", "high"]
    idempotency: Literal["none", "tool_call_audit"]


def build_tool_manifest(
    source_groups: list[tuple[str, RunMode, list[BaseTool]]],
) -> tuple[ToolSpec, ...]:
    sources: dict[str, tuple[BaseTool, str, RunMode]] = {}
    for domain, mode, tools in source_groups:
        for tool in tools:
            if tool.name in sources:
                raise ValueError(f"Tool {tool.name!r} is registered in multiple source groups")
            sources[tool.name] = (tool, domain, mode)

    pack_by_name: dict[str, set[str]] = {}
    for pack, names in PACK_TOOL_NAMES.items():
        for name in names:
            pack_by_name.setdefault(name, set()).add(pack)

    missing_metadata = sources.keys() - pack_by_name.keys()
    stale_metadata = pack_by_name.keys() - sources.keys()
    if missing_metadata or stale_metadata:
        raise ValueError(
            "Tool pack metadata drift: "
            f"missing={sorted(missing_metadata)}, stale={sorted(stale_metadata)}"
        )
    stale_policies = HITL_POLICY_METADATA.keys() - sources.keys()
    if stale_policies:
        raise ValueError(f"HITL policy references unregistered tools: {sorted(stale_policies)}")

    manifest: list[ToolSpec] = []
    for name, (tool, domain, source_mode) in sources.items():
        if name in HANDOFF_TOOL_NAMES:
            effect: ToolEffect = "handoff"
        elif name in DRAFT_TOOL_NAMES:
            effect = "draft"
        elif name in DERIVE_TOOL_NAMES:
            effect = "derive"
        elif source_mode == "write":
            effect = "business_write"
        else:
            effect = "read"

        effective_mode: RunMode = "write" if effect == "draft" else source_mode
        requires_approval = name in HITL_POLICY_METADATA
        retry_safe = effect == "read"
        if requires_approval:
            audit_risk_level: Literal["read", "low", "high"] = "high"
        elif effective_mode == "write" or effect in {"derive", "draft"}:
            audit_risk_level = "low"
        else:
            audit_risk_level = "read"

        manifest.append(
            ToolSpec(
                tool=tool,
                domain=domain,
                effect=effect,
                packs=frozenset(pack_by_name[name]),
                run_modes=frozenset({effective_mode}),
                requires_approval=requires_approval,
                retry_safe=retry_safe,
                audit_risk_level=audit_risk_level,
                idempotency=(
                    "tool_call_audit" if effect in {"derive", "draft", "business_write"} else "none"
                ),
            )
        )
    return tuple(manifest)


def retry_safe_tools(manifest: tuple[ToolSpec, ...]) -> list[BaseTool]:
    return [spec.tool for spec in manifest if spec.retry_safe]

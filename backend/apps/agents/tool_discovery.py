"""Provider-independent tool discovery over the deterministic policy candidate set."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from apps.agents.configuration import ToolDiscoveryDefinition, get_agent_config
from apps.agents.tools.manifest import ToolSpec

ToolDiscoveryStrategy = Literal[
    "regex_pack", "llm_selector", "lexical_retrieval", "retrieval_plus_llm"
]


@dataclass(frozen=True, slots=True)
class ToolDiscoverySettings:
    strategy: ToolDiscoveryStrategy = "regex_pack"
    lexical_top_k: int = 8
    candidate_top_k: int = 10
    selector_max_tools: int = 6
    selector_model_alias: str | None = None
    always_include: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.lexical_top_k < 1:
            raise ValueError("lexical_top_k must be at least 1")
        if self.candidate_top_k < 1:
            raise ValueError("candidate_top_k must be at least 1")
        if self.selector_max_tools < 1:
            raise ValueError("selector_max_tools must be at least 1")
        if len(self.always_include) != len(set(self.always_include)):
            raise ValueError("always_include cannot contain duplicate tool names")


@dataclass(frozen=True, slots=True)
class ToolDiscoveryResult:
    selected_tools: frozenset[str]
    fallback_reason: str | None = None


def resolve_tool_discovery_settings(
    override: ToolDiscoverySettings | None = None,
    definition: ToolDiscoveryDefinition | None = None,
) -> ToolDiscoverySettings:
    """Convert the single runtime config block, unless an experiment injects an override."""

    if override is not None:
        return override
    configured = definition or get_agent_config().tool_discovery
    return ToolDiscoverySettings(
        strategy=configured.strategy,
        lexical_top_k=configured.lexical_top_k,
        candidate_top_k=configured.candidate_top_k,
        selector_max_tools=configured.selector_max_tools,
        selector_model_alias=configured.selector_model,
        always_include=tuple(configured.always_include),
    )


_TOKEN = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]+", re.IGNORECASE)
_ENGLISH_WORD = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


def _terms(text: str) -> list[str]:
    """Tokenize English words and overlapping Chinese bigrams/trigrams."""

    output: list[str] = []
    for span in _TOKEN.findall(text.casefold()):
        if _ENGLISH_WORD.fullmatch(span):
            output.append(span)
            continue
        if len(span) <= 3:
            output.append(span)
        for width in (2, 3):
            output.extend(span[index : index + width] for index in range(len(span) - width + 1))
    return output


def _document(spec: ToolSpec) -> str:
    tool = spec.tool
    return " ".join(
        (
            str(tool.name).replace("_", " "),
            str(tool.description or ""),
            spec.domain,
            " ".join(sorted(spec.packs)),
            " ".join(spec.search_keywords),
        )
    )


def rank_tools(
    query: str,
    *,
    tool_specs: Mapping[str, ToolSpec],
    candidate_names: frozenset[str],
    limit: int,
) -> tuple[str, ...]:
    """Rank only authorized candidates with a small in-process BM25 index."""

    names = [
        name
        for name in sorted(candidate_names)
        if name in tool_specs and tool_specs[name].searchable
    ]
    if not names:
        return ()
    query_terms = list(dict.fromkeys(_terms(query)))
    if not query_terms:
        return ()

    documents = {name: _terms(_document(tool_specs[name])) for name in names}
    lengths = {name: len(terms) for name, terms in documents.items()}
    average_length = sum(lengths.values()) / max(len(lengths), 1)
    document_frequency: dict[str, int] = {}
    for terms in documents.values():
        for term in set(terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    scores: dict[str, float] = {}
    total_documents = len(documents)
    for name, terms in documents.items():
        frequency: dict[str, int] = {}
        for term in terms:
            frequency[term] = frequency.get(term, 0) + 1
        score = 0.0
        for term in query_terms:
            term_frequency = frequency.get(term, 0)
            if not term_frequency:
                continue
            df = document_frequency.get(term, 0)
            inverse_frequency = math.log1p((total_documents - df + 0.5) / (df + 0.5))
            denominator = term_frequency + 1.2 * (
                1 - 0.75 + 0.75 * lengths[name] / max(average_length, 1.0)
            )
            score += inverse_frequency * term_frequency * 2.2 / denominator
        scores[name] = score

    # Deterministic lexical tie-break keeps repeated runs stable.
    if not any(score > 0 for score in scores.values()):
        return ()
    ranked = sorted(names, key=lambda name: (-scores[name], name))
    return tuple(ranked[:limit])


def select_discovery_candidates(
    query: str,
    *,
    tool_specs: Mapping[str, ToolSpec],
    hard_allowed_names: frozenset[str],
    lifecycle_visible_names: frozenset[str],
    settings: ToolDiscoverySettings,
    fallback_names: frozenset[str] | None = None,
) -> ToolDiscoveryResult:
    """Return model-facing candidates after request policy and lifecycle gates."""

    candidates = hard_allowed_names.intersection(lifecycle_visible_names)
    if settings.strategy == "regex_pack":
        return ToolDiscoveryResult(frozenset(candidates))
    if settings.strategy == "llm_selector":
        return ToolDiscoveryResult(frozenset(candidates))

    limit = (
        settings.candidate_top_k
        if settings.strategy == "retrieval_plus_llm"
        else settings.lexical_top_k
    )
    ranked = rank_tools(
        query,
        tool_specs=tool_specs,
        candidate_names=frozenset(candidates),
        limit=limit,
    )
    fallback_reason = None
    if ranked:
        selected = set(ranked)
    else:
        fallback_reason = "lexical_no_match"
        fallback = candidates if fallback_names is None else candidates.intersection(fallback_names)
        selected = set(fallback or candidates)
    selected.update(name for name in settings.always_include if name in candidates)
    selected.update(name for name in candidates if tool_specs[name].always_eager)
    return ToolDiscoveryResult(frozenset(selected), fallback_reason)

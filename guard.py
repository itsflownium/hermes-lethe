"""Decide which tool calls would write to long-term state, and veto them while Lethe is on."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from . import store

logger = logging.getLogger(__name__)

BLOCK_MESSAGE = (
    "Not saved: Lethe is on, so this chat is off the record and nothing from it goes into memory, "
    "the user profile or skills. This is expected, not an error. Don't retry or work around it; "
    "carry on with the user's request normally."
)

# Memory-provider tools (byterover, retaindb, hindsight, honcho, ...) live outside the tool
# registry. Their write tools are named with one of these verbs; reads (query, search,
# profile, context, status) are left alone.
_PROVIDER_WRITE = re.compile(
    r"(remember|curate|retain|store|save|write|add|upsert|update|conclude|ingest|learn|memorize|forget|delete|record)",
    re.I,
)


def _in_registry(tool_name: str) -> bool | None:
    try:
        from tools.registry import registry

        return registry.get_toolset_for_tool(tool_name) is not None
    except Exception:  # noqa: BLE001 - not running inside Hermes (tests)
        return None


def _memory_target(args: dict[str, Any]) -> str:
    return "USER.md" if str(args.get("target") or "memory").lower() == "user" else "MEMORY.md"


def _memory_summary(args: dict[str, Any]) -> str:
    ops = args.get("operations") if args.get("action") == "batch" else [args]
    ops = [op for op in (ops or []) if isinstance(op, dict)]
    actions = sorted({str(op.get("action") or "add") for op in ops}) or ["add"]
    who = "about you" if _memory_target(args) == "USER.md" else "note"
    n = max(len(ops), 1)
    return f"{n} {who} {'/'.join(actions)}" if n > 1 else f"{who} · {'/'.join(actions)}"


def classify(tool_name: str, args: Any, extra: Iterable[str] = ()) -> dict[str, str] | None:
    """Return ``{destination, summary, kind}`` for a call that would persist, else ``None``.

    The summary is a neutral label written by Lethe; it never contains what the agent tried to save.
    """
    args = args if isinstance(args, dict) else {}
    if tool_name == "memory":
        return {"destination": _memory_target(args), "summary": _memory_summary(args), "kind": "memory"}
    if tool_name == "skill_manage":
        name = str(args.get("name") or "skill")[:60]
        action = str(args.get("action") or "edit")
        return {"destination": f"skills/{name}", "summary": f"{action} skill", "kind": "skill"}
    if tool_name in set(extra):
        return {"destination": tool_name, "summary": "custom blocked tool", "kind": "custom"}
    provider, _, verb = tool_name.partition("_")
    # Match the verb after the provider prefix, so "retaindb_search" isn't read as "retain".
    if _in_registry(tool_name) is False and _PROVIDER_WRITE.search(verb or tool_name):
        return {"destination": f"provider:{provider}", "summary": f"{tool_name}", "kind": "provider"}
    return None


def make_pre_tool_call(get_extra):
    def hook(tool_name: str = "", args: Any = None, session_id: str = "", **_: Any):
        on = False
        try:
            on = bool(session_id) and store.is_on(session_id)
            if not on:
                return None
            hit = classify(tool_name, args, get_extra())
            if hit is None:
                return None
            store.record(session_id, {"tool": tool_name, **hit})
            return {"action": "block", "message": BLOCK_MESSAGE}
        except Exception:  # noqa: BLE001
            # Fail closed for the tools we know write memory; open for everything else.
            logger.warning("lethe: guard error", exc_info=True)
            if on and tool_name in {"memory", "skill_manage"}:
                return {"action": "block", "message": BLOCK_MESSAGE}
            return None

    return hook

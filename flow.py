"""The "where it went" view: a summary of what Lethe kept out, for text surfaces and Desktop."""

from __future__ import annotations

from typing import Any

from . import store

LANES = (
    ("memory", "Memory", "MEMORY.md"),
    ("user", "User profile", "USER.md"),
    ("skills", "Skills", "skills/"),
    ("provider", "Memory provider", "provider:"),
)


def _lane(destination: str) -> str:
    if destination == "MEMORY.md":
        return "memory"
    if destination == "USER.md":
        return "user"
    if destination.startswith("skills/"):
        return "skills"
    if destination.startswith("provider:"):
        return "provider"
    return "memory"


def configured_provider() -> str:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        return str(((cfg.get("memory") or {}).get("provider")) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def build(sid: str) -> dict[str, Any]:
    s = store.get(sid) or {}
    events = list(s.get("events") or [])
    lanes = []
    for key, label, dest in LANES:
        hits = [e for e in events if _lane(str(e.get("destination", ""))) == key]
        lanes.append({"key": key, "label": label, "dest": dest, "kept_out": len(hits),
                      "labels": [e.get("summary", "") for e in hits][-3:]})
    gaps = []
    provider = configured_provider()
    if provider:
        gaps.append(f"{provider} syncs each turn outside tool calls; Lethe can't stop that sync.")
    if int(s.get("since_turn") or 0) > 0:
        n = int(s["since_turn"])
        gaps.append("1 turn while Lethe was off wasn't covered." if n == 1
                    else f"{n} turns while Lethe was off weren't covered.")
    if s.get("shred_note") and not s.get("shredded"):
        gaps.append(s["shred_note"])
    return {
        "session_id": sid,
        "on": bool(s.get("on")),
        "since": s.get("since"),
        "since_turn": int(s.get("since_turn") or 0),
        "shredded": bool(s.get("shredded")),
        "total": len(events),
        "lanes": lanes,
        "events": [{"t": e.get("t"), "tool": e.get("tool"), "destination": e.get("destination"),
                    "summary": e.get("summary")} for e in events][-50:],
        "gaps": gaps,
    }


def line(sid: str) -> str:
    """The one-line live status shown after each turn in the CLI/TUI."""
    f = build(sid)
    if not f["on"]:
        return ""
    n = f["total"]
    return (f"≋ Lethe · off the record · nothing saved"
            + (f" · {n} write{'s' if n != 1 else ''} kept out" if n else "") + " · /lethe-where")


TEXT_ART_SURFACES = frozenset({"cli", "tui"})


def text(sid: str, *, ending: bool = False, surface: str = "cli") -> str:
    """The river view for chat output. Terminals get the drawing; Desktop and messaging apps
    (proportional fonts) get the same receipt as a plain list."""
    from . import art

    surface = (surface or "cli").lower()
    if surface in TEXT_ART_SURFACES:
        return art.card(build(sid), ending=ending)
    return art.plain(build(sid), ending=ending, desktop=surface in {"desktop", "gui"})

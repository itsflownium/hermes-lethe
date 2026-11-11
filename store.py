"""Lethe's own small state file, shared by the agent process and the Desktop backend.

Lives at ``$HERMES_HOME/plugin-data/lethe/sessions.json``. It only ever holds session ids,
timestamps and neutral labels for what was kept out of memory (never the content itself).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

MAX_SESSIONS = 200
MAX_EVENTS = 200


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:  # noqa: BLE001 - tests and the Desktop backend may run without Hermes on path
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def data_dir() -> Path:
    return hermes_home() / "plugin-data" / "lethe"


def _path() -> Path:
    return data_dir() / "sessions.json"


@contextlib.contextmanager
def _locked() -> Iterator[None]:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "sessions.lock", "a+") as handle:
        if os.name == "nt":  # pragma: no cover
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name != "nt":
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read() -> dict[str, Any]:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write(data: dict[str, Any]) -> None:
    sessions = data.get("sessions", {})
    if len(sessions) > MAX_SESSIONS:  # keep the most recently touched
        keep = sorted(sessions.items(), key=lambda kv: kv[1].get("touched", 0), reverse=True)[:MAX_SESSIONS]
        data["sessions"] = dict(keep)
    fd, tmp = tempfile.mkstemp(dir=str(data_dir()), prefix=".sessions.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, _path())


def _session(data: dict[str, Any], sid: str) -> dict[str, Any]:
    return data.setdefault("sessions", {}).setdefault(sid, {
        "on": False, "since": None, "since_turn": 0, "events": [], "shredded": False,
    })


# --- reads ------------------------------------------------------------------------------------

def get(sid: str) -> dict[str, Any] | None:
    if not sid:
        return None
    return _read().get("sessions", {}).get(sid)


def is_on(sid: str) -> bool:
    s = get(sid)
    return bool(s and s.get("on"))


# --- writes -----------------------------------------------------------------------------------

def enable(sid: str, turn: int | None = None) -> dict[str, Any]:
    """Turn Lethe on. ``turn`` is how many user turns came before; ``None`` = fill in next turn."""
    with _locked():
        data = _read()
        s = _session(data, sid)
        if not s["on"]:
            s.update(on=True, since=time.time(), since_turn=turn if turn is not None and not s.get("covered_through") else None)
        s["touched"] = time.time()
        _write(data)
        return dict(s)


def disable(sid: str) -> dict[str, Any]:
    with _locked():
        data = _read()
        s = _session(data, sid)
        s["on"] = False
        s["off_at"] = time.time()
        s["touched"] = time.time()
        _write(data)
        return dict(s)


def note_turn(sid: str, before: int) -> None:
    """Called at the start of each turn while Lethe is on. ``before`` is how many user turns came
    before this one. Turns between the last covered turn and this one weren't covered (Lethe was
    off, or not yet on); they're added to ``since_turn``, the uncovered-turn count shown as a gap."""
    with _locked():
        data = _read()
        s = _session(data, sid)
        if not s.get("on"):
            return
        covered = int(s.get("covered_through") or 0)
        if s.get("since_turn") is None:  # first turn since Lethe was (re)enabled
            s["since_turn"] = int(s.get("uncovered") or 0) + max(0, int(before) - covered)
            s["uncovered"] = s["since_turn"]
        s["covered_through"] = max(covered, int(before) + 1)
        _write(data)


def record(sid: str, event: dict[str, Any]) -> None:
    with _locked():
        data = _read()
        s = _session(data, sid)
        events = s.setdefault("events", [])
        events.append({"t": time.time(), **event})
        del events[:-MAX_EVENTS]
        s["touched"] = time.time()
        _write(data)


def mark_shredded(sid: str, ok: bool, note: str = "") -> None:
    with _locked():
        data = _read()
        s = _session(data, sid)
        s["shredded"] = bool(ok)
        s["shred_note"] = note
        s["touched"] = time.time()
        _write(data)


def recent(limit: int = 20) -> list[tuple[str, dict[str, Any]]]:
    """Chats Lethe has been used in, most recently touched first."""
    sessions = _read().get("sessions", {})
    rows = sorted(sessions.items(), key=lambda kv: kv[1].get("touched", 0), reverse=True)
    return rows[:limit]


# --- the end-of-chat receipt -------------------------------------------------------------------
# Hermes's shared gateway runs on_session_finalize but doesn't pass its message back to the CLI,
# so the receipt is kept here and shown once in the next chat instead.

def set_pending_receipt(receipt: dict[str, Any]) -> None:
    with _locked():
        data = _read()
        data["pending_receipt"] = {**receipt, "t": time.time()}
        _write(data)


def pop_pending_receipt(exclude_sid: str = "") -> dict[str, Any] | None:
    with _locked():
        data = _read()
        receipt = data.get("pending_receipt")
        if not receipt or receipt.get("session_id") == exclude_sid:
            return None
        data.pop("pending_receipt", None)
        _write(data)
        return receipt


def mark_ended(sid: str) -> None:
    with _locked():
        data = _read()
        s = _session(data, sid)
        s["ended"] = True
        s["touched"] = time.time()
        _write(data)


# --- "start the next Desktop chat off the record" ----------------------------------------------
# Desktop can't run a command in a chat that doesn't exist yet, so the panel arms Lethe and the
# on_session_start hook turns the new chat off the record before its first message reaches the model.

ARM_SECONDS = 300


def arm(seconds: float = ARM_SECONDS) -> dict[str, Any]:
    with _locked():
        data = _read()
        data["armed"] = {"t": time.time(), "expires": time.time() + max(30.0, float(seconds))}
        _write(data)
        return data["armed"]


def disarm() -> None:
    with _locked():
        data = _read()
        if data.pop("armed", None) is not None:
            _write(data)


def armed() -> dict[str, Any] | None:
    a = _read().get("armed")
    return a if a and a.get("expires", 0) > time.time() else None


def consume_armed() -> bool:
    with _locked():
        data = _read()
        a = data.pop("armed", None)
        if a is None:
            return False
        _write(data)
        return a.get("expires", 0) > time.time()

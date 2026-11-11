"""Delete an off-the-record chat's transcript from Hermes's session database."""

from __future__ import annotations

import logging

from . import store

logger = logging.getLogger(__name__)


def shred(sid: str) -> tuple[bool, str]:
    """Delete *sid* (and its compression chain) from ``state.db``. Returns ``(ok, note)``."""
    origin(sid)  # keep the client's name in Lethe's record once the row is gone
    try:
        from hermes_state import SessionDB
    except Exception:  # noqa: BLE001
        note = "Transcript not deleted: Hermes's session database wasn't available."
        store.mark_shredded(sid, False, note)
        return False, note
    try:
        db = SessionDB()
        try:
            db.delete_session(
                sid,
                sessions_dir=store.hermes_home() / "sessions",
                exclude_active_write_guards=True,
                include_compression_chain=True,
            )
            still_there = db.get_session(sid) if hasattr(db, "get_session") else None
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()
    except Exception as exc:  # noqa: BLE001 - includes SessionActiveWriteGuardError mid-turn
        name = type(exc).__name__
        note = ("Transcript not deleted yet: a turn is still running. It will be deleted when the chat ends."
                if "Guard" in name else f"Transcript not deleted: {name}.")
        logger.warning("lethe: shred failed for %s", sid, exc_info=True)
        store.mark_shredded(sid, False, note)
        return False, note
    if still_there:
        note = "Transcript not deleted: the session is still listed."
        store.mark_shredded(sid, False, note)
        return False, note
    store.mark_shredded(sid, True)
    return True, "Transcript deleted."


_origins: dict[str, str] = {}


def message_count(sid: str) -> int:
    try:
        from hermes_state import SessionDB

        db = SessionDB()
        try:
            row = db.get_session(sid) or {}
            return int(row.get("message_count") or 0)
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()
    except Exception:  # noqa: BLE001
        return 0


def session_row(sid: str) -> dict[str, Any] | None:
    """Hermes's row for a chat: ``{}`` when it doesn't exist, ``None`` when it can't be read."""
    try:
        from hermes_state import SessionDB

        db = SessionDB()
        try:
            return dict(db.get_session(sid) or {})
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()
    except Exception:  # noqa: BLE001
        return None


def origin(sid: str) -> str:
    """The client that created a chat (``cli``, ``tui``, ``desktop``), from Hermes's session row."""
    if sid in _origins:
        return _origins[sid]
    value = ""
    try:
        from hermes_state import SessionDB

        db = SessionDB()
        try:
            row = db.get_session(sid) or {}
            value = str(row.get("created_source") or row.get("source") or "").lower()
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()
    except Exception:  # noqa: BLE001
        value = ""
    if value:
        _origins[sid] = value
        try:
            store.note_app(sid, value)
        except Exception:  # noqa: BLE001
            pass
    return value

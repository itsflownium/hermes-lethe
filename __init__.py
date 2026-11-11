"""Lethe: take one Hermes chat off the record.

While Lethe is on for a chat, Hermes can still read what it already knows, but nothing from the
chat is written to MEMORY.md, USER.md, skills or a memory provider's write tools, including by the
background review that runs after each turn. When the chat ends, its transcript is deleted from
Hermes's session database.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from . import cli, flow, guard, shred, store

logger = logging.getLogger(__name__)

CONTEXT_NOTE = (
    "[Lethe] This chat is off the record. Behave as you normally would, including saving things to "
    "memory or the user profile when you'd usually do so: Lethe will refuse those writes, and that is "
    "expected, so don't retry or work around it. When a save is refused, tell the user briefly that it "
    "wasn't saved because this chat is off the record. Never say you noted or will remember "
    "something from this chat."
)
LINE_SURFACES = frozenset({"cli", "tui"})

HELP = """/lethe            take this chat off the record
/lethe-off        put it back on the record (the transcript is then kept)
/lethe-where      show where everything went
/lethe-status     is this chat off the record?
/lethe-end        finish off the record: delete the transcript now and show the receipt
/lethe-forget     delete this chat's transcript now (Lethe stays on)

/lethe off, /lethe where, /lethe status, /lethe end and /lethe forget work too.
In another terminal, `hermes lethe watch` shows the live river beside your chat."""

_lock = threading.Lock()
_turns: dict[str, int] = {}
_handles: dict[str, Any] = {}
_last: dict[str, str] = {}


_ALIASES = {
    "": "on", "on": "on", "enable": "on", "start": "on", "private": "on",
    "off": "off", "disable": "off", "stop": "off", "end": "off", "exit": "off",
    "where": "where", "show": "where", "flow": "where", "river": "where",
    "status": "status", "state": "status", "?": "status",
    "forget": "forget", "shred": "forget", "delete": "forget",
    "end": "end", "finish": "end", "done": "end", "close": "end", "receipt": "end",
    "help": "help", "-h": "help", "--help": "help",
}


def parse(raw_args: str) -> str:
    """First word of the arguments, forgiving of case, punctuation and a leading slash or dash.

    ``/lethe -where`` (a dash left over from typing ``/lethe-where`` after the menu inserted
    ``/lethe ``) and ``/lethe lethe-where`` both mean ``where``.
    """
    if (raw_args or "").strip().lower() in {"-h", "--help"}:
        return "help"
    words = (raw_args or "").strip().lower().split()
    word = words[0].strip("/.,!?;:'\"()[]") if words else ""
    if word.startswith("lethe"):
        word = word[len("lethe"):]
    word = word.lstrip("-_").strip("/.,!?;:'\"()[]")
    if not word and words and "?" in words[0]:
        word = "?"
    return _ALIASES.get(word, word)


def _user_turns(history: Any) -> int | None:
    """User turns that came before the one being sent now.

    In a real Hermes turn ``conversation_history`` already ends with the message being sent
    (its stored text can differ from ``user_message``), so a trailing user entry isn't "before".
    """
    if not isinstance(history, list):
        return None
    users = sum(1 for m in history if isinstance(m, dict) and m.get("role") == "user")
    last = history[-1] if history else None
    if users and isinstance(last, dict) and last.get("role") == "user":
        return users - 1
    return users


def _receipt_line(receipt: dict[str, Any]) -> str:
    n = int(receipt.get("total") or 0)
    sid = str(receipt.get("session_id") or "")
    gone = "transcript deleted" if receipt.get("shredded") else "transcript kept"
    return (f"≋ Lethe · your last off-the-record chat ended: {n} write{'s' if n != 1 else ''} kept out of memory"
            f" · {gone} · hermes lethe show {sid[:18]}")


def _banner(sid: str) -> str:
    # Kept to 2 short lines: the TUI shows replies up to ~180 characters inline and pages longer ones.
    return ("≋ Lethe is on · this chat is off the record: nothing from it is saved, and its transcript "
            "is deleted when it ends.\n   /lethe-where · /lethe-end · /lethe-off")


def register(ctx: Any) -> None:
    def extra_tools() -> list[str]:
        try:
            value = ctx.get_config("block_tools", []) or []
            return [str(v) for v in value] if isinstance(value, (list, tuple)) else []
        except Exception:  # noqa: BLE001
            return []

    def keep_transcript() -> bool:
        try:
            return bool(ctx.get_config("keep_transcript", False))
        except Exception:  # noqa: BLE001
            return False

    def status_line_on() -> bool:
        try:
            return bool(ctx.get_config("status_line", True))
        except Exception:  # noqa: BLE001
            return True

    def surface(platform: str = "") -> str:
        try:
            s = ctx.session_surface() if hasattr(ctx, "session_surface") else ""
        except Exception:  # noqa: BLE001
            s = ""
        return str(s or platform or "").lower()

    # --- hooks -------------------------------------------------------------------------------

    ctx.register_hook("pre_tool_call", guard.make_pre_tool_call(extra_tools))

    def pre_llm_call(session_id: str = "", conversation_history: Any = None, **_: Any):
        if not session_id or not store.is_on(session_id):
            return None
        before = _user_turns(conversation_history)
        store.note_turn(session_id, before if before is not None else 0)
        return {"context": CONTEXT_NOTE}

    ctx.register_hook("pre_llm_call", pre_llm_call)

    def post_llm_call(session_id: str = "", platform: str = "", **_: Any) -> None:
        try:
            if not session_id:
                return
            with _lock:
                _turns[session_id] = _turns.get(session_id, 0) + 1
            if surface(platform) in LINE_SURFACES and hasattr(ctx, "post_message"):
                receipt = store.pop_pending_receipt(exclude_sid=session_id)
                if receipt:
                    ctx.post_message(_receipt_line(receipt))
            if not store.is_on(session_id) or surface(platform) not in LINE_SURFACES or not status_line_on():
                return
            if not hasattr(ctx, "post_message"):
                return
            text = flow.line(session_id)
            if not text or _last.get(session_id) == text:
                return
            handle = _handles.get(session_id)
            result = handle.edit(text) if handle is not None else None
            if handle is None:
                handle = ctx.post_message(text)
            if getattr(handle, "ok", False) or (isinstance(result, dict) and result.get("ok")):
                with _lock:
                    _handles[session_id] = handle
                    _last[session_id] = text
        except Exception:  # noqa: BLE001 - the line is a convenience
            logger.debug("lethe: live line skipped", exc_info=True)

    ctx.register_hook("post_llm_call", post_llm_call)

    def on_session_finalize(session_id: str = "", **_: Any):
        try:
            if not session_id:
                return None
            s = store.get(session_id)
            if not s:
                return None
            with _lock:
                _handles.pop(session_id, None)
                _last.pop(session_id, None)
                _turns.pop(session_id, None)
            if not s.get("on"):
                return None
            if not keep_transcript():
                shred.shred(session_id)
            if not s.get("ended"):
                f = flow.build(session_id)
                store.set_pending_receipt({"session_id": session_id, "total": f["total"], "shredded": f["shredded"]})
            # Shown at exit where Hermes relays it (local CLI, one-shot, TUI /new, messaging);
            # the shared gateway drops it, so the pending receipt above covers that case.
            return {"message": flow.text(session_id, ending=True)}
        except Exception:  # noqa: BLE001
            logger.warning("lethe: finalize failed", exc_info=True)
            return None

    ctx.register_hook("on_session_finalize", on_session_finalize)

    def on_session_start(session_id: str = "", **_: Any) -> None:
        """A Desktop chat started from the panel's "Start off the record" goes off the record
        here, before its first message reaches the model."""
        try:
            if not session_id or store.get(session_id) or not store.armed():
                return
            if shred.origin(session_id) not in {"desktop", "gui"} or shred.message_count(session_id) > 1:
                return
            if store.consume_armed():
                store.enable(session_id, None)
        except Exception:  # noqa: BLE001
            logger.warning("lethe: on_session_start failed", exc_info=True)

    ctx.register_hook("on_session_start", on_session_start)

    # --- /lethe ------------------------------------------------------------------------------

    def _where(session_id: str | None, platform: str | None) -> str:
        """cli / tui / desktop / a messaging platform. The shared gateway labels CLI and Desktop
        chats alike as ``local``, so fall back to the client that created the chat."""
        for value in (platform, surface()):
            v = (value or "").lower()
            if v and v != "local":
                return "desktop" if v == "gui" else v
        origin = shred.origin(session_id) if session_id else ""
        return {"gui": "desktop"}.get(origin, origin) or "cli"

    def run(sub: str, session_id: str | None, platform: str | None = None) -> str:
        where = _where(session_id, platform)
        if sub == "help":
            return HELP
        if not session_id:
            return "Lethe needs a chat to work on. Start a chat, then type /lethe."
        if sub == "on":
            if store.is_on(session_id):
                return "≋ This chat is already off the record.\n   /lethe-where shows what was kept out · /lethe-off goes back on"
            with _lock:
                turns = _turns.get(session_id)
            store.enable(session_id, None)
            return _banner(session_id)
        if sub == "off":
            if not store.is_on(session_id):
                return "This chat is already on the record. Type /lethe to take it off."
            store.disable(session_id)
            with _lock:
                h = _handles.pop(session_id, None)
                _last.pop(session_id, None)
            if h is not None:
                try:
                    h.edit("≋ Lethe off · this chat is back on the record")
                except Exception:  # noqa: BLE001
                    pass
            n = flow.build(session_id)["total"]
            return (f"≋ Lethe is off · this chat is back on the record from here on.\n"
                    f"   {n} write{'s' if n != 1 else ''} kept out while it was on · /lethe-where to see them")
        if sub == "where":
            if not store.get(session_id):
                return "Lethe hasn't been used in this chat. Type /lethe to take it off the record."
            return flow.text(session_id, surface=where)
        if sub == "status":
            if store.is_on(session_id):
                n = flow.build(session_id)["total"]
                return (f"≋ This chat is off the record · {n} write{'s' if n != 1 else ''} kept out so far.\n"
                        "   /lethe-where to see them · /lethe-off to go back on the record")
            return "This chat is on the record. Type /lethe to take it off."
        if sub == "end":
            if not store.get(session_id) or not store.is_on(session_id):
                return "This chat isn't off the record. Type /lethe to take it off."
            store.mark_ended(session_id)
            note = "Transcript kept (keep_transcript is on)."
            if not keep_transcript():
                ok, note = shred.shred(session_id)
            close = "type /exit to close it" if where in {"cli", "tui"} else "you can close it now"
            return (flow.text(session_id, ending=True, surface=where) + f"\n\n≋ {note} This chat is finished off the record: "
                    f"{close}. Lethe stays on until you do, and anything after this is deleted too.")
        if sub == "forget":
            if not store.is_on(session_id):
                store.enable(session_id, None)
            ok, note = shred.shred(session_id)
            return (f"≋ {note} Lethe stays on, and anything after this is deleted when the chat ends."
                    if ok else f"⚠ {note}")
        return f"Unknown option: {sub}\n\n{HELP}"

    def command(raw_args: str = "", session_id: str | None = None, platform: str | None = None, **_: Any) -> str:
        return run(parse(raw_args), session_id, platform)

    ctx.register_command(
        "lethe", handler=command,
        description="Take this chat off the record: nothing from it goes into Hermes's memory.",
        args_hint="[on|off|where|forget|status]",
    )

    # One command per action too, so each is a single pick in Desktop's / menu and in TUI completion.
    for name, sub, text in (
        ("lethe-off", "off", "Put this chat back on the record (Lethe off)."),
        ("lethe-where", "where", "Show where everything from this off-the-record chat went."),
        ("lethe-status", "status", "Is this chat off the record?"),
        ("lethe-forget", "forget", "Delete this chat's transcript now (Lethe stays on)."),
        ("lethe-end", "end", "Finish this chat off the record: delete the transcript now and show the receipt."),
    ):
        ctx.register_command(
            name, handler=(lambda raw_args="", session_id=None, platform=None, _sub=sub, **_: run(_sub, session_id, platform)),
            description=text,
        )

    cli.register(ctx)

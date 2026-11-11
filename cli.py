"""`hermes lethe ...`: Lethe's terminal side.

    hermes lethe              off-the-record chats, newest first
    hermes lethe watch [ID]   a live river next to your CLI/TUI chat (Ctrl+C to quit)
    hermes lethe show [ID]    the river for one chat, once

`watch` is the terminal's version of the Desktop panel: open it in a split pane beside
`hermes chat --tui` and every write Hermes tries to make drops into the river as it happens.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from . import art, flow, shred, store

FRAME_S = 0.12
POLL_S = 0.6


def _color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


STALE_S = 30 * 60  # a chat with no session row and no activity for this long is treated as gone


def _ended(sid: str, s: dict) -> bool:
    """Lethe's own record, or Hermes's session row, says this chat is over."""
    if s.get("ended") or s.get("shredded"):
        return True
    row = shred.session_row(sid)
    if row is None:  # can't read Hermes's database: trust Lethe's record
        return False
    if not row:  # no row: a chat that never got going, or was removed
        return time.time() - float(s.get("touched") or s.get("since") or 0) > STALE_S
    return bool(row.get("ended_at"))


def _live(sid: str, s: dict) -> bool:
    """Off the record and still open."""
    return bool(s.get("on")) and not _ended(sid, s)


def _latest(on_only: bool = True) -> str | None:
    for sid, s in store.recent(50):
        if not on_only or _live(sid, s):
            return sid
    return None


def _resolve(given: str | None, live_only: bool = False) -> str | None:
    if given:
        rows = [sid for sid, _ in store.recent(200)]
        if given in rows:
            return given
        matches = [sid for sid in rows if sid.startswith(given) or sid.endswith(given)]
        return matches[0] if len(matches) == 1 else given
    return _latest(True) if live_only else (_latest(True) or _latest(False))


_APPS = {"cli": "CLI", "tui": "TUI", "desktop": "Desktop", "gui": "Desktop"}


def _when(ts: float) -> str:
    if not ts:
        return "?"
    lt = time.localtime(ts)
    return time.strftime("%H:%M" if time.strftime("%Y%m%d", lt) == time.strftime("%Y%m%d") else "%d %b", lt)


def _list() -> int:
    rows = store.recent(20)
    if not rows:
        print("Lethe hasn't been used yet. In a chat, type /lethe to take it off the record.")
        return 0
    t, d, r = (art.TEAL, art.DIM, art.RESET) if _color() else ("", "", "")
    print(f"{d}{'chat':<14} {'app':<8} {'started':<8} {'state':<26} {'kept out':>8}{r}")
    for sid, s in rows:
        n = len(s.get("events") or [])
        app = _APPS.get(shred.origin(sid), "?")
        if _live(sid, s):
            state = f"{t}{'live · off the record':<26}{r}"
        elif s.get("on") or s.get("shredded"):
            gone = "transcript deleted" if s.get("shredded") else "transcript kept"
            state = f"{d}{'ended · ' + gone:<26}{r}"
        else:
            state = f"{d}{'back on the record':<26}{r}"
        short = sid[:12] + "…" if len(sid) > 13 else sid
        print(f"{short:<14} {app:<8} {_when(float(s.get('since') or s.get('touched') or 0)):<8} {state} {n:>8}")
    print(f"\n{d}hermes lethe watch  follows the newest live chat · hermes lethe show ID  one chat's river{r}")
    return 0


def _show(sid: str | None) -> int:
    sid = _resolve(sid)
    if not sid or not store.get(sid):
        print("No off-the-record chat found. In a chat, type /lethe first.")
        return 1
    data = flow.build(sid)
    print(art.card(data, color=_color(), ending=bool(data.get("shredded")), max_events=12))
    return 0


def _watch(sid_arg: str | None) -> int:
    if not sys.stdout.isatty():
        return _show(sid_arg)
    out = sys.stdout
    out.write("\x1b[?25l\x1b[2J")
    seen: set[str] = set()
    first = True
    drops: list[list[Any]] = []  # [lane, age]
    frame = 0
    sid = None
    data: dict[str, Any] = {}
    last_poll = 0.0
    try:
        while True:
            now = time.time()
            if now - last_poll >= POLL_S:
                last_poll = now
                sid = _resolve(sid_arg, live_only=not sid_arg)
                data = flow.build(sid) if sid and store.get(sid) else {}
                for e in data.get("events", []):
                    key = f"{e.get('t')}-{e.get('tool')}"
                    if key in seen:
                        continue
                    seen.add(key)
                    if not first:  # don't replay history; only new writes fall
                        drops.append([art.lane_of(e.get("destination", "")), -2 * len(drops)])
                first = False
            if data:
                live = [(lane, age) for lane, age in drops if age >= 0]
                body = art.card(data, color=True, frame=frame // 3, drops=live, max_events=8)
                head = f"{art.DIM}watching {sid[:24]}…{art.RESET}"
            else:
                body = ("≋ Lethe\n\n  Waiting for an off-the-record chat.\n"
                        "  In your Hermes chat, type /lethe.")
                head = f"{art.DIM}hermes lethe watch · Ctrl+C to quit{art.RESET}"
            text = head + "\n\n" + body
            out.write("\x1b[H" + "\n".join(line + "\x1b[K" for line in text.split("\n")) + "\x1b[J")
            out.flush()
            for drop in drops:
                drop[1] += 1
            drops = [x for x in drops if x[1] < art.DROP_ROWS + 3]
            frame += 1
            time.sleep(FRAME_S)
    except KeyboardInterrupt:
        pass
    finally:
        out.write("\x1b[?25h\n")
        out.flush()
    return 0


def _setup(subparser: Any) -> None:
    subs = subparser.add_subparsers(dest="lethe_command")
    subs.add_parser("list", help="Off-the-record chats, newest first")
    w = subs.add_parser("watch", help="A live river beside your chat (Ctrl+C to quit)")
    w.add_argument("session", nargs="?", help="Chat id (default: the newest off-the-record chat)")
    s = subs.add_parser("show", help="The river for one chat")
    s.add_argument("session", nargs="?", help="Chat id (default: the newest off-the-record chat)")


def _handle(args: Any) -> int:
    sub = getattr(args, "lethe_command", None)
    if sub == "watch":
        return _watch(getattr(args, "session", None))
    if sub == "show":
        return _show(getattr(args, "session", None))
    return _list()


def register(ctx: Any) -> None:
    if hasattr(ctx, "register_cli_command"):
        ctx.register_cli_command(
            name="lethe",
            help="Lethe: off-the-record chats and the live river view",
            setup_fn=_setup,
            handler_fn=_handle,
        )

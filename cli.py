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


IDLE_S = 30 * 60  # off the record but quiet this long: probably a window closed without ending the chat


def _state(sid: str, s: dict) -> str:
    """``live``, ``idle``, ``ended`` or ``off`` (back on the record)."""
    if not s.get("on"):
        return "ended" if s.get("shredded") else "off"
    if s.get("ended") or s.get("shredded"):
        return "ended"
    row = shred.session_row(sid)
    if row and row.get("ended_at"):
        return "ended"
    last = max(
        float(s.get("touched") or s.get("since") or 0),
        float((row or {}).get("last_activity_at") or 0),
        max((float(e.get("t") or 0) for e in s.get("events") or [] if isinstance(e.get("t"), (int, float))), default=0.0),
    )
    return "live" if time.time() - last <= IDLE_S else "idle"


def _live(sid: str, s: dict) -> bool:
    return _state(sid, s) == "live"


def _latest(on_only: bool = True) -> str | None:
    """Newest live chat; else the newest idle one; else (on_only=False) the newest of any."""
    rows = store.recent(50)
    states = [(sid, _state(sid, s)) for sid, s in rows]
    for want in ("live", "idle"):
        for sid, st in states:
            if st == want:
                return sid
    return None if on_only else (rows[0][0] if rows else None)


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
        app = _APPS.get(s.get("app") or shred.origin(sid), "?")
        st = _state(sid, s)
        if st == "live":
            state = f"{t}{'live · off the record':<26}{r}"
        elif st == "idle":
            state = f"{'idle · off the record':<26}"
        elif st == "ended":
            gone = "transcript deleted" if s.get("shredded") else "transcript kept"
            state = f"{d}{'ended · ' + gone:<26}{r}"
        else:
            state = f"{d}{'back on the record':<26}{r}"
        short = sid[:12] + "…" if len(sid) > 13 else sid
        print(f"{short:<14} {app:<8} {_when(float(s.get('since') or s.get('touched') or 0)):<8} {state} {n:>8}")
    print(f"\n{d}hermes lethe watch  follows the newest live (else idle) chat · hermes lethe show ID  one chat's river{r}")
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

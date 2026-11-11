"""The river, drawn in text: the same picture as the Desktop panel, for the CLI and TUI.

    ╭─────────────╮
    │  this chat  │      every write Hermes tries to make drops out of the chat...
    ╰──────┬──────╯
  ≈≈≈≈≈≈≈○≈≈≈≈≈≈≈≈≈≈   ...and sinks into the river Lethe...
  ╭──────╮ ╭──────╮    ...so the stores below stay at 0 written.

``render`` is pure: give it a flow (``flow.build``) and, for animation, the drops in flight.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

WIDTH = 44
CENTERS = (6, 17, 28, 39)
MID = 22
LANES = ("memory", "user", "skills", "provider")
NAMES = {"memory": "Memory", "user": "Profile", "skills": "Skills", "provider": "Provider"}
DROP_ROWS = 2  # rows a drop falls through before it reaches the river

TEAL, DIM, BOLD, YELLOW, RESET = "\x1b[38;5;37m", "\x1b[2m", "\x1b[1m", "\x1b[33m", "\x1b[0m"
WAVE = "≈≈∼≈≈≈∽≈"


def lane_of(destination: str) -> str:
    d = str(destination or "")
    if d == "USER.md":
        return "user"
    if d.startswith("skills/"):
        return "skills"
    if d.startswith("provider:"):
        return "provider"
    return "memory"


class _Canvas:
    """A grid of cells, each with its own colour, so colour codes never break the alignment."""

    def __init__(self, rows: int, color: bool):
        self.cells = [[(" ", "") for _ in range(WIDTH)] for _ in range(rows)]
        self.color = color

    def put(self, row: int, col: int, text: str, style: str = "") -> None:
        for i, ch in enumerate(text):
            if 0 <= col + i < WIDTH:
                self.cells[row][col + i] = (ch, style)

    def lines(self) -> list[str]:
        out = []
        for row in self.cells:
            if not self.color:
                out.append("".join(ch for ch, _ in row).rstrip())
                continue
            parts, cur = [], ""
            while row and row[-1][0] == " ":
                row = row[:-1]
            for ch, style in row:
                if style != cur:
                    parts.append(RESET if cur else "")
                    parts.append(style)
                    cur = style
                parts.append(ch)
            parts.append(RESET if cur else "")
            out.append("".join(parts).rstrip())
        return out


def render(flow: dict[str, Any], *, color: bool = False, frame: int = 0,
           drops: Iterable[tuple[str, int]] = ()) -> list[str]:
    """Draw the river. ``drops`` are ``(lane, age_in_frames)`` for writes in flight.

    With no drops, a static picture marks each lane that kept something out with ✕ above
    the river and a ripple ○ in it.
    """
    on = bool(flow.get("on"))
    counts = {l["key"]: int(l.get("kept_out") or 0) for l in flow.get("lanes", [])}
    t = TEAL if color and on else DIM if color else ""
    d = DIM if color else ""
    c = _Canvas(13, color)

    # The chat
    c.put(0, MID - 7, "╭─────────────╮", t)
    c.put(1, MID - 7, "│  this chat  │", t)
    c.put(1, MID - 4, "this chat", BOLD if color else "")
    c.put(2, MID - 7, "╰──────┬──────╯", t)

    # Paths to each store
    c.put(3, CENTERS[0], "╭" + "─" * (CENTERS[-1] - CENTERS[0] - 1) + "╮", d)
    for x in CENTERS[1:-1]:
        c.put(3, x, "┬", d)
    c.put(3, MID, "┴", d)
    for row in range(4, 4 + DROP_ROWS):
        for x in CENTERS:
            c.put(row, x, "┊", d)

    # The river
    river_row = 4 + DROP_ROWS
    wave = TEAL if color and on else DIM if color else ""
    for row, shift in ((river_row, frame), (river_row + 1, -frame + 3)):
        line = "".join(WAVE[(i + shift) % len(WAVE)] for i in range(WIDTH))
        c.put(row, 0, line, wave)
    c.put(river_row + 1, WIDTH - 13, " L E T H E ", (TEAL + BOLD) if color and on else d)

    drops = list(drops)
    if drops:
        for lane, age in drops:
            x = CENTERS[LANES.index(lane)]
            if age < DROP_ROWS:
                c.put(4 + age, x, "◆", (TEAL + BOLD) if color else "")
            elif age < DROP_ROWS + 3:
                c.put(river_row, x - 1, ("○", "( )", "(   )")[age - DROP_ROWS].center(3), TEAL if color else "")
    else:
        for lane, x in zip(LANES, CENTERS):
            if counts.get(lane):
                c.put(4 + DROP_ROWS - 1, x, "✕", TEAL if color else "")
                c.put(river_row, x, "○", TEAL if color else "")

    # The stores, untouched
    top = river_row + 2
    for lane, x in zip(LANES, CENTERS):
        n = counts.get(lane, 0)
        style = TEAL if color and n else d
        c.put(top, x - 5, "╭────────╮", style)
        c.put(top + 1, x - 5, "│" + NAMES[lane].center(8) + "│", style)
        c.put(top + 2, x - 5, "│" + (f"{n} kept" if n else "·").center(8) + "│", style)
        c.put(top + 3, x - 5, "╰────────╯", style)
    c.put(top + 4, 0, "nothing saved · 0 written to any of them".center(WIDTH), d)
    return c.lines()


def _clock(ts: Any) -> str:
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return "--:--:--"


def card(flow: dict[str, Any], *, color: bool = False, ending: bool = False, frame: int = 0,
         drops: Iterable[tuple[str, int]] = (), max_events: int = 6) -> str:
    """The full view: headline, river, recent writes kept out, transcript status and gaps."""
    t = TEAL if color else ""
    b = BOLD if color else ""
    r = RESET if color else ""
    y = YELLOW if color else ""
    d = DIM if color else ""
    on = bool(flow.get("on"))
    total = int(flow.get("total") or 0)
    state = ("was off the record" if ending else "is off the record") if on or ending else "is on the record"
    out = [f"{t}{b}≋ Lethe{r} · this chat {state}"
           + (f" · {total} write{'s' if total != 1 else ''} kept out" if total else ""), ""]
    out += ["  " + line for line in render(flow, color=color, frame=frame, drops=drops)]
    events = list(flow.get("events") or [])[-max_events:]
    if events:
        out.append("")
        for e in reversed(events):
            what = str(e.get("summary") or e.get("tool") or "")[:22]
            out.append(f"  {d}{_clock(e.get('t'))}{r}  {what:<22} {d}→ {str(e.get('destination') or '')[:18]:<18}{r} {t}✕{r}")
    out.append("")
    if flow.get("shredded"):
        out.append(f"  {t}✕{r} Transcript deleted from your session history.")
    elif on:
        out.append(f"  {d}Transcript: deleted when this chat ends.{r}")
    elif total:
        out.append(f"  {d}Transcript: kept (Lethe was turned off).{r}")
    for gap in flow.get("gaps") or []:
        out.append(f"  {y}⚠ {gap}{r}")
    return "\n".join(out).rstrip()


def plain(flow: dict[str, Any], *, ending: bool = False, desktop: bool = False, max_events: int = 6) -> str:
    """The same receipt without the drawing, for surfaces that don't use a fixed-width font
    (Desktop shows command replies in a proportional font; messaging apps do too)."""
    on = bool(flow.get("on"))
    total = int(flow.get("total") or 0)
    state = ("was off the record" if ending else "is off the record") if on or ending else "is on the record"
    out = [f"≋ Lethe · this chat {state}"
           + (f" · {total} write{'s' if total != 1 else ''} kept out" if total else " · nothing tried to reach memory")]
    lanes = []
    for l in flow.get("lanes", []):
        n = int(l.get("kept_out") or 0)
        lanes.append(f"{NAMES.get(l['key'], l['key'])}: {f'{n} kept out' if n else '—'}")
    out.append("   " + " · ".join(lanes) + " · nothing saved")
    for e in list(flow.get("events") or [])[-max_events:][::-1]:
        out.append(f"   {_clock(e.get('t'))}  {e.get('summary') or e.get('tool')} → {e.get('destination')}  ✕ kept out")
    if flow.get("shredded"):
        out.append("   ✕ Transcript deleted from your session history.")
    elif on:
        out.append("   Transcript: deleted when this chat ends.")
    elif total:
        out.append("   Transcript: kept (Lethe was turned off).")
    for gap in flow.get("gaps") or []:
        out.append(f"   ⚠ {gap}")
    if desktop:
        out.append("   The river is in the Lethe panel: the eye-and-waves icon in the top bar.")
    return "\n".join(out)

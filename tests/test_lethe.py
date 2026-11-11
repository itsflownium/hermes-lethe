import json

import pytest

from lethe import flow, guard, shred, store


def call(ctx, tool, args, sid="s1"):
    return ctx.hooks["pre_tool_call"](tool_name=tool, args=args, session_id=sid, task_id="t", tool_call_id="c")


def lethe(ctx, args="", sid="s1"):
    return ctx.commands["lethe"](args, session_id=sid)


# --- what counts as a write ---------------------------------------------------------------------

def test_classify_memory_targets():
    assert guard.classify("memory", {"action": "add", "target": "memory", "content": "x"})["destination"] == "MEMORY.md"
    assert guard.classify("memory", {"action": "add", "target": "user", "content": "x"})["destination"] == "USER.md"
    batch = guard.classify("memory", {"action": "batch", "target": "user",
                                      "operations": [{"action": "add"}, {"action": "replace"}]})
    assert batch["destination"] == "USER.md" and batch["summary"].startswith("2 ")


def test_classify_skill_and_provider_writes():
    assert guard.classify("skill_manage", {"action": "create", "name": "deploy"})["destination"] == "skills/deploy"
    assert guard.classify("brv_curate", {})["destination"] == "provider:brv"
    assert guard.classify("retaindb_remember", {})["destination"] == "provider:retaindb"


def test_reads_and_normal_tools_pass():
    for tool in ("brv_query", "retaindb_search", "retaindb_profile", "read_file", "web_search", "session_search"):
        assert guard.classify(tool, {}) is None, tool


def test_registry_tools_never_treated_as_provider_writes(monkeypatch):
    monkeypatch.setattr(guard, "_in_registry", lambda name: True)
    assert guard.classify("write_file", {}) is None
    assert guard.classify("todo_update", {}) is None


def test_extra_block_tools():
    assert guard.classify("notes_save_mcp", {}, extra=["notes_save_mcp"])["kind"] in {"custom", "provider"}


# --- the guard ----------------------------------------------------------------------------------

def test_off_by_default(ctx):
    assert call(ctx, "memory", {"action": "add", "content": "x"}) is None


def test_blocks_only_the_lethe_chat(ctx):
    assert "off the record" in lethe(ctx)
    blocked = call(ctx, "memory", {"action": "add", "target": "user", "content": "Planning a surprise party for Sam"})
    assert blocked["action"] == "block" and blocked["message"].startswith("Not saved")
    assert call(ctx, "memory", {"action": "add", "content": "x"}, sid="other") is None
    assert call(ctx, "read_file", {"path": "a"}) is None


def test_event_log_never_holds_content(ctx, isolated_home):
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "target": "user", "content": "Planning a surprise party for Sam"})
    raw = (isolated_home / "plugin-data" / "lethe" / "sessions.json").read_text()
    assert "Sam" not in raw and "surprise" not in raw
    assert json.loads(raw)["sessions"]["s1"]["events"][0]["destination"] == "USER.md"


def test_background_review_fork_is_caught(ctx):
    """The review fork runs with the parent's session_id, so the same check applies."""
    lethe(ctx)
    assert call(ctx, "skill_manage", {"action": "patch", "name": "x"})["action"] == "block"


def test_off_lets_writes_through_again(ctx):
    lethe(ctx)
    out = lethe(ctx, "off")
    assert "back on the record" in out
    assert call(ctx, "memory", {"action": "add", "content": "x"}) is None


# --- context, live line, receipt ----------------------------------------------------------------

def test_context_note_and_turns_before(ctx):
    assert ctx.hooks["pre_llm_call"](session_id="s1", conversation_history=[]) is None
    lethe(ctx)
    hist = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"}, {"role": "assistant", "content": "d"}]
    res = ctx.hooks["pre_llm_call"](session_id="s1", conversation_history=hist)
    assert "off the record" in res["context"]
    assert store.get("s1")["since_turn"] == 2
    assert any("2 turns while Lethe was off" in g for g in flow.build("s1")["gaps"])


def test_live_line_posts_then_edits(ctx):
    lethe(ctx)
    ctx.hooks["post_llm_call"](session_id="s1", platform="cli")
    call(ctx, "memory", {"action": "add", "content": "x"})
    ctx.hooks["post_llm_call"](session_id="s1", platform="cli")
    assert ctx.posted[0].startswith("≋ Lethe") and "nothing saved" in ctx.posted[0] and "1 write kept out" in ctx.posted[-1]


def test_no_live_line_on_messaging_platforms(ctx):
    ctx.surface = "telegram"
    lethe(ctx)
    ctx.hooks["post_llm_call"](session_id="s1", platform="telegram")
    assert ctx.posted == []


def test_where_view(ctx):
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "target": "user", "content": "x"})
    call(ctx, "skill_manage", {"action": "create", "name": "party"})
    text = lethe(ctx, "where")
    assert "Profile" in text and "1 kept" in text and "L E T H E" in text and "0 written" in text


def test_provider_gap_is_reported(ctx, monkeypatch):
    monkeypatch.setattr(flow, "configured_provider", lambda: "byterover")
    lethe(ctx)
    assert any("byterover" in g for g in flow.build("s1")["gaps"])


# --- end of chat --------------------------------------------------------------------------------

def test_finalize_shreds_and_returns_receipt(ctx, monkeypatch):
    shredded = []
    monkeypatch.setattr(shred, "shred", lambda sid: (shredded.append(sid), store.mark_shredded(sid, True), (True, "ok"))[-1])
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "content": "x"})
    res = ctx.hooks["on_session_finalize"](session_id="s1")
    assert shredded == ["s1"]
    assert "was off the record" in res["message"] and "deleted" in res["message"]


def test_finalize_keeps_transcript_when_configured(monkeypatch):
    import lethe as pkg
    from conftest import FakeCtx
    c = FakeCtx(config={"keep_transcript": True})
    pkg.register(c)
    monkeypatch.setattr(shred, "shred", lambda sid: pytest.fail("should not shred"))
    c.commands["lethe"]("", session_id="s9")
    assert c.hooks["on_session_finalize"](session_id="s9")["message"]


def test_finalize_ignores_normal_and_turned_off_chats(ctx, monkeypatch):
    monkeypatch.setattr(shred, "shred", lambda sid: pytest.fail("should not shred"))
    assert ctx.hooks["on_session_finalize"](session_id="never") is None
    lethe(ctx)
    lethe(ctx, "off")
    assert ctx.hooks["on_session_finalize"](session_id="s1") is None


def test_shred_without_hermes_reports_honestly(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "hermes_state":
            raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    store.enable("s2")
    ok, note = shred.shred("s2")
    assert not ok and "not deleted" in note
    assert any("not deleted" in g for g in flow.build("s2")["gaps"])


def test_command_needs_a_session(ctx):
    assert "needs a chat" in ctx.commands["lethe"]("", session_id=None)
    assert "/lethe off" in ctx.commands["lethe"]("help", session_id="s1")


# --- the text river and `hermes lethe` ----------------------------------------------------------

def test_river_lines_line_up(ctx):
    from lethe import art
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "target": "user", "content": "x"})
    lines = art.render(flow.build("s1"))
    assert all(len(l) <= art.WIDTH for l in lines)
    assert lines[2].index("┬") == lines[3].index("┴") == art.MID
    for x in art.CENTERS:  # each store sits under its own path
        assert lines[4][x] == "┊"
    assert lines[5][art.CENTERS[1]] == "✕" and lines[5][art.CENTERS[0]] == "┊"


def test_river_animation_frames(ctx):
    from lethe import art
    f = flow.build("nobody")
    falling = art.render(f, drops=[("skills", 0)])
    assert falling[4][art.CENTERS[2]] == "◆"
    splash = art.render(f, drops=[("skills", art.DROP_ROWS)])
    assert "○" in splash[4 + art.DROP_ROWS]


def test_colour_codes_keep_alignment(ctx):
    import re
    from lethe import art
    lethe(ctx)
    plain = art.render(flow.build("s1"))
    coloured = art.render(flow.build("s1"), color=True)
    strip = [re.sub(r"\x1b\[[0-9;]*m", "", l) for l in coloured]
    assert strip == plain


def test_shell_list_and_show(ctx, capsys):
    from lethe import cli
    assert cli._handle(type("A", (), {"lethe_command": None})()) == 0
    assert "hasn't been used" in capsys.readouterr().out
    lethe(ctx)
    call(ctx, "skill_manage", {"action": "create", "name": "party"})
    cli._handle(type("A", (), {"lethe_command": None})())
    assert "s1" in capsys.readouterr().out
    cli._handle(type("A", (), {"lethe_command": "watch", "session": None})())  # not a TTY: prints once
    out = capsys.readouterr().out
    assert "L E T H E" in out and "skills/party" in out


# --- every command, and forgiving arguments ------------------------------------------------------

def test_separate_commands_registered(ctx):
    assert {"lethe", "lethe-off", "lethe-where", "lethe-status", "lethe-forget", "lethe-end"} <= set(ctx.commands)


def test_lethe_off_command_turns_it_off(ctx):
    lethe(ctx)
    out = ctx.commands["lethe-off"]("", session_id="s1")
    assert "Lethe is off" in out and not store.is_on("s1")
    assert call(ctx, "memory", {"action": "add", "content": "x"}) is None
    assert "already on the record" in ctx.commands["lethe-off"]("", session_id="s1")


def test_lethe_status_and_where_commands(ctx):
    assert "on the record" in ctx.commands["lethe-status"]("", session_id="s1")
    assert "hasn't been used" in ctx.commands["lethe-where"]("", session_id="s1")
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "content": "x"})
    assert "1 write kept out" in ctx.commands["lethe-status"]("", session_id="s1")
    assert "L E T H E" in ctx.commands["lethe-where"]("", session_id="s1")


def test_lethe_forget_command(ctx, monkeypatch):
    monkeypatch.setattr(shred, "shred", lambda sid: (True, "Transcript deleted."))
    out = ctx.commands["lethe-forget"]("", session_id="s1")
    assert "Transcript deleted" in out and store.is_on("s1")


@pytest.mark.parametrize("raw,expected", [
    ("where?", "where"), ("Where", "where"), ("/off", "off"), ("disable", "off"), ("stop", "off"),
    ("status?", "status"), ("?", "status"), ("", "on"), ("  ON  ", "on"), ("delete", "forget"),
    ("off please", "off"), ("--help", "help"), ("-where", "where"), ("-off", "off"),
    ("-status", "status"), ("-forget", "forget"), ("lethe-where", "where"), ("/lethe-off", "off"), ("-h", "help"),
])
def test_forgiving_arguments(raw, expected):
    import lethe as pkg
    assert pkg.parse(raw) == expected


def test_every_subcommand_through_lethe(ctx, monkeypatch):
    monkeypatch.setattr(shred, "shred", lambda sid: (True, "Transcript deleted."))
    assert "off the record" in lethe(ctx, "")
    assert "already off the record" in lethe(ctx, "on")
    assert "kept out so far" in lethe(ctx, "status?")
    assert "L E T H E" in lethe(ctx, "where?")
    assert "Transcript deleted" in lethe(ctx, "forget")
    assert "Lethe is off" in lethe(ctx, "off")
    assert "Unknown option: banana" in lethe(ctx, "banana")


def test_turns_before_ignores_the_message_being_sent(ctx):
    lethe(ctx)
    # Hermes's real CLI passes the current message as the last history entry.
    ctx.hooks["pre_llm_call"](session_id="s1", user_message="hi",
                               conversation_history=[{"role": "user", "content": "[12:00] hi"}])
    assert store.get("s1")["since_turn"] == 0
    assert not any("while Lethe was off" in g for g in flow.build("s1")["gaps"])


# --- the receipt when the gateway drops on_session_finalize's message -------------------------

def test_lethe_end_shreds_and_shows_receipt(ctx, monkeypatch):
    monkeypatch.setattr(shred, "shred", lambda sid: (store.mark_shredded(sid, True), (True, "Transcript deleted."))[-1])
    assert "isn't off the record" in ctx.commands["lethe-end"]("", session_id="s1")
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "target": "user", "content": "x"})
    out = ctx.commands["lethe-end"]("", session_id="s1")
    assert "was off the record" in out and "Transcript deleted" in out and "/exit" in out
    assert "/exit" not in ctx.commands["lethe-end"]("", session_id="s1", platform="desktop")
    assert store.is_on("s1")  # still blocking until the chat really closes
    assert lethe(ctx, "end").startswith("≋ Lethe")


def test_receipt_shows_once_in_the_next_chat(ctx, monkeypatch):
    monkeypatch.setattr(shred, "shred", lambda sid: (store.mark_shredded(sid, True), (True, "ok"))[-1])
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "target": "user", "content": "x"})
    ctx.hooks["on_session_finalize"](session_id="s1")
    ctx.posted.clear()
    ctx.hooks["post_llm_call"](session_id="s2", platform="cli")
    assert len(ctx.posted) == 1 and "last off-the-record chat ended: 1 write kept out" in ctx.posted[0]
    assert "transcript deleted" in ctx.posted[0]
    ctx.hooks["post_llm_call"](session_id="s3", platform="cli")
    assert len(ctx.posted) == 1  # only once


def test_no_next_chat_receipt_after_lethe_end(ctx, monkeypatch):
    monkeypatch.setattr(shred, "shred", lambda sid: (True, "ok"))
    lethe(ctx)
    ctx.commands["lethe-end"]("", session_id="s1")
    ctx.hooks["on_session_finalize"](session_id="s1")
    ctx.posted.clear()
    ctx.hooks["post_llm_call"](session_id="s2", platform="cli")
    assert ctx.posted == []


def test_receipt_waits_for_a_terminal_surface(ctx, monkeypatch):
    monkeypatch.setattr(shred, "shred", lambda sid: (True, "ok"))
    lethe(ctx)
    ctx.hooks["on_session_finalize"](session_id="s1")
    ctx.surface = "telegram"
    ctx.hooks["post_llm_call"](session_id="s2", platform="telegram")
    assert not any("ended" in p for p in ctx.posted)
    ctx.surface = "cli"
    ctx.posted.clear()
    ctx.hooks["post_llm_call"](session_id="s3", platform="cli")
    assert any("ended" in p for p in ctx.posted)


def _fits_inline(text):
    # The TUI shows a reply inline when it's <= 180 chars and <= 2 non-empty lines; longer ones page.
    return len(text) <= 180 and len([l for l in text.split("\n") if l.strip()]) <= 2


def test_quick_replies_fit_inline_in_the_tui(ctx):
    on = lethe(ctx)
    again = lethe(ctx)
    call(ctx, "memory", {"action": "add", "content": "x"})
    status = ctx.commands["lethe-status"]("", session_id="s1")
    off = ctx.commands["lethe-off"]("", session_id="s1")
    status_off = ctx.commands["lethe-status"]("", session_id="s1")
    for text in (on, again, status, off, status_off):
        assert _fits_inline(text), text
    assert "1 write kept out" in off


def test_desktop_and_messaging_get_a_plain_receipt(ctx):
    lethe(ctx)
    call(ctx, "memory", {"action": "add", "target": "user", "content": "x"})
    desk = ctx.commands["lethe-where"]("", session_id="s1", platform="desktop")
    assert "╭" not in desk and "≈" not in desk and "Profile: 1 kept out" in desk and "Lethe panel" in desk
    import lethe as pkg
    from lethe import shred as sh
    ctx.surface = "local"  # what the shared gateway really reports for CLI and Desktop chats
    sh._origins["s1"] = "desktop"
    assert "Lethe panel" in ctx.commands["lethe-where"]("", session_id="s1", platform="local")
    sh._origins["s1"] = "cli"
    assert "L E T H E" in ctx.commands["lethe-where"]("", session_id="s1", platform="local")
    sh._origins.pop("s1")
    ctx.surface = "cli"
    tg = ctx.commands["lethe"]("where", session_id="s1", platform="telegram")
    assert "╭" not in tg and "Lethe panel" not in tg
    term = ctx.commands["lethe-where"]("", session_id="s1", platform="tui")
    assert "L E T H E" in term


def test_turning_lethe_back_on_only_counts_turns_it_missed(ctx):
    u = lambda n: [{"role": "user", "content": str(i)} for i in range(n)]
    lethe(ctx)
    ctx.hooks["pre_llm_call"](session_id="s1", conversation_history=u(1))  # turn 1, covered
    assert flow.build("s1")["gaps"] == []
    ctx.commands["lethe-off"]("", session_id="s1")
    lethe(ctx)  # back on before any uncovered turn
    ctx.hooks["pre_llm_call"](session_id="s1", conversation_history=u(2))  # turn 2, covered
    assert flow.build("s1")["gaps"] == []
    ctx.commands["lethe-off"]("", session_id="s1")
    # turn 3 happens with Lethe off (no pre_llm_call record), then it's turned on for turn 4
    lethe(ctx)
    ctx.hooks["pre_llm_call"](session_id="s1", conversation_history=u(4))
    assert any(g.startswith("1 turn while Lethe was off") for g in flow.build("s1")["gaps"])


# --- "Start off the record" for a brand-new Desktop chat ---------------------------------------

def _origin(monkeypatch, where="desktop", count=0):
    monkeypatch.setattr(shred, "origin", lambda sid: where)
    monkeypatch.setattr(shred, "message_count", lambda sid: count)


def test_armed_new_desktop_chat_starts_off_the_record(ctx, monkeypatch):
    _origin(monkeypatch)
    store.arm()
    ctx.hooks["on_session_start"](session_id="new1")
    assert store.is_on("new1") and store.armed() is None
    # the very first message is covered: no gap, and a write is blocked
    ctx.hooks["pre_llm_call"](session_id="new1", conversation_history=[{"role": "user", "content": "hi"}])
    assert flow.build("new1")["gaps"] == []
    assert call(ctx, "memory", {"action": "add", "content": "x"}, sid="new1")["action"] == "block"


def test_arm_is_used_once(ctx, monkeypatch):
    _origin(monkeypatch)
    store.arm()
    ctx.hooks["on_session_start"](session_id="new1")
    ctx.hooks["on_session_start"](session_id="new2")
    assert store.is_on("new1") and not store.is_on("new2")


def test_arm_ignores_cli_chats_and_old_chats(ctx, monkeypatch):
    store.arm()
    _origin(monkeypatch, where="cli")
    ctx.hooks["on_session_start"](session_id="cli1")
    _origin(monkeypatch, where="desktop", count=6)
    ctx.hooks["on_session_start"](session_id="old1")
    assert not store.is_on("cli1") and not store.is_on("old1") and store.armed()


def test_arm_expires_and_can_be_cancelled(ctx, monkeypatch):
    import time
    _origin(monkeypatch)
    store.arm()
    store.disarm()
    ctx.hooks["on_session_start"](session_id="n1")
    assert not store.is_on("n1")
    store.arm()
    monkeypatch.setattr(time, "time", lambda: 10**12)
    assert store.armed() is None
    ctx.hooks["on_session_start"](session_id="n2")
    assert not store.is_on("n2")


def test_watch_follows_only_live_chats(ctx, monkeypatch):
    from lethe import cli
    monkeypatch.setattr(shred, "shred", lambda sid: (store.mark_shredded(sid, True), (True, "ok"))[-1])
    lethe(ctx, sid="old")
    ctx.commands["lethe-end"]("", session_id="old")
    assert cli._resolve(None, live_only=True) is None  # a finished chat isn't followed
    assert cli._resolve(None) == "old"                 # but `show` still finds it
    lethe(ctx, sid="new")
    assert cli._resolve(None, live_only=True) == "new"


# --- review fixes ------------------------------------------------------------------------------

def test_status_line_can_be_turned_off():
    import lethe as pkg
    from conftest import FakeCtx
    c = FakeCtx(config={"status_line": False}); pkg.register(c)
    c.commands["lethe"]("", session_id="q1")
    c.hooks["post_llm_call"](session_id="q1", platform="cli")
    assert c.posted == []


def test_guard_fails_closed_only_when_off_the_record(ctx, monkeypatch):
    def boom(*a, **k): raise OSError("disk full")
    monkeypatch.setattr(store, "record", boom)
    # a normal chat must never be blocked, even when Lethe's bookkeeping fails
    assert call(ctx, "memory", {"action": "add", "content": "x"}, sid="normal") is None
    lethe(ctx)
    assert call(ctx, "memory", {"action": "add", "content": "x"})["action"] == "block"


def test_arm_window_is_configurable(monkeypatch):
    import time
    a = store.arm(90)
    assert 85 < a["expires"] - time.time() <= 90
    a = store.arm(1)  # floors at 30 seconds
    assert a["expires"] - time.time() >= 29

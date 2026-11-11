"""Backend for the Lethe Desktop button and panel, at /api/plugins/lethe/."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()
_PKG = "lethe_panel_pkg"
_lock = threading.RLock()
_SID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,255}\Z")


def _mod(name: str):
    root = Path(__file__).resolve().parent.parent
    with _lock:
        if _PKG not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                _PKG, root / "__init__.py", submodule_search_locations=[str(root)])
            pkg = importlib.util.module_from_spec(spec)
            sys.modules[_PKG] = pkg
            try:
                spec.loader.exec_module(pkg)
            except Exception:
                sys.modules.pop(_PKG, None)
                raise
    return importlib.import_module(f"{_PKG}.{name}")


def _sid(value: Any) -> str:
    sid = str(value or "")
    if not _SID.fullmatch(sid):
        raise ValueError("Open a chat first.")
    return sid


async def _serve(call: Callable[[], dict[str, Any]], what: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(call)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:  # noqa: BLE001
        logger.warning("lethe: %s failed", what, exc_info=True)
        return {"ok": False, "error": f"Lethe couldn't {what}."}


@router.get("/flow")
async def flow(session_id: str = "") -> dict[str, Any]:
    def run():
        return {"ok": True, **_mod("flow").build(_sid(session_id))}
    return await _serve(run, "read this chat")


@router.post("/toggle")
async def toggle(body: dict) -> dict[str, Any]:
    def run():
        sid = _sid((body or {}).get("session_id"))
        store = _mod("store")
        want = (body or {}).get("on")
        on = (not store.is_on(sid)) if want is None else bool(want)
        store.enable(sid, None) if on else store.disable(sid)
        return {"ok": True, **_mod("flow").build(sid)}
    return await _serve(run, "change this chat")


@router.post("/forget")
async def forget(body: dict) -> dict[str, Any]:
    def run():
        sid = _sid((body or {}).get("session_id"))
        store = _mod("store")
        if not store.is_on(sid):
            store.enable(sid, None)
        ok, note = _mod("shred").shred(sid)
        return {"ok": ok, "message": note, **_mod("flow").build(sid)}
    return await _serve(run, "delete this chat's transcript")


def _arm_seconds() -> float:
    """plugins.entries.lethe.settings.arm_minutes (default 5)."""
    try:
        from hermes_cli.config import load_config
        cfg = load_config() or {}
        minutes = (((cfg.get("plugins") or {}).get("entries") or {}).get("lethe") or {}).get("settings", {}).get("arm_minutes", 5)
        return max(0.5, float(minutes)) * 60
    except Exception:  # noqa: BLE001
        return 300.0


@router.get("/armed")
async def armed() -> dict[str, Any]:
    def run():
        a = _mod("store").armed()
        return {"ok": True, "armed": bool(a), "expires": (a or {}).get("expires"), "minutes": round(_arm_seconds() / 60, 1)}
    return await _serve(run, "read the next-chat setting")


@router.post("/arm")
async def arm(body: dict) -> dict[str, Any]:
    def run():
        store = _mod("store")
        if (body or {}).get("on") is False:
            store.disarm()
            return {"ok": True, "armed": False}
        a = store.arm(_arm_seconds())
        return {"ok": True, "armed": True, "expires": a["expires"]}
    return await _serve(run, "change the next-chat setting")


@router.post("/diag")
async def diag(body: dict) -> dict[str, Any]:
    def run():
        import json
        import time
        d = _mod("store").data_dir()
        d.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **(body or {})}, default=str)[:2000]
        with open(d / "desktop-diag.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return {"ok": True}
    return await _serve(run, "write diagnostics")

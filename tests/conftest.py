"""Load the plugin folder as a package named `lethe` (no Hermes needed)."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if "lethe" not in sys.modules:
    spec = importlib.util.spec_from_file_location("lethe", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["lethe"] = pkg
    spec.loader.exec_module(pkg)


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    from lethe import flow
    monkeypatch.setattr(flow, "configured_provider", lambda: "")
    return home


class FakeHandle:
    def __init__(self, sink, text):
        self.ok = True
        self.sink = sink
        sink.append(text)

    def edit(self, text):
        self.sink.append(text)
        return {"ok": True}


class FakeCtx:
    def __init__(self, config=None, surface="cli"):
        self.hooks = {}
        self.commands = {}
        self.config = config or {}
        self.surface = surface
        self.posted = []

    def register_hook(self, name, fn, **_):
        self.hooks[name] = fn

    def register_command(self, name, handler, **_):
        self.commands[name] = handler

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def session_surface(self):
        return self.surface

    def post_message(self, text):
        return FakeHandle(self.posted, text)


@pytest.fixture
def ctx():
    import lethe
    c = FakeCtx()
    lethe.register(c)
    return c

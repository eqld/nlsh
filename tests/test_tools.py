"""Tests for nlsh/tools/ (context gatherers)."""

import os

from nlsh.tools import get_minimal_tools, get_tools
from nlsh.tools.availability import ToolAvailability
from nlsh.tools.directory import DirLister
from nlsh.tools.environment import EnvInspector
from nlsh.tools.system import SystemInfo


class TestEnvInspector:
    def test_whitelisted_vars_appear(self, config, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/bash")
        monkeypatch.setenv("TERM", "xterm-256color")
        ctx = EnvInspector(config).get_context()
        assert "SHELL=/bin/bash" in ctx
        assert "TERM=xterm-256color" in ctx

    def test_secret_never_appears(self, config, monkeypatch):
        monkeypatch.setenv("SECRET_LEAK_XYZ", "leakme")
        ctx = EnvInspector(config).get_context()
        assert "leakme" not in ctx
        assert "SECRET_LEAK_XYZ" not in ctx

    def test_path_entry_cap_respected(self, config, monkeypatch):
        huge_path = os.pathsep.join(f"/fake/path/{i}" for i in range(200))
        monkeypatch.setenv("PATH", huge_path)
        ctx = EnvInspector(config).get_context()
        shown_lines = [line for line in ctx.splitlines() if line.startswith("- /fake/path/")]
        assert len(shown_lines) == EnvInspector.MAX_PATH_ENTRIES
        assert "200 total" in ctx


class TestDirLister:
    def test_files_and_dirs_listed_hidden_skipped(self, config, tmp_path, monkeypatch):
        (tmp_path / "visible_file.txt").write_text("hello")
        (tmp_path / "visible_dir").mkdir()
        (tmp_path / ".hidden_file").write_text("secret")
        (tmp_path / ".hidden_dir").mkdir()
        monkeypatch.chdir(tmp_path)

        ctx = DirLister(config).get_context()
        assert "visible_file.txt" in ctx
        assert "visible_dir" in ctx
        assert ".hidden_file" not in ctx
        assert ".hidden_dir" not in ctx

    def test_truncation_line_when_over_max_entries(self, config, tmp_path, monkeypatch):
        for i in range(DirLister.MAX_ENTRIES + 5):
            (tmp_path / f"file_{i:03d}.txt").write_text("x")
        monkeypatch.chdir(tmp_path)

        ctx = DirLister(config).get_context()
        assert "more entries (listing truncated)" in ctx

    def test_no_truncation_when_under_max_entries(self, config, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("x")
        monkeypatch.chdir(tmp_path)

        ctx = DirLister(config).get_context()
        assert "listing truncated" not in ctx

    def test_unreadable_dir_graceful_message(self, config, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        def raise_oserror(path):
            raise OSError("permission denied")

        monkeypatch.setattr("nlsh.tools.directory.scan_visible_entries", raise_oserror)
        ctx = DirLister(config).get_context()
        assert "unable to list directory contents" in ctx


class TestSystemInfo:
    def test_contains_architecture_and_datetime(self, config):
        ctx = SystemInfo(config).get_context()
        assert "Architecture:" in ctx
        assert "Current datetime:" in ctx

    def test_shell_version_probe_success(self, config, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/myshell")

        class FakeResult:
            stdout = "myshell version 5.0\n"

        monkeypatch.setattr("nlsh.tools.system.subprocess.run", lambda *a, **k: FakeResult())
        ctx = SystemInfo(config).get_context()
        assert "myshell version 5.0" in ctx

    def test_shell_version_probe_exception_no_crash(self, config, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/myshell")

        def raise_exc(*a, **k):
            raise Exception("boom")

        monkeypatch.setattr("nlsh.tools.system.subprocess.run", raise_exc)
        ctx = SystemInfo(config).get_context()
        assert "Shell: bash" in ctx
        assert "boom" not in ctx


class TestToolAvailability:
    def test_only_available_tools_listed(self, config, monkeypatch):
        available = {"git", "curl"}

        def fake_which(name):
            return f"/usr/bin/{name}" if name in available else None

        monkeypatch.setattr("nlsh.tools.availability.shutil.which", fake_which)
        ctx = ToolAvailability(config).get_context()
        assert "git" in ctx
        assert "curl" in ctx
        assert "docker" not in ctx
        assert "kubectl" not in ctx


class TestGetToolsHelpers:
    def test_get_tools_returns_all(self, config):
        tools = get_tools(config)
        names = {t.name for t in tools}
        assert names == {"SystemInfo", "EnvInspector", "ToolAvailability", "DirLister"}

    def test_get_minimal_tools_returns_subset(self, config):
        tools = get_minimal_tools(config)
        names = {t.name for t in tools}
        assert names == {"SystemInfo", "ToolAvailability"}

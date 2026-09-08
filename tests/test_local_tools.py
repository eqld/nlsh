"""Tests for nlsh/local_tools.py."""

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from nlsh.local_tools import MAX_OUTPUT_CHARS, SUBPROCESS_TIMEOUT, LocalToolRegistry


@pytest.fixture
def registry():
    return LocalToolRegistry()


class TestDefinitions:
    def test_definitions_shape(self, registry):
        defs = registry.definitions()
        names = {d["function"]["name"] for d in defs}
        assert names == {"list_directory", "read_env_var", "which", "help_snippet", "man_summary"}
        for d in defs:
            assert d["type"] == "function"
            assert "parameters" in d["function"]
            assert "description" in d["function"]


class TestListDirectory:
    def test_files_and_dirs_hidden_skipped(self, registry, tmp_path):
        (tmp_path / "file_a.txt").write_text("hello")
        (tmp_path / "dir_b").mkdir()
        (tmp_path / ".hidden").write_text("secret")

        out = registry.execute("list_directory", json.dumps({"path": str(tmp_path)}))
        assert "file_a.txt" in out
        assert "dir_b/" in out
        assert ".hidden" not in out

    def test_bad_path(self, registry):
        out = registry.execute(
            "list_directory", json.dumps({"path": "/definitely/not/a/real/path/xyz"})
        )
        assert "does not exist" in out.lower()

    def test_path_is_not_a_directory(self, registry, tmp_path):
        f = tmp_path / "a_file.txt"
        f.write_text("x")
        out = registry.execute("list_directory", json.dumps({"path": str(f)}))
        assert "not a directory" in out.lower()

    def test_max_entries_clamping(self, registry, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("x")
        # max_entries way above the 200 cap should be clamped, not error.
        out = registry.execute(
            "list_directory", json.dumps({"path": str(tmp_path), "max_entries": 100000})
        )
        assert "Tool error" not in out
        for i in range(5):
            assert f"f{i}.txt" in out

    def test_max_entries_clamped_low(self, registry, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text("x")
        out = registry.execute(
            "list_directory", json.dumps({"path": str(tmp_path), "max_entries": 0})
        )
        # Clamped to a minimum of 1.
        assert "showing 1" in out

    def test_default_path_is_cwd(self, registry, tmp_path, monkeypatch):
        (tmp_path / "cwd_file.txt").write_text("x")
        monkeypatch.chdir(tmp_path)
        out = registry.execute("list_directory", "{}")
        assert "cwd_file.txt" in out


class TestReadEnvVar:
    def test_secret_never_returned(self, registry, monkeypatch):
        monkeypatch.setenv("SECRET_XYZ", "leakme")
        out = registry.execute("read_env_var", json.dumps({"name": "SECRET_XYZ"}))
        assert "leakme" not in out
        assert "not permitted" in out

    def test_whitelisted_var_returned(self, registry, monkeypatch):
        monkeypatch.setenv("HOME", "/home/tester")
        out = registry.execute("read_env_var", json.dumps({"name": "HOME"}))
        assert "not permitted" not in out
        assert "/home/tester" in out

    def test_invalid_name_rejected(self, registry):
        out = registry.execute("read_env_var", json.dumps({"name": "$(evil)"}))
        assert "not permitted" in out

    def test_path_special_cased(self, registry, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        out = registry.execute("read_env_var", json.dumps({"name": "PATH"}))
        assert "PATH entries" in out

    def test_unset_var_message(self, registry, monkeypatch):
        monkeypatch.delenv("EDITOR", raising=False)
        out = registry.execute("read_env_var", json.dumps({"name": "EDITOR"}))
        assert "is not set" in out


class TestWhich:
    def test_resolves_existing_binary(self, registry, monkeypatch):
        monkeypatch.setattr(
            "nlsh.local_tools.shutil.which", lambda b: "/usr/bin/ls" if b == "ls" else None
        )
        out = registry.execute("which", json.dumps({"binary": "ls"}))
        assert out == "/usr/bin/ls"

    def test_not_found(self, registry, monkeypatch):
        monkeypatch.setattr("nlsh.local_tools.shutil.which", lambda b: None)
        out = registry.execute("which", json.dumps({"binary": "totallymadeup"}))
        assert out == "not found"

    def test_injection_looking_name_rejected(self, registry):
        out = registry.execute("which", json.dumps({"binary": "bad name; rm -rf /"}))
        assert "invalid" in out.lower()

    def test_injection_with_dollar_paren_rejected(self, registry):
        out = registry.execute("which", json.dumps({"binary": "$(evil)"}))
        assert "invalid" in out.lower()


class TestHelpSnippet:
    def test_calls_subprocess_with_argv_list_and_timeout(self, registry, monkeypatch):
        monkeypatch.setattr(
            "nlsh.local_tools.shutil.which", lambda b: "/usr/bin/ls" if b == "ls" else None
        )
        mock_run = MagicMock(return_value=MagicMock(stdout="usage: ls [-@ABC]", stderr=""))
        monkeypatch.setattr("nlsh.local_tools.subprocess.run", mock_run)

        out = registry.execute("help_snippet", json.dumps({"binary": "ls"}))

        assert "usage: ls" in out
        call = mock_run.call_args
        assert call.args[0] == ["/usr/bin/ls", "--help"]
        assert call.kwargs["timeout"] == SUBPROCESS_TIMEOUT
        assert "shell" not in call.kwargs

    def test_falls_back_to_dash_h(self, registry, monkeypatch):
        monkeypatch.setattr(
            "nlsh.local_tools.shutil.which", lambda b: "/usr/bin/foo" if b == "foo" else None
        )

        def fake_run(argv, **kwargs):
            if argv[-1] == "--help":
                return MagicMock(stdout="", stderr="")
            return MagicMock(stdout="usage via -h", stderr="")

        monkeypatch.setattr("nlsh.local_tools.subprocess.run", fake_run)
        out = registry.execute("help_snippet", json.dumps({"binary": "foo"}))
        assert "usage via -h" in out

    def test_binary_not_found(self, registry, monkeypatch):
        monkeypatch.setattr("nlsh.local_tools.shutil.which", lambda b: None)
        out = registry.execute("help_snippet", json.dumps({"binary": "nope"}))
        assert out == "not found"

    def test_invalid_binary_name(self, registry):
        out = registry.execute("help_snippet", json.dumps({"binary": "bad;name"}))
        assert "invalid" in out.lower()

    def test_subprocess_exception_handled(self, registry, monkeypatch):
        monkeypatch.setattr(
            "nlsh.local_tools.shutil.which", lambda b: "/usr/bin/ls" if b == "ls" else None
        )

        def raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="ls", timeout=SUBPROCESS_TIMEOUT)

        monkeypatch.setattr("nlsh.local_tools.subprocess.run", raise_timeout)
        out = registry.execute("help_snippet", json.dumps({"binary": "ls"}))
        assert "Tool error" in out

    def test_output_truncated_to_max_output_chars(self, registry, monkeypatch):
        monkeypatch.setattr(
            "nlsh.local_tools.shutil.which", lambda b: "/usr/bin/ls" if b == "ls" else None
        )
        huge = "x" * (MAX_OUTPUT_CHARS * 3)
        monkeypatch.setattr(
            "nlsh.local_tools.subprocess.run",
            lambda *a, **k: MagicMock(stdout=huge, stderr=""),
        )
        out = registry.execute("help_snippet", json.dumps({"binary": "ls"}))
        assert len(out) <= MAX_OUTPUT_CHARS + len("\n... [truncated]")
        assert "[truncated]" in out


class TestManSummary:
    def test_calls_subprocess_with_argv_list_no_shell(self, registry, monkeypatch):
        def fake_which(b):
            return "/usr/bin/ls" if b in ("ls", "man") else None

        monkeypatch.setattr("nlsh.local_tools.shutil.which", fake_which)
        mock_run = MagicMock(return_value=MagicMock(stdout="LS(1)  NAME\n", stderr=""))
        monkeypatch.setattr("nlsh.local_tools.subprocess.run", mock_run)

        out = registry.execute("man_summary", json.dumps({"binary": "ls"}))

        assert "LS(1)" in out
        call = mock_run.call_args
        assert call.args[0] == ["man", "ls"]
        assert call.kwargs["timeout"] == SUBPROCESS_TIMEOUT
        assert "shell" not in call.kwargs

    def test_man_not_available(self, registry, monkeypatch):
        def fake_which(b):
            return "/usr/bin/ls" if b == "ls" else None

        monkeypatch.setattr("nlsh.local_tools.shutil.which", fake_which)
        out = registry.execute("man_summary", json.dumps({"binary": "ls"}))
        assert "man is not available" in out

    def test_binary_not_found(self, registry, monkeypatch):
        monkeypatch.setattr("nlsh.local_tools.shutil.which", lambda b: None)
        out = registry.execute("man_summary", json.dumps({"binary": "nope"}))
        assert out == "not found"

    def test_subprocess_exception_handled(self, registry, monkeypatch):
        def fake_which(b):
            return "/usr/bin/ls" if b in ("ls", "man") else None

        monkeypatch.setattr("nlsh.local_tools.shutil.which", fake_which)

        def raise_err(*a, **k):
            raise subprocess.SubprocessError("boom")

        monkeypatch.setattr("nlsh.local_tools.subprocess.run", raise_err)
        out = registry.execute("man_summary", json.dumps({"binary": "ls"}))
        assert "Tool error" in out

    def test_output_truncated(self, registry, monkeypatch):
        def fake_which(b):
            return "/usr/bin/ls" if b in ("ls", "man") else None

        monkeypatch.setattr("nlsh.local_tools.shutil.which", fake_which)
        huge = "y" * (MAX_OUTPUT_CHARS * 3)
        monkeypatch.setattr(
            "nlsh.local_tools.subprocess.run",
            lambda *a, **k: MagicMock(stdout=huge, stderr=""),
        )
        out = registry.execute("man_summary", json.dumps({"binary": "ls"}))
        assert len(out) <= MAX_OUTPUT_CHARS + len("\n... [truncated]")
        assert "[truncated]" in out


class TestExecute:
    def test_unknown_tool(self, registry):
        assert "Unknown tool" in registry.execute("nope", "{}")

    def test_malformed_json(self, registry):
        assert "Invalid arguments" in registry.execute("which", "{not json")

    def test_non_dict_arguments(self, registry):
        assert "Invalid arguments" in registry.execute("which", "[1, 2, 3]")

    def test_empty_arguments_string_defaults_to_empty_dict(self, registry, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out = registry.execute("list_directory", "")
        assert "Tool error" not in out

    def test_none_arguments_defaults_to_empty_dict(self, registry, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out = registry.execute("list_directory", None)
        assert "Tool error" not in out

    def test_handler_exception_caught(self, registry, monkeypatch):
        def raise_exc(**kwargs):
            raise RuntimeError("handler exploded")

        registry._tools["which"]["handler"] = raise_exc
        out = registry.execute("which", json.dumps({"binary": "ls"}))
        assert "Tool error: handler exploded" in out

    def test_handler_type_error_caught(self, registry):
        # `read_env_var` requires `name`; omitting it triggers a TypeError
        # inside the handler call, which execute() must catch gracefully.
        out = registry.execute("read_env_var", json.dumps({}))
        assert "Tool error" in out

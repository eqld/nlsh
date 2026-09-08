"""Tests for nlsh/cli.py main flows.

All generation functions and `execute_command` are mocked except in
`TestExecuteCommand`, where real (harmless, portable) subprocess execution is
the function under test.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nlsh import cli
from nlsh.backends import CommandResult


@pytest.fixture
def config_path(tmp_path):
    """Path to a minimal valid config file, for --config."""
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        "shell: bash\n"
        "backends:\n"
        "  - name: test-backend\n"
        "    url: http://localhost:9999/v1\n"
        "    api_key: dummy-key\n"
        "    model: test-model\n"
        "default_backend: 0\n"
    )
    return str(cfg)


def set_argv(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["nlsh", *args])


def force_no_stdin(monkeypatch):
    """Make `_check_stdin_input()` return None cleanly (simulates a real TTY)."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


class TestVersionAndArgErrors:
    def test_version_flag_exits_zero_and_prints_version(self, monkeypatch, capsys):
        set_argv(monkeypatch, "--version")
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 0
        assert "nlsh version" in captured.out

    def test_no_prompt_and_no_stdin_errors(self, monkeypatch, capsys, config_path):
        force_no_stdin(monkeypatch)
        set_argv(monkeypatch, "--config", config_path)
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 1
        assert "Error: No prompt provided" in captured.out

    def test_print_and_explain_are_mutually_exclusive(self, monkeypatch, capsys, config_path):
        set_argv(monkeypatch, "--config", config_path, "-p", "-e", "list files")
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 1
        assert "cannot be used together" in captured.err


class TestPrintMode:
    def test_print_mode_outputs_bare_command(self, monkeypatch, capsys, config_path):
        force_no_stdin(monkeypatch)
        result = CommandResult(command="ls -la", danger_level=None, raw_response="ls -la")
        monkeypatch.setattr(cli, "generate_command", AsyncMock(return_value=result))
        set_argv(monkeypatch, "--config", config_path, "-p", "list files")
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 0
        assert captured.out.strip() == "ls -la"


class TestConfirmationFlow:
    def test_decline_cancels_execution(self, monkeypatch, capsys, config_path):
        force_no_stdin(monkeypatch)
        result = CommandResult(command="ls -la", danger_level=None, raw_response="ls -la")
        monkeypatch.setattr(cli, "generate_command", AsyncMock(return_value=result))
        monkeypatch.setattr("builtins.input", lambda *_: "n")
        set_argv(monkeypatch, "--config", config_path, "list files")
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 0
        assert "Command execution cancelled" in captured.out

    def test_confirm_executes_command(self, monkeypatch, capsys, config_path):
        force_no_stdin(monkeypatch)
        result = CommandResult(command="ls -la", danger_level=None, raw_response="ls -la")
        monkeypatch.setattr(cli, "generate_command", AsyncMock(return_value=result))
        monkeypatch.setattr("builtins.input", lambda *_: "y")
        monkeypatch.setattr(cli, "execute_command", lambda cmd: (0, "out"))
        set_argv(monkeypatch, "--config", config_path, "list files")
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 0
        assert "Executing: ls -la" in captured.out

    def test_destructive_command_prints_warning_before_confirmation(
        self, monkeypatch, capsys, config_path
    ):
        force_no_stdin(monkeypatch)
        result = CommandResult(
            command="rm -rf /tmp/x", danger_level="destructive", raw_response="rm -rf /tmp/x"
        )
        monkeypatch.setattr(cli, "generate_command", AsyncMock(return_value=result))
        monkeypatch.setattr("builtins.input", lambda *_: "n")
        set_argv(monkeypatch, "--config", config_path, "remove stuff")
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 0
        lines = captured.out.splitlines()
        warn_idx = next(i for i, line in enumerate(lines) if "potentially destructive" in line)
        cancel_idx = next(
            i for i, line in enumerate(lines) if "Command execution cancelled" in line
        )
        assert warn_idx < cancel_idx


class TestEditFlow:
    def test_edit_then_execute_uses_edited_command(self, monkeypatch, capsys, config_path):
        force_no_stdin(monkeypatch)
        result = CommandResult(command="ls -la", danger_level=None, raw_response="ls -la")
        monkeypatch.setattr(cli, "generate_command", AsyncMock(return_value=result))
        answers = iter(["e", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        monkeypatch.setattr(cli, "edit_text_in_editor", lambda *a, **k: "ls -la -h")
        exec_calls = []

        def fake_execute(cmd):
            exec_calls.append(cmd)
            return (0, "")

        monkeypatch.setattr(cli, "execute_command", fake_execute)
        set_argv(monkeypatch, "--config", config_path, "list files")
        code = cli.main()
        assert code == 0
        assert exec_calls == ["ls -la -h"]


class TestRegenerateFlow:
    def test_regenerate_records_declined_command_and_executes_new_one(
        self, monkeypatch, capsys, config_path
    ):
        force_no_stdin(monkeypatch)
        r1 = CommandResult(command="ls -la", danger_level=None, raw_response="ls -la")
        r2 = CommandResult(command="du -sh /tmp", danger_level=None, raw_response="du -sh /tmp")
        monkeypatch.setattr(cli, "generate_command", AsyncMock(return_value=r1))
        regen_mock = AsyncMock(return_value=r2)
        monkeypatch.setattr(cli, "generate_command_regeneration", regen_mock)
        answers = iter(["r", "", "y"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        exec_calls = []

        def fake_execute(cmd):
            exec_calls.append(cmd)
            return (0, "")

        monkeypatch.setattr(cli, "execute_command", fake_execute)
        set_argv(monkeypatch, "--config", config_path, "list files")
        code = cli.main()
        assert code == 0
        assert regen_mock.await_count == 1
        call = regen_mock.call_args
        assert call.args[3] == [{"command": "ls -la", "note": None}]
        assert exec_calls == ["du -sh /tmp"]


class TestExecuteCommand:
    """`execute_command` is the function under test here, so real (harmless,
    portable) subprocess execution is permitted -- this is the one exception
    to the "mock all subprocess calls" rule."""

    def test_successful_command_returns_zero_and_output(self):
        code, output = cli.execute_command("echo hello")
        assert code == 0
        assert output == "hello\n"

    def test_failing_command_returns_nonzero_code(self):
        code, _output = cli.execute_command("exit 3")
        assert code == 3


class TestStdinProcessingMode:
    def test_stdin_mode_prints_processed_result(self, monkeypatch, capsys, config_path):
        monkeypatch.setattr(cli, "_check_stdin_input", lambda: (b"hello", "text/plain"))
        process_mock = AsyncMock(return_value="HELLO")
        monkeypatch.setattr(cli, "process_stdin_input", process_mock)
        set_argv(monkeypatch, "--config", config_path, "summarize it")
        code = cli.main()
        captured = capsys.readouterr()
        assert code == 0
        assert "HELLO" in captured.out


class TestLog:
    def test_writes_valid_json_entry_with_expected_keys(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        backend = SimpleNamespace(name="test-backend", model="test-model", url="http://x")
        cli.log(str(log_path), backend, "sys prompt", "user prompt", "resp text")

        entry = json.loads(log_path.read_text())
        assert entry["backend"] == {
            "name": "test-backend",
            "model": "test-model",
            "url": "http://x",
        }
        assert entry["prompt"] == "user prompt"
        assert entry["system_context"] == "sys prompt"
        assert entry["response"] == "resp text"
        assert "timestamp" in entry
        assert "tool_calls" not in entry

    def test_creates_missing_parent_directory(self, tmp_path):
        log_path = tmp_path / "sub" / "dir" / "log.jsonl"
        backend = SimpleNamespace(name="b", model="m", url="u")
        cli.log(str(log_path), backend, "sys", "prompt", "resp")
        assert log_path.exists()

    def test_includes_tool_calls_when_given(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        backend = SimpleNamespace(name="b", model="m", url="u")
        tool_calls = [{"name": "list_directory", "arguments": {}, "result_chars": 42}]
        cli.log(str(log_path), backend, "sys", "prompt", "resp", tool_calls=tool_calls)

        entry = json.loads(log_path.read_text())
        assert entry["tool_calls"] == tool_calls

    def test_noop_when_log_file_falsy(self, tmp_path):
        backend = SimpleNamespace(name="b", model="m", url="u")
        # Neither call should raise nor create any files.
        cli.log(None, backend, "sys", "prompt", "resp")
        cli.log("", backend, "sys", "prompt", "resp")
        assert list(tmp_path.iterdir()) == []

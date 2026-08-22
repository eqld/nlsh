"""Tests for nlsh/editor.py.

All editor invocations are mocked via `subprocess.run` -- no real editor is
spawned. The mock simulates "the user edited and saved the file" by
rewriting the temp file path passed to it.
"""

import os
import subprocess
from unittest.mock import MagicMock

from nlsh.editor import edit_text_in_editor


def _rewrite_file(new_content):
    """Build a `subprocess.run` replacement that rewrites the temp file path
    passed as `[editor, path]`, simulating a user editing and saving."""

    def fake_run(args, check=True):
        path = args[1]
        with open(path, "w") as f:
            f.write(new_content)
        return MagicMock(returncode=0)

    return fake_run


class TestEditTextInEditor:
    def test_returns_edited_text(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "fake-editor")
        monkeypatch.setattr("nlsh.editor.subprocess.run", _rewrite_file("edited content"))
        result = edit_text_in_editor("original content")
        assert result == "edited content"

    def test_strips_surrounding_whitespace(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "fake-editor")
        monkeypatch.setattr("nlsh.editor.subprocess.run", _rewrite_file("  edited  \n\n"))
        result = edit_text_in_editor("original content")
        assert result == "edited"

    def test_uses_vim_fallback_when_editor_unset(self, monkeypatch):
        monkeypatch.delenv("EDITOR", raising=False)
        captured = {}

        def fake_run(args, check=True):
            captured["editor"] = args[0]
            with open(args[1], "w") as f:
                f.write("content")
            return MagicMock(returncode=0)

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        result = edit_text_in_editor("original")
        assert captured["editor"] == "vim"
        assert result == "content"

    def test_custom_suffix_used_for_temp_file(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "fake-editor")
        captured_path = {}

        def fake_run(args, check=True):
            captured_path["path"] = args[1]
            with open(args[1], "w") as f:
                f.write("edited")
            return MagicMock(returncode=0)

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        edit_text_in_editor("original content", suffix=".sh")
        assert captured_path["path"].endswith(".sh")

    def test_editor_not_found_returns_none(self, monkeypatch, capsys):
        monkeypatch.setenv("EDITOR", "nonexistent-editor")

        def fake_run(args, check=True):
            raise FileNotFoundError()

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        result = edit_text_in_editor("original content")
        assert result is None
        captured = capsys.readouterr()
        assert "not found" in captured.err
        assert "EDITOR" in captured.err

    def test_editor_exit_error_returns_none(self, monkeypatch, capsys):
        monkeypatch.setenv("EDITOR", "fake-editor")

        def fake_run(args, check=True):
            raise subprocess.CalledProcessError(returncode=1, cmd=args)

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        result = edit_text_in_editor("original content")
        assert result is None
        captured = capsys.readouterr()
        assert "exited with error code 1" in captured.err

    def test_emptied_file_returns_none(self, monkeypatch, capsys):
        monkeypatch.setenv("EDITOR", "fake-editor")
        monkeypatch.setattr("nlsh.editor.subprocess.run", _rewrite_file(""))
        result = edit_text_in_editor("original content")
        assert result is None
        captured = capsys.readouterr()
        assert "empty" in captured.err.lower()

    def test_whitespace_only_file_returns_none(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "fake-editor")
        monkeypatch.setattr("nlsh.editor.subprocess.run", _rewrite_file("   \n  \n"))
        result = edit_text_in_editor("original content")
        assert result is None

    def test_temp_file_cleaned_up_after_success(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "fake-editor")
        captured_path = {}

        def fake_run(args, check=True):
            captured_path["path"] = args[1]
            with open(args[1], "w") as f:
                f.write("edited")
            return MagicMock(returncode=0)

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        edit_text_in_editor("original content")
        assert not os.path.exists(captured_path["path"])

    def test_temp_file_cleaned_up_after_editor_not_found(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "nonexistent-editor")
        captured_path = {}

        def fake_run(args, check=True):
            captured_path["path"] = args[1]
            raise FileNotFoundError()

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        edit_text_in_editor("original content")
        assert not os.path.exists(captured_path["path"])

    def test_temp_file_cleaned_up_after_exit_error(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "fake-editor")
        captured_path = {}

        def fake_run(args, check=True):
            captured_path["path"] = args[1]
            raise subprocess.CalledProcessError(returncode=2, cmd=args)

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        edit_text_in_editor("original content")
        assert not os.path.exists(captured_path["path"])

    def test_initial_text_written_before_editing(self, monkeypatch):
        monkeypatch.setenv("EDITOR", "fake-editor")
        seen_initial = {}

        def fake_run(args, check=True):
            with open(args[1]) as f:
                seen_initial["content"] = f.read()
            with open(args[1], "w") as f:
                f.write("edited")
            return MagicMock(returncode=0)

        monkeypatch.setattr("nlsh.editor.subprocess.run", fake_run)
        edit_text_in_editor("the original text")
        assert seen_initial["content"] == "the original text"

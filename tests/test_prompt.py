"""Tests for nlsh/prompt.py."""

import pytest

from nlsh.prompt import PromptBuilder
from nlsh.tools.base import BaseTool


class FakeTool(BaseTool):
    """Minimal BaseTool subclass returning a fixed string."""

    def __init__(self, config=None, text="fixed context", tool_name="FakeTool"):
        super().__init__(config)
        self._text = text
        self._tool_name = tool_name

    def get_context(self):
        return self._text

    @property
    def name(self):
        return self._tool_name


class RaisingTool(BaseTool):
    """A tool whose get_context() raises -- error text should be embedded,
    not propagated, by PromptBuilder._gather_tools_context."""

    def get_context(self):
        raise RuntimeError("boom")


@pytest.fixture
def builder(config):
    return PromptBuilder(config)


class TestBuildSystemPrompt:
    def test_contains_strict_output_rules_and_shell(self, builder):
        sp = builder.build_system_prompt([FakeTool()])
        assert "STRICT OUTPUT RULES" in sp
        assert "bash" in sp

    def test_contains_tool_context(self, builder):
        sp = builder.build_system_prompt([FakeTool(text="my special context")])
        assert "my special context" in sp
        assert "FakeTool" in sp

    def test_structured_variant_mentions_json(self, builder):
        sp = builder.build_system_prompt([FakeTool()], structured=True)
        assert "JSON object" in sp
        assert "danger_level" in sp

    def test_raising_tool_error_embedded_not_raised(self, builder, config):
        sp = builder.build_system_prompt([RaisingTool(config)])
        assert "Error getting context from RaisingTool: boom" in sp

    def test_shell_substitution(self, config, tmp_path):
        cfg = tmp_path / "zsh_config.yml"
        cfg.write_text(
            "shell: zsh\n"
            "backends:\n"
            "  - name: test-backend\n"
            "    url: http://localhost:9999/v1\n"
            "    api_key: dummy-key\n"
            "    model: test-model\n"
        )
        from nlsh.config import Config

        zsh_builder = PromptBuilder(Config(str(cfg)))
        sp = zsh_builder.build_system_prompt([FakeTool()])
        assert "zsh" in sp


class TestMinimalSystemPrompts:
    def test_minimal_system_prompt_has_tool_calling_note(self, builder):
        sp = builder.build_minimal_system_prompt([FakeTool()])
        assert "call them when needed instead of guessing" in sp
        assert "STRICT OUTPUT RULES" in sp

    def test_full_system_prompt_lacks_tool_calling_note(self, builder):
        sp = builder.build_system_prompt([FakeTool()])
        assert "call them when needed instead of guessing" not in sp

    def test_minimal_regeneration_system_prompt(self, builder):
        sp = builder.build_minimal_regeneration_system_prompt([FakeTool()])
        assert "call them when needed instead of guessing" in sp
        assert "DIFFERENT" in sp

    def test_minimal_fixing_system_prompt(self, builder):
        sp = builder.build_minimal_fixing_system_prompt([FakeTool()])
        assert "call them when needed instead of guessing" in sp
        assert "previously suggested" in sp.lower()


class TestBuildFixingSystemPrompt:
    def test_contains_markers(self, builder):
        sp = builder.build_fixing_system_prompt([FakeTool()])
        assert "STRICT OUTPUT RULES" in sp
        assert "previously suggested" in sp.lower()

    def test_structured_variant(self, builder):
        sp = builder.build_fixing_system_prompt([FakeTool()], structured=True)
        assert "danger_level" in sp


class TestBuildRegenerationSystemPrompt:
    def test_contains_markers(self, builder):
        sp = builder.build_regeneration_system_prompt([FakeTool()])
        assert "STRICT OUTPUT RULES" in sp
        assert "DIFFERENT" in sp

    def test_structured_variant(self, builder):
        sp = builder.build_regeneration_system_prompt([FakeTool()], structured=True)
        assert "danger_level" in sp


class TestBuildExplanationSystemPrompt:
    def test_contains_markers(self, builder):
        sp = builder.build_explanation_system_prompt([FakeTool(text="ctx-data")])
        assert "PURPOSE" in sp
        assert "bash" in sp
        assert "ctx-data" in sp


class TestBuildGitCommitSystemPrompt:
    def test_no_language_gives_empty_instruction_line(self, builder):
        sp = builder.build_git_commit_system_prompt()
        assert "Generate the commit message in" not in sp

    def test_language_instruction_included(self, builder):
        sp = builder.build_git_commit_system_prompt(language="Spanish")
        assert "Generate the commit message in Spanish." in sp

    def test_git_commit_regeneration_language(self, builder):
        sp = builder.build_git_commit_regeneration_system_prompt(language="French")
        assert "Generate the commit message in French." in sp

    def test_git_commit_regeneration_no_language(self, builder):
        sp = builder.build_git_commit_regeneration_system_prompt()
        assert "Generate the commit message in" not in sp


class TestStdinProcessingPrompts:
    def test_system_prompt_markers(self, builder):
        sp = builder.build_stdin_processing_system_prompt()
        assert "STDIN" in sp or "pipeline" in sp.lower()

    def test_user_prompt_has_input_markers(self, builder):
        up = builder.build_stdin_processing_user_prompt("some data", "summarize it")
        assert "INPUT_START" in up
        assert "INPUT_END" in up
        assert "some data" in up
        assert "summarize it" in up


class TestBuildFixingUserPrompt:
    def test_contains_failed_command_exit_code_and_output(self, builder):
        up = builder.build_fixing_user_prompt("list files", "ls -z", 127, "ls: invalid option -- z")
        assert "ls -z" in up
        assert "127" in up
        assert "ls: invalid option -- z" in up
        assert "list files" in up


class TestBuildRegenerationUserPrompt:
    def test_without_declined_commands(self, builder):
        up = builder.build_regeneration_user_prompt("find big files", [])
        assert "find big files" in up
        assert "Please generate a command" in up

    def test_with_declined_commands_no_notes(self, builder):
        declined = [{"command": "find . -size +1G"}]
        up = builder.build_regeneration_user_prompt("find big files", declined)
        assert "`find . -size +1G`" in up
        assert "Please generate a different command" in up
        assert "Take the provided feedback into account." not in up

    def test_with_declined_commands_and_notes(self, builder):
        declined = [
            {"command": "find . -size +1G", "note": "too slow"},
            {"command": "du -sh *"},
        ]
        up = builder.build_regeneration_user_prompt("find big files", declined)
        assert "1. `find . -size +1G` (Reason: too slow)" in up
        assert "2. `du -sh *`" in up
        assert "Take the provided feedback into account." in up


class TestGitCommitUserPrompts:
    def test_build_git_commit_user_prompt_basic(self, builder):
        up = builder.build_git_commit_user_prompt("diff --git a/x b/x\n+line")
        assert "diff --git a/x b/x" in up

    def test_build_git_commit_user_prompt_with_files(self, builder):
        up = builder.build_git_commit_user_prompt(
            "diff content", changed_files_content={"foo.py": "print(1)"}
        )
        assert "foo.py" in up
        assert "print(1)" in up

    def test_regeneration_user_prompt_with_declined_messages(self, builder):
        up = builder.build_git_commit_regeneration_user_prompt(
            "diff content", declined_messages=["feat: old message"]
        )
        assert "feat: old message" in up
        assert "diff content" in up

    def test_regeneration_user_prompt_without_declined_messages(self, builder):
        up = builder.build_git_commit_regeneration_user_prompt("diff content")
        assert "diff content" in up
        assert "Previously declined" not in up


class TestLoadPromptFromFile:
    def test_happy_path(self, builder, tmp_path):
        p = tmp_path / "prompt.txt"
        p.write_text("  hello prompt  \n")
        assert builder.load_prompt_from_file(str(p)) == "hello prompt"

    def test_missing_file(self, builder, tmp_path):
        missing = tmp_path / "does_not_exist.txt"
        result = builder.load_prompt_from_file(str(missing))
        assert "Error loading prompt file:" in result

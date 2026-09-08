"""Tests for nlsh/git_commit.py (the nlgc entry point).

Git operations run against real, hermetic temp repositories (local and
isolated from the developer's real gitconfig via
GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM=/dev/null and explicit GIT_AUTHOR_*/
GIT_COMMITTER_* env vars). All OpenAI/backend calls are mocked.
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest

from nlsh import git_commit
from nlsh.git_commit import (
    ContextLengthExceededError,
    EmptyCommitMessageError,
    GitCommandError,
    _prepare_git_data,
    generate_commit_message,
    generate_commit_message_regeneration,
    get_changed_files,
    get_git_diff,
    read_file_content,
    run_git_commit,
)


def make_api_error(cls, message, status_code=400):
    """Construct a real openai.* exception instance (not a mock)."""
    req = httpx.Request("POST", "http://localhost:9999/v1/chat/completions")
    resp = httpx.Response(status_code, request=req)
    return cls(message, response=resp, body=None)


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A real, empty, hermetic git repository, chdir'd into."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Isolate from the developer's real gitconfig, and avoid relying on
    # `git config user.email/name` (which would otherwise require a HOME
    # with a writable gitconfig).
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")

    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)], check=True)
    monkeypatch.chdir(repo_dir)
    return repo_dir


def stage_file(repo_dir, name, content):
    """Write a file under repo_dir and `git add` it."""
    path = repo_dir / name
    path.write_text(content)
    subprocess.run(["git", "add", name], cwd=str(repo_dir), check=True)
    return path


class TestGetGitRoot:
    def test_returns_repo_root(self, git_repo):
        root = git_commit._get_git_root()
        # macOS may resolve tmp_path through a symlink (e.g. /tmp ->
        # /private/tmp); compare resolved paths.
        assert Path(root).resolve() == git_repo.resolve()

    def test_not_a_repository_raises(self, tmp_path, monkeypatch):
        not_a_repo = tmp_path / "not_a_repo"
        not_a_repo.mkdir()
        monkeypatch.chdir(not_a_repo)
        with pytest.raises(GitCommandError, match="git repository"):
            git_commit._get_git_root()


class TestGetGitDiff:
    def test_no_staged_changes_raises_error(self, git_repo):
        # get_git_diff raises RuntimeError("No changes detected...") inside
        # its own try block, which its own `except Exception` clause then
        # re-wraps as GitCommandError -- assert on the actual observable
        # behavior rather than the internal RuntimeError.
        with pytest.raises(GitCommandError, match="No changes detected"):
            get_git_diff(staged=True)

    def test_staged_change_diff_contains_filename(self, git_repo):
        stage_file(git_repo, "foo.txt", "hello\n")
        diff = get_git_diff(staged=True)
        assert "foo.txt" in diff
        assert "+hello" in diff

    def test_all_flag_sees_unstaged_changes_too(self, git_repo):
        path = git_repo / "bar.txt"
        stage_file(git_repo, "bar.txt", "unstaged\n")
        subprocess.run(["git", "commit", "-q", "-m", "add bar"], cwd=str(git_repo), check=True)
        path.write_text("modified\n")
        diff_all = get_git_diff(staged=False)
        assert "bar.txt" in diff_all
        assert "modified" in diff_all


class TestGetChangedFiles:
    def test_returns_staged_file_list(self, git_repo):
        stage_file(git_repo, "foo.txt", "hello\n")
        stage_file(git_repo, "baz.txt", "world\n")
        files = get_changed_files(staged=True)
        assert set(files) == {"foo.txt", "baz.txt"}


class TestRunGitCommit:
    def test_successful_commit_returns_zero_and_commit_exists(self, git_repo):
        stage_file(git_repo, "foo.txt", "hello\n")
        code = run_git_commit("feat: add foo")
        assert code == 0
        log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(git_repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "feat: add foo" in log

    def test_failure_path_prints_stderr_not_none(self, git_repo, monkeypatch, capsys):
        error = subprocess.CalledProcessError(
            returncode=1, cmd=["git", "commit"], output="", stderr="fatal: nothing to commit"
        )

        def fake_run(*args, **kwargs):
            raise error

        monkeypatch.setattr(git_commit.subprocess, "run", fake_run)
        code = run_git_commit("feat: add foo")
        captured = capsys.readouterr()
        assert code == 1
        assert "fatal: nothing to commit" in captured.err
        assert "None" not in captured.err

    def test_failure_without_stderr_shows_exit_code(self, git_repo, monkeypatch, capsys):
        error = subprocess.CalledProcessError(
            returncode=7, cmd=["git", "commit"], output="", stderr=""
        )

        def fake_run(*args, **kwargs):
            raise error

        monkeypatch.setattr(git_commit.subprocess, "run", fake_run)
        code = run_git_commit("feat: add foo")
        captured = capsys.readouterr()
        assert code == 1
        assert "exit code 7" in captured.err


class TestReadFileContent:
    def test_existing_file_returns_content(self, git_repo):
        stage_file(git_repo, "foo.txt", "hello world\n")
        content = read_file_content("foo.txt", str(git_repo))
        assert content == "hello world\n"

    def test_missing_file_returns_none_and_warns(self, git_repo, capsys):
        content = read_file_content("does_not_exist.txt", str(git_repo))
        captured = capsys.readouterr()
        assert content is None
        assert "Warning" in captured.err


class TestPrepareGitData:
    def _args(self, all_flag=False):
        return SimpleNamespace(all=all_flag)

    def test_no_changes_raises_error(self, git_repo):
        # See the comment in TestGetGitDiff -- the underlying RuntimeError is
        # wrapped as GitCommandError by get_git_diff's own except clause.
        # `_main` catches both (GitCommandError, RuntimeError), so either is
        # handled correctly by the CLI either way.
        with pytest.raises(GitCommandError, match="No changes detected"):
            _prepare_git_data(self._args(), include_full_files=True)

    def test_include_full_files_false_returns_no_file_dict(self, git_repo):
        stage_file(git_repo, "foo.txt", "hello\n")
        git_diff, changed_files_content = _prepare_git_data(self._args(), include_full_files=False)
        assert "foo.txt" in git_diff
        assert changed_files_content is None

    def test_include_full_files_true_returns_file_dict(self, git_repo):
        stage_file(git_repo, "foo.txt", "hello content\n")
        _git_diff, changed_files_content = _prepare_git_data(self._args(), include_full_files=True)
        assert changed_files_content == {"foo.txt": "hello content\n"}

    def test_large_file_is_truncated(self, git_repo, capsys):
        big_content = "x" * (100 * 1024 + 500)
        stage_file(git_repo, "big.txt", big_content)
        _git_diff, changed_files_content = _prepare_git_data(self._args(), include_full_files=True)
        truncated = changed_files_content["big.txt"]
        assert truncated.endswith("\n... [TRUNCATED]")
        assert len(truncated) == 100 * 1024 + len("\n... [TRUNCATED]")
        captured = capsys.readouterr()
        assert "large" in captured.err.lower()


def _patch_backend_manager(monkeypatch, response_content=None, side_effect=None):
    """Patch git_commit.BackendManager to return a fake backend whose
    generate_response is an AsyncMock."""
    fake_backend = SimpleNamespace(name="test-backend", model="test-model", url="http://x")
    if side_effect is not None:
        fake_backend.generate_response = AsyncMock(side_effect=side_effect)
    else:
        fake_backend.generate_response = AsyncMock(return_value=response_content)

    fake_manager = MagicMock()
    fake_manager.get_backend.return_value = fake_backend
    monkeypatch.setattr(git_commit, "BackendManager", MagicMock(return_value=fake_manager))
    return fake_backend


class TestGenerateCommitMessage:
    def test_returns_generated_message(self, monkeypatch, config):
        _patch_backend_manager(monkeypatch, response_content="feat: add thing")
        message = generate_commit_message(config, None, "diff content", None, verbose=True)
        assert message == "feat: add thing"

    def test_empty_response_raises_empty_commit_message_error(self, monkeypatch, config):
        _patch_backend_manager(monkeypatch, response_content="")
        with pytest.raises(EmptyCommitMessageError):
            generate_commit_message(config, None, "diff content", None, verbose=True)

    def test_context_length_error_raises_context_length_exceeded(self, monkeypatch, config):
        error = make_api_error(
            openai.BadRequestError,
            "This model's maximum context length is 4096 tokens, context_length_exceeded",
        )
        _patch_backend_manager(monkeypatch, side_effect=error)
        with pytest.raises(ContextLengthExceededError):
            generate_commit_message(config, None, "diff content", None, verbose=True)

    def test_other_bad_request_error_wrapped_as_nlgc_error(self, monkeypatch, config):
        error = make_api_error(openai.BadRequestError, "some other unrelated failure")
        _patch_backend_manager(monkeypatch, side_effect=error)
        with pytest.raises(git_commit.NlgcError):
            generate_commit_message(config, None, "diff content", None, verbose=True)

    def test_language_reaches_system_prompt(self, monkeypatch, config):
        fake_backend = _patch_backend_manager(monkeypatch, response_content="feat: x")
        generate_commit_message(
            config, None, "diff content", None, verbose=True, language="Spanish"
        )
        call = fake_backend.generate_response.call_args
        system_prompt = call.args[1]
        assert "Generate the commit message in Spanish." in system_prompt


class TestGenerateCommitMessageRegeneration:
    def test_declined_messages_reach_user_prompt(self, monkeypatch, config):
        fake_backend = _patch_backend_manager(monkeypatch, response_content="feat: better")
        message = generate_commit_message_regeneration(
            config,
            None,
            "diff content",
            None,
            declined_messages=["feat: worse"],
            verbose=True,
        )
        assert message == "feat: better"
        call = fake_backend.generate_response.call_args
        user_prompt = call.args[0]
        assert "feat: worse" in user_prompt

    def test_empty_response_raises_empty_commit_message_error(self, monkeypatch, config):
        _patch_backend_manager(monkeypatch, response_content="")
        with pytest.raises(EmptyCommitMessageError):
            generate_commit_message_regeneration(
                config, None, "diff content", None, declined_messages=["x"], verbose=True
            )


class TestParseArgs:
    def test_all_flag_help_states_only_staged_is_committed(self, monkeypatch, capsys):
        """--all widens analysis only; the help text must say so.

        run_git_commit always runs `git commit -m <msg>` (no -a), so the help
        must not imply that unstaged changes get committed.
        """
        monkeypatch.setattr(sys, "argv", ["nlgc", "--help"])
        with pytest.raises(SystemExit):
            git_commit.parse_args(["--help"])
        help_text = capsys.readouterr().out
        assert "Only staged changes are committed." in help_text

    def test_all_flag_sets_namespace(self):
        assert git_commit.parse_args(["--all"]).all is True
        assert git_commit.parse_args(["-a"]).all is True
        assert git_commit.parse_args([]).all is False


class TestMainExitCodes:
    """`nlgc` must not rewrite explicit exit codes to the generic failure code.

    Regression test: `main()` used to end in `finally: sys.exit(exit_code)`
    with `exit_code` defaulting to 1, which swallowed argparse's SystemExit(0)
    for --help and SystemExit(2) for a usage error, and the --init success
    path's SystemExit(0).
    """

    def test_help_exits_zero(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["nlgc", "--help"])
        with pytest.raises(SystemExit) as exc:
            git_commit.main()
        assert exc.value.code == 0
        assert "usage:" in capsys.readouterr().out

    def test_unknown_flag_exits_two(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["nlgc", "--definitely-not-a-flag"])
        with pytest.raises(SystemExit) as exc:
            git_commit.main()
        assert exc.value.code == 2

    def test_init_exits_zero_and_creates_config(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "argv", ["nlgc", "--init"])
        with pytest.raises(SystemExit) as exc:
            git_commit.main()
        assert exc.value.code == 0
        # isolated_env points HOME at tmp_path, so this is the real created file.
        assert (tmp_path / ".nlsh" / "config.yml").exists()

    def test_error_path_still_exits_one(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["nlgc"])
        monkeypatch.setattr(git_commit, "_main", MagicMock(side_effect=GitCommandError("boom")))
        with pytest.raises(SystemExit) as exc:
            git_commit.main()
        assert exc.value.code == 1

    def test_success_path_exits_with_main_result(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["nlgc"])
        monkeypatch.setattr(git_commit, "_main", MagicMock(return_value=0))
        with pytest.raises(SystemExit) as exc:
            git_commit.main()
        assert exc.value.code == 0

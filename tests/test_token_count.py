"""Tests for nlsh/token_count.py (the nlt entry point)."""

import io

import pytest
import tiktoken
from PIL import Image

from nlsh.token_count import (
    count_image_tokens,
    count_text_tokens,
    main,
    parse_args,
    process_file,
    process_stdin,
)


@pytest.fixture(autouse=True, scope="module")
def _require_cl100k_base():
    """tiktoken downloads/caches encodings on first use. Skip gracefully if
    the encoding cannot be loaded (e.g. fully offline CI without a
    pre-warmed cache), per the phase plan's guidance."""
    try:
        tiktoken.get_encoding("cl100k_base")
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"cl100k_base encoding unavailable: {e}")


def _make_png_bytes(size=(28, 28), color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def set_argv(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["nlt", *args])


def force_no_stdin(monkeypatch):
    """Simulate a real TTY so `_check_stdin_input()` returns None."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


class TestCountTextTokens:
    def test_returns_positive_count(self):
        assert count_text_tokens("Hello world", "cl100k_base") > 0

    def test_deterministic_for_same_input(self):
        a = count_text_tokens("The quick brown fox jumps over the lazy dog", "cl100k_base")
        b = count_text_tokens("The quick brown fox jumps over the lazy dog", "cl100k_base")
        assert a == b

    def test_empty_string_is_zero_tokens(self):
        assert count_text_tokens("", "cl100k_base") == 0

    def test_invalid_encoding_raises_value_error(self):
        with pytest.raises(ValueError, match="Error with encoding"):
            count_text_tokens("Hello world", "not-a-real-encoding")


class TestCountImageTokens:
    def test_28x28_image_matches_formula(self):
        # 28x28 at 14px patches -> 2x2 = 4 patches; 85 base + 4 = 89.
        data = _make_png_bytes(size=(28, 28))
        assert count_image_tokens(data) == 89

    def test_non_multiple_of_patch_size_ceils(self):
        # 15x15 -> ceil(15/14) = 2 per dimension -> 4 patches; 85 + 4 = 89.
        data = _make_png_bytes(size=(15, 15))
        assert count_image_tokens(data) == 89

    def test_larger_image_more_tokens(self):
        small = count_image_tokens(_make_png_bytes(size=(28, 28)))
        large = count_image_tokens(_make_png_bytes(size=(280, 280)))
        assert large > small

    def test_malformed_image_raises_value_error(self):
        with pytest.raises(ValueError, match="Error processing image"):
            count_image_tokens(b"not actually an image")


class TestProcessFile:
    def test_text_file(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Hello world")
        tokens, file_type = process_file(str(f), "cl100k_base")
        assert file_type == "text"
        assert tokens == count_text_tokens("Hello world", "cl100k_base")

    def test_image_file(self, tmp_path):
        f = tmp_path / "pic.png"
        f.write_bytes(_make_png_bytes())
        tokens, file_type = process_file(str(f), "cl100k_base")
        assert file_type == "image"
        assert tokens == 89

    def test_empty_file_is_zero_text_tokens(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        tokens, file_type = process_file(str(f), "cl100k_base")
        assert (tokens, file_type) == (0, "text")

    def test_missing_file_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="File not found"):
            process_file(str(missing), "cl100k_base")


class TestProcessStdin:
    def test_text_stdin(self):
        tokens, data_type = process_stdin(b"Hello world", "cl100k_base")
        assert data_type == "text"
        assert tokens == count_text_tokens("Hello world", "cl100k_base")

    def test_image_stdin(self):
        tokens, data_type = process_stdin(_make_png_bytes(), "cl100k_base")
        assert data_type == "image"
        assert tokens == 89

    def test_empty_stdin_is_zero_text_tokens(self):
        assert process_stdin(b"", "cl100k_base") == (0, "text")


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.files is None
        assert args.encoding == "cl100k_base"
        assert args.verbose is False

    def test_multiple_files_appended(self):
        args = parse_args(["-f", "a.txt", "-f", "b.txt"])
        assert args.files == ["a.txt", "b.txt"]

    def test_verbose_flag(self):
        args = parse_args(["-v"])
        assert args.verbose is True

    def test_encoding_override(self):
        args = parse_args(["--encoding", "o200k_base"])
        assert args.encoding == "o200k_base"


class TestMain:
    def test_file_input_prints_token_count(self, monkeypatch, capsys, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Hello world")
        force_no_stdin(monkeypatch)
        set_argv(monkeypatch, "-f", str(f))
        code = main()
        captured = capsys.readouterr()
        assert code == 0
        assert captured.out.strip() == str(count_text_tokens("Hello world", "cl100k_base"))

    def test_verbose_mode_prints_breakdown_and_total(self, monkeypatch, capsys, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Hello world")
        force_no_stdin(monkeypatch)
        set_argv(monkeypatch, "-f", str(f), "-v")
        code = main()
        captured = capsys.readouterr()
        assert code == 0
        assert str(f) in captured.out
        assert "Total:" in captured.out

    def test_no_input_at_all_errors(self, monkeypatch, capsys):
        force_no_stdin(monkeypatch)
        set_argv(monkeypatch)
        code = main()
        captured = capsys.readouterr()
        assert code == 1
        assert "No input provided" in captured.err

    def test_invalid_encoding_errors(self, monkeypatch, capsys, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Hello world")
        force_no_stdin(monkeypatch)
        set_argv(monkeypatch, "-f", str(f), "--encoding", "not-a-real-encoding")
        code = main()
        captured = capsys.readouterr()
        assert code == 1
        assert "Invalid encoding" in captured.err

    def test_missing_file_reports_error_but_continues(self, monkeypatch, capsys, tmp_path):
        good = tmp_path / "good.txt"
        good.write_text("Hello world")
        missing = tmp_path / "missing.txt"
        force_no_stdin(monkeypatch)
        set_argv(monkeypatch, "-f", str(missing), "-f", str(good))
        code = main()
        captured = capsys.readouterr()
        assert code == 0
        assert "Error processing file" in captured.err
        assert captured.out.strip() == str(count_text_tokens("Hello world", "cl100k_base"))

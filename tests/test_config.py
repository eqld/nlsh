"""Tests for nlsh/config.py."""

import pytest

from nlsh.config import Config, ConfigValidationError


def write_config(tmp_path, text):
    cfg = tmp_path / "config.yml"
    cfg.write_text(text)
    return str(cfg)


class TestDefaults:
    def test_missing_config_file(self, tmp_path):
        cfg = Config(str(tmp_path / "does_not_exist.yml"))
        assert cfg.config_file_found is False
        assert cfg.config["backends"]
        assert cfg.config["default_backend"] == 0
        assert cfg.get_shell() == "bash"

    def test_no_config_path_given(self, tmp_path):
        # HOME is monkeypatched to tmp_path by isolated_env, so no real
        # config file will be found.
        cfg = Config()
        assert cfg.config_file_found is False


class TestLoadingValidYaml:
    def test_shell_and_backends_loaded(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: zsh\n"
            "backends:\n"
            "  - name: b1\n"
            "    url: http://localhost:1234/v1\n"
            "    api_key: dummy-key\n"
            "    model: m1\n"
            "default_backend: 0\n",
        )
        cfg = Config(path)
        assert cfg.config_file_found is True
        assert cfg.get_shell() == "zsh"
        backend = cfg.get_backend()
        assert backend["name"] == "b1"
        assert backend["model"] == "m1"

    def test_stdin_and_nlgc_sections_loaded(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\n"
            "backends:\n"
            "  - name: b1\n"
            "    url: http://localhost:1234/v1\n"
            "    model: m1\n"
            "stdin:\n"
            "  max_tokens: 555\n"
            "nlgc:\n"
            "  language: German\n",
        )
        cfg = Config(path)
        assert cfg.get_stdin_config()["max_tokens"] == 555
        assert cfg.get_nlgc_config()["language"] == "German"


class TestValidationFailures:
    def test_bad_shell(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: powerpc\nbackends:\n  - name: b\n    url: u\n    model: m\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_empty_backends(self, tmp_path):
        path = write_config(tmp_path, "shell: bash\nbackends: []\n")
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_backend_missing_required_field(self, tmp_path):
        path = write_config(tmp_path, "shell: bash\nbackends:\n  - name: b\n    url: u\n")
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_bad_timeout(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n    timeout: -5\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_bad_structured_output(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "    structured_output: nope\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_bad_tool_calling(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "    tool_calling: maybe\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_bad_stdin_max_tokens(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "stdin:\n  max_tokens: -1\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_bad_nlgc_include_full_files(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "nlgc:\n  include_full_files: not-a-bool\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_bad_nlgc_language(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "nlgc:\n  language: ''\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_bad_nlgc_default_backend(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "nlgc:\n  default_backend: -1\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)

    def test_missing_env_var_for_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MY_MISSING_KEY_VAR", raising=False)
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "    api_key: $MY_MISSING_KEY_VAR\n",
        )
        with pytest.raises(ConfigValidationError):
            Config(path)


class TestEnvOverrides:
    def test_nlsh_shell_override(self, tmp_path, monkeypatch):
        path = write_config(
            tmp_path, "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
        )
        monkeypatch.setenv("NLSH_SHELL", "fish")
        cfg = Config(path)
        assert cfg.get_shell() == "fish"

    def test_nlsh_default_backend_override(self, tmp_path, monkeypatch):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b0\n    url: u\n    model: m\n"
            "  - name: b1\n    url: u\n    model: m\n",
        )
        monkeypatch.setenv("NLSH_DEFAULT_BACKEND", "1")
        cfg = Config(path)
        assert cfg.config["default_backend"] == 1
        assert cfg.get_backend()["name"] == "b1"

    def test_nlsh_stdin_max_tokens_override(self, tmp_path, monkeypatch):
        path = write_config(
            tmp_path, "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
        )
        monkeypatch.setenv("NLSH_STDIN_MAX_TOKENS", "42")
        cfg = Config(path)
        assert cfg.get_stdin_config()["max_tokens"] == 42

    def test_nlsh_nlgc_language_override(self, tmp_path, monkeypatch):
        path = write_config(
            tmp_path, "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
        )
        monkeypatch.setenv("NLSH_NLGC_LANGUAGE", "Japanese")
        cfg = Config(path)
        assert cfg.get_nlgc_config()["language"] == "Japanese"

    def test_backend_indexed_api_key_override(self, tmp_path, monkeypatch):
        path = write_config(
            tmp_path, "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
        )
        monkeypatch.setenv("NLSH_BACKEND_0_API_KEY", "indexed-key-value")
        cfg = Config(path)
        assert cfg.get_backend(0)["api_key"] == "indexed-key-value"

    def test_named_api_key_override(self, tmp_path, monkeypatch):
        path = write_config(
            tmp_path, "shell: bash\nbackends:\n  - name: mybackend\n    url: u\n    model: m\n"
        )
        monkeypatch.setenv("MYBACKEND_API_KEY", "named-key-value")
        cfg = Config(path)
        assert cfg.get_backend(0)["api_key"] == "named-key-value"

    def test_dollar_var_expansion_success(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_REAL_KEY_VAR", "a-real-api-key-value")
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "    api_key: $MY_REAL_KEY_VAR\n",
        )
        cfg = Config(path)
        assert cfg.get_backend(0)["api_key"] == "a-real-api-key-value"


class TestStdinAndNlgcBackendPrecedence:
    def test_get_stdin_backend_vision_precedence(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "default_backend: 0\n"
            "stdin:\n  default_backend: 1\n  default_backend_vision: 2\n",
        )
        cfg = Config(path)
        assert cfg.get_stdin_backend(is_vision=True) == 2
        assert cfg.get_stdin_backend(is_vision=False) == 1

    def test_get_stdin_backend_falls_back_to_default_backend(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "default_backend: 3\n"
            "stdin:\n  default_backend_vision: 2\n",
        )
        cfg = Config(path)
        assert cfg.get_stdin_backend(is_vision=False) == 3
        # No vision-specific requested backend when is_vision False even
        # though default_backend_vision is set.

    def test_get_stdin_backend_vision_falls_back_when_no_vision_backend(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "default_backend: 5\n"
            "stdin:\n  default_backend: 1\n",
        )
        cfg = Config(path)
        assert cfg.get_stdin_backend(is_vision=True) == 1

    def test_get_nlgc_backend_precedence(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "default_backend: 0\n"
            "nlgc:\n  default_backend: 4\n",
        )
        cfg = Config(path)
        assert cfg.get_nlgc_backend() == 4

    def test_get_nlgc_backend_falls_back_to_global_default(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "default_backend: 7\n",
        )
        cfg = Config(path)
        assert cfg.get_nlgc_backend() == 7


class TestDeepcopyRegression:
    def test_mutating_instance_config_does_not_affect_fresh_config(self, tmp_path):
        c1 = Config(str(tmp_path / "nonexistent.yml"))
        c1.config["stdin"]["max_tokens"] = 999
        c2 = Config(str(tmp_path / "nonexistent2.yml"))
        assert c2.config["stdin"]["max_tokens"] == 2000

    def test_mutating_backends_list_does_not_leak(self, tmp_path):
        c1 = Config(str(tmp_path / "nonexistent.yml"))
        c1.config["backends"][0]["name"] = "mutated"
        c2 = Config(str(tmp_path / "nonexistent2.yml"))
        assert c2.config["backends"][0]["name"] == "openai"


class TestUpdateConfigNestedMerge:
    def test_nested_merge_preserves_unspecified_defaults(self, tmp_path):
        path = write_config(
            tmp_path,
            "shell: bash\nbackends:\n  - name: b\n    url: u\n    model: m\n"
            "nlgc:\n  language: Italian\n",
        )
        cfg = Config(path)
        nlgc = cfg.get_nlgc_config()
        assert nlgc["language"] == "Italian"
        # include_full_files was not specified in the file; default preserved.
        assert nlgc["include_full_files"] is True

    def test_update_config_direct_call(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        new = {"a": {"y": 20}, "c": 4}
        cfg = Config.__new__(Config)
        cfg._update_config(base, new)
        assert base == {"a": {"x": 1, "y": 20}, "b": 3, "c": 4}


class TestGetBackendFallback:
    def test_invalid_index_falls_back_to_first_backend(self, tmp_path):
        path = write_config(
            tmp_path, "shell: bash\nbackends:\n  - name: only\n    url: u\n    model: m\n"
        )
        cfg = Config(path)
        assert cfg.get_backend(99)["name"] == "only"

"""Tests for nlsh/structured.py."""

import pytest

from nlsh.structured import (
    COMMAND_JSON_SCHEMA,
    build_response_format,
    parse_command_response,
)


class TestParseCommandResponse:
    @pytest.mark.parametrize("danger", ["safe", "caution", "destructive"])
    def test_valid_json_all_danger_levels(self, danger):
        raw = f'{{"command": "ls -la", "danger_level": "{danger}"}}'
        cmd, level = parse_command_response(raw)
        assert cmd == "ls -la"
        assert level == danger

    def test_unknown_danger_level_returns_command_with_none_danger(self):
        cmd, level = parse_command_response('{"command": "ls", "danger_level": "weird"}')
        assert cmd == "ls"
        assert level is None

    def test_non_dict_json_returns_none_none(self):
        assert parse_command_response("[1, 2, 3]") == (None, None)
        assert parse_command_response("42") == (None, None)
        assert parse_command_response('"just a string"') == (None, None)

    def test_invalid_json_returns_none_none(self):
        assert parse_command_response("rm -rf /") == (None, None)
        assert parse_command_response("{not json") == (None, None)

    def test_empty_string_returns_none_none(self):
        assert parse_command_response("") == (None, None)
        assert parse_command_response("   ") == (None, None)

    def test_missing_command_key_returns_none_none(self):
        assert parse_command_response('{"nope": 1}') == (None, None)

    def test_empty_command_returns_none_none(self):
        assert parse_command_response('{"command": "", "danger_level": "safe"}') == (None, None)
        assert parse_command_response('{"command": "   ", "danger_level": "safe"}') == (
            None,
            None,
        )

    def test_non_string_command_returns_none_none(self):
        assert parse_command_response('{"command": 5, "danger_level": "safe"}') == (None, None)
        assert parse_command_response('{"command": null, "danger_level": "safe"}') == (
            None,
            None,
        )

    def test_command_is_stripped(self):
        cmd, level = parse_command_response('{"command": "  ls -la  ", "danger_level": "safe"}')
        assert cmd == "ls -la"
        assert level == "safe"


class TestBuildResponseFormat:
    def test_json_schema_mode(self):
        result = build_response_format("json_schema")
        assert result == {"type": "json_schema", "json_schema": COMMAND_JSON_SCHEMA}

    def test_json_object_mode(self):
        assert build_response_format("json_object") == {"type": "json_object"}

    def test_off_mode_returns_none(self):
        assert build_response_format("off") is None

    def test_unknown_mode_returns_none(self):
        assert build_response_format("nonsense") is None
        assert build_response_format("auto") is None


class TestCommandJsonSchema:
    def test_strict_is_true(self):
        assert COMMAND_JSON_SCHEMA["strict"] is True

    def test_additional_properties_false(self):
        assert COMMAND_JSON_SCHEMA["schema"]["additionalProperties"] is False

    def test_required_matches_properties(self):
        schema = COMMAND_JSON_SCHEMA["schema"]
        assert set(schema["required"]) == set(schema["properties"].keys())

    def test_danger_level_enum(self):
        schema = COMMAND_JSON_SCHEMA["schema"]
        assert schema["properties"]["danger_level"]["enum"] == ["safe", "caution", "destructive"]

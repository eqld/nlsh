"""
Structured output support for nlsh command generation.
"""

import json
from typing import Optional

COMMAND_JSON_SCHEMA = {
    "name": "shell_command",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The single shell command to run, exactly as it should be executed, no markdown.",
            },
            "danger_level": {
                "type": "string",
                "enum": ["safe", "caution", "destructive"],
                "description": (
                    "safe: read-only; caution: modifies files/state reversibly; "
                    "destructive: may delete/overwrite data or affect the system irreversibly."
                ),
            },
        },
        "required": ["command", "danger_level"],
        "additionalProperties": False,
    },
}

# Appended to the system prompt when json_object mode is used (json_object has no
# server-side schema enforcement, so the schema must be described in the prompt).
JSON_OBJECT_INSTRUCTION = (
    "\n\nRespond with a JSON object exactly matching this schema: "
    '{"command": "<the shell command>", "danger_level": "safe|caution|destructive"}. '
    "Output only the JSON object, nothing else."
)


def build_response_format(mode: str) -> Optional[dict]:
    """Return the response_format kwarg value for a given structured output mode."""
    if mode == "json_schema":
        return {"type": "json_schema", "json_schema": COMMAND_JSON_SCHEMA}
    if mode == "json_object":
        return {"type": "json_object"}
    return None


def parse_command_response(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Parse a structured command response.

    Returns:
        (command, danger_level) on success, (None, None) if the content is not
        valid JSON matching the schema (caller should fall back to plain text).
    """
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    command = data.get("command")
    danger = data.get("danger_level")
    if not isinstance(command, str) or not command.strip():
        return None, None
    if danger not in ("safe", "caution", "destructive"):
        danger = None
    return command.strip(), danger

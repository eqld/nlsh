"""
Local read-only tools exposed to the LLM via OpenAI function calling.

The registry interface (definitions() / execute()) is intentionally transport-
agnostic so that an MCP-backed registry can be added later (follow-up work).

Security posture: every tool here is read-only, validates its own arguments
(never trusting the JSON schema alone), caps its output size, never
interpolates arguments into a shell string, and never executes arbitrary
commands. Subprocess use is limited to argv-list form (the shell-invocation
subprocess mode is never enabled), a fixed set of allowed programs, and short
timeouts.
"""

import json
import os
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, List

from nlsh.tools.common import format_path_entries, format_size, scan_visible_entries
from nlsh.tools.environment import EnvInspector

MAX_OUTPUT_CHARS = 4000  # every tool result is truncated to this
SUBPROCESS_TIMEOUT = 3  # seconds

# Whitelist of environment variables the model is allowed to read, plus PATH
# (which gets special handling below). Imported from EnvInspector so the two
# lists never drift apart.
_ENV_WHITELIST = set(EnvInspector.WHITELIST) | {"PATH"}

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BINARY_NAME_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")

_MAX_PATH_ENTRIES = 50


def _truncate(text: str) -> str:
    """Cap text at MAX_OUTPUT_CHARS, noting truncation if applied."""
    if text is None:
        text = ""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + "\n... [truncated]"


def _tool_list_directory(path: str = ".", max_entries: int = 50) -> str:
    """List directory entries (names + type + size only, no file contents)."""
    if not isinstance(path, str) or not path:
        path = "."
    try:
        max_entries = int(max_entries)
    except (TypeError, ValueError):
        max_entries = 50
    max_entries = max(1, min(200, max_entries))

    resolved = os.path.realpath(path)
    if not os.path.exists(resolved):
        return f"Path does not exist: {path}"
    if not os.path.isdir(resolved):
        return f"Path is not a directory: {path}"

    try:
        entries = scan_visible_entries(resolved)
    except OSError as e:
        return f"Tool error: {e}"

    entries.sort(key=lambda e: e.name)
    total = len(entries)
    shown = entries[:max_entries]

    lines = [f"Directory listing for {resolved} ({total} entries, showing {len(shown)}):"]
    for e in shown:
        try:
            if e.is_dir(follow_symlinks=False):
                lines.append(f"{e.name}/")
            else:
                try:
                    size = format_size(e.stat(follow_symlinks=False).st_size)
                except OSError:
                    size = "?"
                lines.append(f"{e.name}\t{size}")
        except OSError:
            lines.append(f"{e.name}\t?")

    if total > len(shown):
        lines.append(f"... ({total - len(shown)} more entries not shown)")

    return _truncate("\n".join(lines))


def _tool_read_env_var(name: str) -> str:
    """Read a whitelisted environment variable."""
    if not isinstance(name, str) or not _ENV_NAME_RE.match(name):
        return f"Access to environment variable '{name}' is not permitted."

    if name not in _ENV_WHITELIST:
        return f"Access to environment variable '{name}' is not permitted."

    if name == "PATH":
        lines = format_path_entries(_MAX_PATH_ENTRIES)
        return _truncate("\n".join(lines))

    value = os.environ.get(name)
    if value is None:
        return f"{name} is not set."
    return _truncate(f"{name}={value}")


def _tool_which(binary: str) -> str:
    """Resolve a binary name to a path on PATH."""
    if not isinstance(binary, str) or not _BINARY_NAME_RE.match(binary):
        return "Invalid binary name."
    resolved = shutil.which(binary)
    return resolved if resolved else "not found"


def _tool_help_snippet(binary: str) -> str:
    """Run `<binary> --help` (falling back to `-h`) and return capped output."""
    if not isinstance(binary, str) or not _BINARY_NAME_RE.match(binary):
        return "Invalid binary name."

    resolved = shutil.which(binary)
    if not resolved:
        return "not found"

    def _run(flag: str):
        try:
            return subprocess.run(  # noqa: S603
                [resolved, flag],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as e:
            return e

    result = _run("--help")
    output = ""
    if not isinstance(result, Exception):
        output = (result.stdout or "") + (result.stderr or "")

    if isinstance(result, Exception) or not output.strip():
        result2 = _run("-h")
        if not isinstance(result2, Exception):
            output = (result2.stdout or "") + (result2.stderr or "")
        elif isinstance(result, Exception):
            return f"Tool error: {result2}"

    if not output.strip():
        return "No help output available."

    return _truncate(output)


def _tool_man_summary(binary: str) -> str:
    """Run `man <binary>` (with pagers disabled) and return capped output."""
    if not isinstance(binary, str) or not _BINARY_NAME_RE.match(binary):
        return "Invalid binary name."

    resolved = shutil.which(binary)
    if not resolved:
        return "not found"

    if not shutil.which("man"):
        return "man is not available on this system."

    try:
        result = subprocess.run(  # noqa: S603, S607
            ["man", binary],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            env={**os.environ, "MANPAGER": "cat", "PAGER": "cat"},
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"Tool error: {e}"

    output = (result.stdout or "") + (result.stderr or "")
    if not output.strip():
        return "No man page available."

    return _truncate(output)


class LocalToolRegistry:
    """Registry of local, read-only tools exposed to the LLM.

    Interface (``definitions()`` / ``execute()``) is intentionally minimal and
    transport-agnostic so a future MCP-backed registry can implement the same
    contract without redesigning callers.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_all()

    def _register(self, definition: dict, handler: Callable[..., str]) -> None:
        name = definition["function"]["name"]
        self._tools[name] = {"definition": definition, "handler": handler}

    def _register_all(self) -> None:
        self._register(
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": (
                        "List entries (names, type, size) in a local directory. "
                        "Does not read file contents. Hidden entries are skipped."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path to list (default: current directory).",
                            },
                            "max_entries": {
                                "type": "integer",
                                "description": "Maximum number of entries to return (1-200, default 50).",
                            },
                        },
                        "required": [],
                    },
                },
            },
            _tool_list_directory,
        )

        self._register(
            {
                "type": "function",
                "function": {
                    "name": "read_env_var",
                    "description": (
                        "Read the value of a whitelisted environment variable. "
                        "Access to non-whitelisted variables (e.g. secrets) is denied."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Environment variable name.",
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
            _tool_read_env_var,
        )

        self._register(
            {
                "type": "function",
                "function": {
                    "name": "which",
                    "description": "Resolve a binary/command name to its path on PATH, if available.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "binary": {
                                "type": "string",
                                "description": "Name of the binary/command to resolve.",
                            },
                        },
                        "required": ["binary"],
                    },
                },
            },
            _tool_which,
        )

        self._register(
            {
                "type": "function",
                "function": {
                    "name": "help_snippet",
                    "description": (
                        "Run `<binary> --help` (falling back to `-h`) and return the "
                        "output, capped in size. The binary must exist on PATH."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "binary": {
                                "type": "string",
                                "description": "Name of the binary/command to get help for.",
                            },
                        },
                        "required": ["binary"],
                    },
                },
            },
            _tool_help_snippet,
        )

        self._register(
            {
                "type": "function",
                "function": {
                    "name": "man_summary",
                    "description": (
                        "Run `man <binary>` and return the output (typically covering "
                        "NAME/SYNOPSIS/DESCRIPTION), capped in size."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "binary": {
                                "type": "string",
                                "description": "Name of the binary/command to look up.",
                            },
                        },
                        "required": ["binary"],
                    },
                },
            },
            _tool_man_summary,
        )

    def definitions(self) -> List[dict]:
        """Return the OpenAI ``tools`` parameter value for all registered tools."""
        return [t["definition"] for t in self._tools.values()]

    def execute(self, name: str, arguments_json: str) -> str:
        """Execute a tool by name with JSON-encoded arguments.

        Never raises; returns an error string on any failure so the tool-call
        loop can continue safely.
        """
        entry = self._tools.get(name)
        if entry is None:
            return f"Unknown tool: {name}"

        try:
            if arguments_json is None or arguments_json == "":
                arguments: Dict[str, Any] = {}
            else:
                arguments = json.loads(arguments_json)
                if not isinstance(arguments, dict):
                    return "Invalid arguments"
        except (json.JSONDecodeError, TypeError):
            return "Invalid arguments"

        handler = entry["handler"]
        try:
            result = handler(**arguments)
        except TypeError as e:
            return f"Tool error: {e}"
        except Exception as e:  # noqa: BLE001 - must never raise out of execute()
            return f"Tool error: {e}"

        if not isinstance(result, str):
            result = str(result)
        return result
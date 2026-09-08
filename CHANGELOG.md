# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Structured command output.** For command generation, regeneration and fixing, backends can now return a JSON object with the command and a `danger_level` (`safe`, `caution`, `destructive`). Controlled per backend with the new `structured_output` key (`auto` | `json_schema` | `json_object` | `off`, default `auto`), which tries strict JSON schema first, then a plain JSON object, then falls back to plain text.
- **Destructive-command warning.** When the model flags a command as destructive, an explicit warning line is printed above the suggestion before the confirmation prompt.
- **On-demand context via tool calling.** Backends supporting OpenAI-style function calling can let the model fetch context only when it needs it, using local read-only tools: `list_directory`, `read_env_var` (whitelisted variables only), `which`, `help_snippet` and `man_summary`. Controlled per backend with the new `tool_calling` key (`auto` | `on` | `off`, default `auto`). The registry is transport-agnostic to allow MCP-backed tools later.
- **Tool-call logging.** With `--log-file`, entries produced via tool calling include a summary of each tool invocation (name, arguments and result length only — never the result content).
- **`ToolAvailability` context tool** reporting which common CLI tools are present on `PATH`, so suggestions match what is actually installed.
- **Richer system context.** `SystemInfo` now also reports the current date/time with timezone (helping with relative-date commands) and the shell version when it can be obtained cheaply.
- **Test suite.** A `tests/` suite covering config, prompts, structured output, image utilities, local tools, backends, and the main `nlsh`/`nlgc`/`nlt` flows, with all OpenAI API calls and subprocess executions mocked.
- **Continuous integration.** A GitHub Actions workflow runs ruff, black and pytest on Ubuntu and macOS across Python 3.9–3.14, plus a `Makefile` with `install-dev`, `lint`, `format`, `typecheck`, `test`, `coverage` and `clean` targets.

### Changed

- **Async OpenAI client.** All API calls now use `AsyncOpenAI`, and the blocking connection probe that ran at backend initialization was removed, so startup no longer waits on a network round trip.
- **Hardened prompts.** System prompts for command generation, fixing, regeneration, explanation, STDIN processing and commit messages now carry explicit strict-output rules (single-line command, no invented flags, prefer non-destructive variants, never emit secrets) and treat provided input as data rather than instructions.
- **Leaner context.** When tool calling is active, only the cheap context tools (`SystemInfo`, `ToolAvailability`) are sent up front instead of the full context.
- **Directory listing.** Entries are now sorted (directories first, then files, alphabetically) and capped at 50 entries with an explicit truncation note.
- **Packaging consolidated into `pyproject.toml`.** `setup.py` was removed, dependencies are split into `requirements.txt` and `requirements-dev.txt` (with a `dev` extra), `openai>=1.40.0` is required, the minimum supported Python is 3.9, and ruff, black, mypy and pytest are configured centrally.
- **Internal refactoring.** Shared LLM generation logic, prompt rule blocks and tool helpers were extracted into common helpers; confirmation and fix state now use an enum and a dataclass instead of magic strings and dicts.
- **Clearer `nlgc -a/--all` help text.** The flag widens which changes are *analyzed*; the commit itself is always `git commit -m <message>` and therefore only ever includes staged changes. The help text now says so explicitly.
- **CI installs pinned lint tools** from `requirements-dev.txt` instead of an unpinned `pip install ruff black`, so an unrelated upstream release can no longer break the build, and now runs `mypy nlsh/` as well. `types-PyYAML` was added to the development dependencies.
- **Type annotations** were added or corrected across the codebase (`Config.DEFAULT_CONFIG`, `Config.config_file_path`, `BackendManager.backends`, `log()`'s optional `log_file`, the `Optional` prompt-builder defaults, `DirLister._format_file_info`, `format_size`, `get_backend_image_size_limit`, and the `tools` helpers). `mypy nlsh/` is now clean.

### Fixed

- **`nlgc` exit codes.** `main()` ended in `finally: sys.exit(exit_code)` with `exit_code` defaulting to `1`, which discarded any in-flight `SystemExit`. As a result `nlgc --help` and a *successful* `nlgc --init` both reported failure (1), and an invalid flag returned 1 instead of argparse's 2. Explicit exits are now propagated unchanged, matching `nlsh` and `nlt`.
- **`format_size` could return `None`.** Its unit loop had no fallback `return`, so an input that fell through (e.g. a negative size) yielded `None`, which callers interpolated into directory listings as the literal `"None"`.
- **Crash on a null model response.** `generate_response` called `.strip()` directly on `choices[0].message.content`, which is optional in the API schema; a tool-call-only or content-filtered response raised `AttributeError` instead of returning the "no response generated" error.
- **`get_backend_image_size_limit(None)` raised `AttributeError`.** `Config.get_backend()` may legitimately return `None`; the default limit is now used instead.
- `DirLister._format_file_info` was annotated as returning `dict[str, str]` while it actually returns `None` for unreadable entries and stores a `bool` under `is_dir`.
- Renamed loop variables that shadowed an enclosing `except ... as e` binding (in `local_tools._tool_list_directory`) and an `Optional` config variable (in `BackendManager.get_vision_capable_backend`).
- `execute_command` now always returns the `(exit code, output)` tuple, including on its error paths.
- Pressing `Ctrl+C` while a generated command runs interrupts only that command instead of terminating `nlsh` itself.
- `nlgc` captures and reports `git commit` output, falling back to the exit code when stderr is empty.
- Default configuration is deep-copied, so loading a config file can no longer mutate the built-in defaults.
- Environment-variable overrides no longer raise when a backend entry has no `name`.
- `nlgc` determines its verbosity from parsed arguments instead of inspecting `sys.argv` directly.
- Removed duplicate imports and other minor code cleanups.

### Removed

- The legacy `test_stdin_feature.sh` script, superseded by the `tests/` suite.

### Security

- **Environment-variable whitelisting.** Only a fixed, whitelisted set of environment variables (plus a capped `PATH` preview) is ever gathered and sent to the LLM; arbitrary variables, including secrets, are no longer collected.
- **Read-only model tools.** Tools callable by the model cannot modify state: they validate their own arguments, never interpolate arguments into a shell string, run subprocesses only as argument lists with short timeouts, and cap their output size.
- **Prompt-injection guardrails.** Content piped via STDIN is delimited with explicit markers and the model is instructed to treat it — as well as commands to explain and git diffs/file contents — strictly as data and to ignore instructions embedded within it.

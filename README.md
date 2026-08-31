# Neural Shell (`nlsh`)

[![PyPI Downloads](https://static.pepy.tech/badge/neural-shell)](https://pepy.tech/projects/neural-shell)
[![CI](https://github.com/eqld/nlsh/actions/workflows/ci.yml/badge.svg)](https://github.com/eqld/nlsh/actions/workflows/ci.yml)
[![Awesome](https://camo.githubusercontent.com/2727609d8bfde9ba1a95be1449eb878bfafa4d76789ba05661857e2c8ac70fa1/68747470733a2f2f63646e2e7261776769742e636f6d2f73696e647265736f726875732f617765736f6d652f643733303566333864323966656437386661383536353265336136336531353464643865383832392f6d656469612f62616467652e737667)](https://github.com/deepseek-ai/awesome-deepseek-integration?tab=readme-ov-file#others)

**nlsh** (*Neural Shell*) is an AI-driven command-line assistant that generates shell commands and one-liners tailored to your system context.

## Features

* 🔄 **Multi-Backend LLM Support**\
Configure multiple OpenAI-compatible endpoints (e.g., local Ollama, DeepSeek API, Mistral API) and switch them using -0, -1, etc.
* 🧠 **System-Aware Context**\
Automatically gathers information about your environment (OS, architecture, date/time, shell, available CLI tools, current directory) to generate commands tailored to your system. Only a whitelisted set of environment variables is ever sent to the LLM.
* 🐚 **Shell-Aware Generation**\
Set your shell (bash/zsh/fish) via config/env to ensure syntax compatibility.
* 🛡️ **Safety First**\
Never executes commands automatically, works in interactive confirmation mode.
* 🧩 **Structured Output**\
Backends that support it return a JSON object with the command plus a danger level, so `nlsh` can print a ⚠️ warning before a potentially destructive command. Falls back automatically on backends without structured-output support.
* 🔧 **On-Demand Context via Tool Calling**\
Instead of stuffing everything into the prompt up front, the model can call local read-only functions (directory listings, whitelisted environment variables, `which`, `--help`/`man` output) only when it actually needs them.
* ⚙️ **Configurable**\
YAML configuration for backends and shell preferences.

Requires Python 3.9 or newer.

--------

## Installation

1. Install the package
```bash
pip install neural-shell
```

2. Create a configuration file
```bash
# Option 1: Use the built-in initialization command
nlsh --init
# or
nlgc --init

# Option 2: Manually create the directory and copy the example
mkdir -p ~/.nlsh
cp examples/config.yml ~/.nlsh/config.yml  # Edit this file with your API keys
```

3. Set up your API keys
```bash
# Edit the config file to add your API keys
nano ~/.nlsh/config.yml

# Or set them as environment variables, referenced in the config file
export OPENAI_API_KEY=sk-...
export GROQ_KEY=gsk_...
export DEEPSEEK_API_KEY=...
```

See: https://pypi.org/project/neural-shell/.

PyPI project statistics:
* https://pypistats.org/packages/neural-shell
* https://pepy.tech/projects/neural-shell

If you want to install from source:

1. Clone the repository
```bash
git clone https://github.com/eqld/nlsh.git
cd nlsh
```

2. Install the package
```bash
# Option 1: Editable install with development dependencies (tests, linters)
pip install -e ".[dev]"
# Equivalent, via the requirements file (it already includes `-e .`)
pip install -r requirements-dev.txt

# Option 2: Simple installation
pip install .
```

## Usage

### Command Generation Mode

Basic usage for generating shell commands:
```bash
nlsh find all pdfs modified in the last 2 days and compress them
# Example output:
# Suggested: find . -name "*.pdf" -mtime -2 -exec tar czvf archive.tar.gz {} +
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: find . -name "*.pdf" -mtime -2 -exec tar czvf archive.tar.gz {} +
# (command output appears here)

# Edit the suggested command before running:
nlsh list all files in the current directory
# Example output:
# Suggested: ls -la
# [Confirm] Run this command? (y/N/e/r/x) e
# (Opens your $EDITOR with 'ls -la')
# (Edit the command, e.g., to 'ls -l')
# (Save and close editor)
#
# Edited command: ls -l
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: ls -l
# (command output appears here)
```

At the confirmation prompt you can answer:

| Answer | Meaning |
| --- | --- |
| `y` / `yes` | Execute the command |
| anything else (or empty) | Decline — prints `Command execution cancelled` |
| `e` / `edit` | Open the command in `$EDITOR` (falls back to `vim`), then confirm again |
| `r` / `regenerate` | Ask for a different command, optionally with a note |
| `x` / `explain` | Explain the command, then return to the confirmation prompt |

Generate and display commands without executing them using the `-p` or `--print` flag:
```bash
# Generate command without execution
nlsh -p find all PDF files larger than 10MB
# Output: find . -name "*.pdf" -size +10M
```

With verbose mode for reasoning models:
```bash
nlsh -v -2 count lines of code in all javascript files
# Example output:
# Reasoning: To count lines of code in JavaScript files, I can use the 'find' command to locate all .js files,
# then pipe the results to 'xargs wc -l' to count the lines in each file.
# Suggested: find . -name "*.js" -type f | xargs wc -l
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: find . -name "*.js" -type f | xargs wc -l
# (command output appears here)
```

**Note on Command Execution:** `nlsh` executes confirmed commands with your `$SHELL` (falling back to `/bin/sh`) and reads their output using non-blocking I/O with the `select` module. This approach ensures compatibility with a wide range of commands, including those with pipes (`|`) and redirections, and prevents deadlocks that can occur with piped commands where one process might be waiting for input before producing output. While this works well for most commands, highly interactive commands (like those with progress bars or TUI applications) might not render perfectly. Pressing `Ctrl+C` while a command runs interrupts that command (exit code 130) instead of killing `nlsh` itself.

**Note on flag combinations:** `-p/--print` and `-e/--explain` cannot be used together, and neither can be used when input is piped into `nlsh` (STDIN processing mode).

### Destructive Command Warnings

When the backend supports structured output (see [Structured Output](#structured-output)), the model also reports a danger level for the command it generates. If it flags the command as destructive, `nlsh` prints an extra warning line above the suggestion:

```bash
nlsh delete all log files older than 30 days
# Example output:
# ⚠️  The model flagged this command as potentially destructive.
# Suggested: find . -name "*.log" -mtime +30 -delete
# [Confirm] Run this command? (y/N/e/r/x) N
# Command execution cancelled
```

The warning is advisory only — it is produced by the model, not by static analysis, so always review commands yourself. It is shown only for the `destructive` level, and it is not repeated after you edit the command with `e` (the edited command has not been assessed by the model).

### Command Explanation Mode

Get detailed explanations of shell commands using the `-e` or `--explain` flag:

```bash
# Explain complex commands
nlsh -e "find . -name '*.log' -mtime +30 -delete"
# Provides a plain-text breakdown: PURPOSE, WORKFLOW, BREAKDOWN, RISKS, IMPROVEMENTS

# Use with verbose mode for reasoning
nlsh -e -v "tar -czf backup.tar.gz /home/user/documents"
# Shows the AI's reasoning process before providing the explanation
```

### STDIN Processing Mode

`nlsh` can also process input from STDIN and output results directly to STDOUT, making it perfect for use in pipelines:

```bash
# Summarize content from a file
cat document.md | nlsh summarize this in 3 bullet points > summary.txt

# Extract specific information from logs
cat server.log | nlsh find all error messages and list them with timestamps

# Process JSON data
curl -s https://api.example.com/data | nlsh extract all email addresses from this JSON

# Transform text content
echo "hello world" | nlsh convert to uppercase and add exclamation marks

# Analyze code files
cat script.py | nlsh explain what this Python script does and identify any potential issues

# Process CSV data
cat data.csv | nlsh find the top 5 entries by sales amount and format as a table

# Control output length with --max-tokens
cat large_document.txt | nlsh --max-tokens 500 summarize this document briefly
```

#### Image Processing Support

`nlsh` automatically detects and processes image input from STDIN when using vision-capable models:

```bash
# Analyze an image
cat image.jpg | nlsh describe what you see in this image

# Extract text from screenshots
cat screenshot.png | nlsh extract all text from this image and format it as markdown

# Analyze charts and graphs
cat chart.png | nlsh summarize the data trends shown in this chart

# Process multiple images in a pipeline
for img in *.jpg; do
    cat "$img" | nlsh identify the main subject of this image >> results.txt
done

# Use specific backend for image processing
cat diagram.png | nlsh -1 explain this technical diagram step by step
```

**Supported Image Formats:**
- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)
- GIF (`.gif`)
- WebP (`.webp`)

BMP input is detected as an image but is not accepted by the API layer — convert it to one of the formats above first.

**Image Processing Features:**
- Automatic input type detection (text vs. image)
- Configurable backend selection for vision processing
- Support for raw binary, base64 and `data:image/...;base64,` input
- Size validation (per-backend `max_image_size_mb`, 20 MB by default)
- Seamless integration with existing STDIN workflows

**In STDIN processing mode:**
- No command confirmation is required
- Output goes directly to STDOUT for easy piping
- The LLM processes the input content according to your instructions
- Perfect for automation and scripting workflows
- Automatic backend selection based on input type (text vs. image)
- The piped content is treated strictly as data, not as instructions (see [Security](#security))

### Using `nlgc` for Commit Messages

The package also includes `nlgc` (Neural Git Commit) to generate commit messages based on your staged changes:

```bash
# Stage your changes first
git add .

# Generate a commit message (using default backend)
nlgc
# Example output:
# Reading content of 3 changed file(s)...
#
# Suggested commit message:
# --------------------
# feat: add nlgc command for AI-generated commit messages
#
# Implements the nlgc command which analyzes staged git diffs
# and uses an LLM to generate conventional commit messages.
# Includes configuration options and CLI flags to control
# whether full file content is included in the prompt.
# --------------------
# [Confirm] Use this message? (y/N/e/r) y
# Commit successful.

# Generate using a specific backend and exclude full file content
nlgc -1 --no-full-files

# Generate commit message in Spanish
nlgc --language Spanish

# Generate commit message in French using short flag
nlgc -l French

# Edit the suggested message before committing
nlgc
# [Confirm] Use this message? (y/N/e/r) e
# (Opens your $EDITOR with the message)
# (Save and close editor)
#
# Using edited message:
# --------------------
# ...
# --------------------
# Commit with this message? (y/N) y
# Commit successful.
```

`nlgc` analyzes the diff of staged files and, optionally, their full content to generate a conventional commit message. You can confirm (`y`), edit (`e`), or regenerate (`r`) the message. The commit itself is always performed as `git commit -m <message>`, so only staged changes are committed — `-a/--all` widens the *analysis* to all tracked modified files, it does not change which files get committed.

### Using `nlt` for Token Counting

The package also includes `nlt` (Neural Language Tokenizer) to count tokens in text and image inputs:

```bash
# Count tokens from STDIN
echo "Hello world" | nlt
# Output: 3

# Count tokens from files
nlt -f document.txt -f image.jpg
# Output: 2628

# Count tokens with breakdown
nlt -v -f document.txt -f image.jpg
# Output:
# document.txt: 1523
# image.jpg: 1105
# Total: 2628

# Count tokens from both STDIN and files
cat input.txt | nlt -f additional.txt

# Count tokens with custom encoding
cat input.txt | nlt --encoding gpt2
```

`nlt` uses `tiktoken` (the same tokenizer used by OpenAI models) to provide accurate token counts for text, and estimates image tokens from the image dimensions. The default encoding is `cl100k_base`.

--------

## Configuration

### Creating a Configuration File

You have two options to create a configuration file:

1. **Automatic initialization**:
   ```bash
   nlsh --init
   # or
   nlgc --init
   ```
   This will prompt you to choose where to create the config file (if `XDG_CONFIG_HOME` is set) and create a default configuration file with placeholders for API keys.

2. **Manual creation**:
   Create `~/.nlsh/config.yml` manually. Configuration files are looked up in this order: the path given to `--config`, then `~/.nlsh/config.yml`, then `~/.config/nlsh/config.yml`.

A complete, self-documenting reference config ships with the repository at [`examples/config.yml`](examples/config.yml). A shorter annotated example:

```yaml
# Shell used for generated commands. Default: bash.
# Allowed: bash, zsh, fish. Override with env $NLSH_SHELL.
shell: "zsh"

backends:
  # Backend 0 — selected with `nlsh -0`
  - name: "openai"                    # Required. Also enables the <NAME>_API_KEY env var.
    url: "https://api.openai.com/v1"  # Required. OpenAI-compatible base URL.
    model: "gpt-4o-mini"              # Required.
    api_key: $OPENAI_API_KEY          # A "$VAR" value is read from that env var.
    timeout: 120.0                    # Request timeout, seconds. Default: 120.0
                                      # (300.0 for localhost/127.0.0.1/::1/unix:// URLs).
    is_reasoning_model: false          # Default: false. Streams reasoning tokens with -v.
    supports_vision: false             # Default: false. Required for image STDIN input.
    max_image_size_mb: 20.0            # Default: 20.0. Used when supports_vision is true.
    structured_output: auto            # auto (default) | json_schema | json_object | off
    tool_calling: auto                 # auto (default) | on | off

  # Backend 1 — vision-capable, used for image input from STDIN
  - name: "openai-gpt4-vision"
    url: "https://api.openai.com/v1"
    model: "gpt-4o"
    api_key: $OPENAI_API_KEY
    supports_vision: true
    max_image_size_mb: 20.0

  # Backend 2 — local Ollama (no real API key needed)
  - name: "local-ollama"
    url: "http://localhost:11434/v1"
    model: "llama3"
    api_key: "ollama"

  # Backend 3 — reasoning model
  - name: "deepseek-reasoner"
    url: "https://api.deepseek.com/v1"
    model: "deepseek-reasoner"
    api_key: $DEEPSEEK_API_KEY
    is_reasoning_model: true

# Index in the backends list used when no -0..-9 flag is given. Default: 0.
# Override with env $NLSH_DEFAULT_BACKEND.
default_backend: 0

# STDIN processing configuration (optional section).
stdin:
  default_backend: 0          # Backend for text STDIN. Default: null (uses default_backend).
  default_backend_vision: 1   # Backend for image STDIN. Default: null (uses stdin.default_backend,
                              # then default_backend). Should have supports_vision: true.
  max_tokens: 2000            # Max output tokens for STDIN mode. Default: 2000.
                              # Overridden by --max-tokens.

# Configuration for the 'nlgc' (Neural Git Commit) command (optional section).
nlgc:
  include_full_files: true    # Send full content of changed files. Default: true.
                              # Overridden by --full-files / --no-full-files.
  language: null              # Commit message language, e.g. "Spanish". Default: null (English).
                              # Overridden by --language/-l.
  default_backend: null       # Backend for nlgc. Default: null (uses default_backend).
```

Notes on individual keys:

*   `name`, `url` and `model` are the only required fields of a backend; everything else has a default.
*   `api_key` may be a literal value or a `$VAR` reference resolved from the environment. Local endpoints (`localhost`, `127.0.0.1`, `::1`, `unix://`) work without a real key; `"ollama"` and any value starting with `dummy` are accepted as placeholders.
*   `timeout` must be a positive number; `max_image_size_mb` must be positive; `stdin.max_tokens` must be a positive integer; `nlgc.default_backend` must be a non-negative integer or `null`.
*   `is_reasoning_model` lets `nlsh` display the model's reasoning tokens in verbose mode (`-v`). It is enabled automatically when the backend name contains "reason".
*   `structured_output` and `tool_calling` apply to command generation, regeneration and fixing only — they have no effect on explanations, STDIN processing or `nlgc`. See [Structured Output](#structured-output) and [On-Demand Tools](#on-demand-tools).
*   `nlgc.include_full_files` provides more context but uses more tokens. If the context becomes too large for the model, `nlgc` will suggest using `--no-full-files`. Individual files larger than ~100KB are truncated before being added to the prompt.

### Running Without a Configuration File

If you run `nlsh` or `nlgc` without a configuration file, the tools will:
1. Notify you that no configuration file was found
2. Use default settings (bash shell, OpenAI backend)
3. Suggest running with `--init` to create a configuration file

Example:
```
Note: No configuration file found at default locations.
Using default configuration. Run 'nlsh --init' to create a config file.
```

### Environment Variable Overrides

You can override configuration settings using environment variables:

*   `NLSH_SHELL`: Overrides the `shell` setting (e.g., `export NLSH_SHELL=fish`).
*   `NLSH_DEFAULT_BACKEND`: Overrides the `default_backend` index (e.g., `export NLSH_DEFAULT_BACKEND=1`).
*   `NLSH_STDIN_DEFAULT_BACKEND`: Overrides `stdin.default_backend` for text STDIN processing (e.g., `export NLSH_STDIN_DEFAULT_BACKEND=0`).
*   `NLSH_STDIN_DEFAULT_BACKEND_VISION`: Overrides `stdin.default_backend_vision` for image STDIN processing (e.g., `export NLSH_STDIN_DEFAULT_BACKEND_VISION=1`).
*   `NLSH_STDIN_MAX_TOKENS`: Overrides `stdin.max_tokens` for STDIN processing output token limit (e.g., `export NLSH_STDIN_MAX_TOKENS=3000`).
*   `NLSH_NLGC_INCLUDE_FULL_FILES`: Overrides `nlgc.include_full_files` (`true`/`1`/`yes` or `false`/`0`/`no`).
*   `NLSH_NLGC_LANGUAGE`: Overrides `nlgc.language` (e.g., `export NLSH_NLGC_LANGUAGE=Spanish`).
*   `NLSH_NLGC_DEFAULT_BACKEND`: Overrides `nlgc.default_backend` for nlgc backend selection (e.g., `export NLSH_NLGC_DEFAULT_BACKEND=2`).
*   `NLSH_BACKEND_[INDEX]_API_KEY`: Sets the API key for a backend by its index (e.g., `export NLSH_BACKEND_0_API_KEY=sk-...`).
*   `[BACKEND_NAME]_API_KEY`: Sets the API key for a named backend (e.g., `export OPENAI_API_KEY=sk-...` for a backend named `openai`). This takes precedence over both `NLSH_BACKEND_[INDEX]_API_KEY` and `$VAR` references in the config file.

Values that cannot be parsed as integers (for the backend index and token limit overrides) are ignored, leaving the configured value in place.

--------

## Advanced Features

### Command Explanation

You can get a detailed explanation of a suggested command by responding with 'x':

```bash
nlsh find all log files larger than 10MB
# Example output:
# Suggested: find . -name "*.log" -size +10M
# [Confirm] Run this command? (y/N/e/r/x) x
#
# Explanation:
# ----------------------------------------
# PURPOSE: Find log files larger than 10MB below the current directory.
#
# BREAKDOWN:
# - `find .`: start searching from the current directory
# - `-name "*.log"`: match files whose names end in .log
# - `-size +10M`: keep only files larger than 10MB
#
# RISKS: No significant risks. The command only reads the filesystem.
# ----------------------------------------
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: find . -name "*.log" -size +10M
# (command output appears here)
```

This feature helps you understand complex commands before executing them, which is especially useful for learning new shell commands or verifying that a suggested command does what you expect.

### Command Regeneration

You can ask for a different command by responding with 'r':

```bash
nlsh find large files
# Example output:
# Suggested: find . -type f -size +100M
# [Confirm] Run this command? (y/N/e/r/x) r
# Note for regeneration (optional): Use 'du' instead
# Suggested: du -h -d 1 | sort -hr
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: du -h -d 1 | sort -hr
# (command output appears here)
```

When you choose to regenerate a command, you can optionally provide a note explaining why you rejected the previous command or what approach you'd prefer. This note helps the AI understand your requirements better and generate more suitable alternatives.

**How it works:**
- The system uses a special regeneration prompt that includes your original request
- All previously rejected commands are listed with their rejection reasons (if provided)
- The AI receives specific guidance about what didn't work and what you're looking for
- Notes are optional — just press Enter to skip

To encourage more diverse suggestions with each regeneration attempt, the temperature parameter (which controls randomness) is automatically increased by 0.1 for each regeneration, starting from 0.2 and capping at 1.0. This applies to both `nlsh` command generation and `nlgc` commit message generation.

### Command Fixing

You can have `nlsh` automatically fix failed commands by responding with 'y' when prompted after a command fails:

```bash
nlsh find files modified today
# Example output:
# Suggested: find . -mtime 0
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: find . -mtime 0
# find: unknown option -- m
# find: `find .mtime' is not a valid expression
#
# ----------------
# Command execution failed with code 1
# Failed command: find . -mtime 0
# Try to fix? If you confirm, the command output and exit code will be sent to LLM.
# [Confirm] Try to fix this command? (y/N) y
# Suggested: find . -type f -mtime 0
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: find . -type f -mtime 0
# (command output appears here)
```

This feature helps you quickly recover from command errors by:
1. Analyzing the error output and exit code of the failed command
2. Considering your original intent (the natural language prompt)
3. Generating a corrected version of the command or an alternative approach

The LLM receives the original prompt, the failed command, its exit code, and output, allowing it to understand what went wrong and how to fix it. This is especially useful for syntax errors, missing flags, or incorrect parameter formats.

### Structured Output

For command generation, regeneration and fixing, `nlsh` asks the model for a JSON object instead of a bare command:

```json
{"command": "find . -name '*.log' -mtime +30 -delete", "danger_level": "destructive"}
```

The `danger_level` is one of `safe` (read-only), `caution` (modifies files/state reversibly) or `destructive` (may delete/overwrite data or affect the system irreversibly). A `destructive` level triggers the ⚠️ warning described in [Destructive Command Warnings](#destructive-command-warnings). The command itself is always shown and always requires confirmation, regardless of the reported level.

The per-backend `structured_output` key controls how this is requested:

| Value | Behavior |
| --- | --- |
| `auto` (default) | Try `json_schema` first, then `json_object`, then plain text. The first mode that works is remembered for the rest of the run. |
| `json_schema` | Always request strict, schema-validated JSON. If the backend rejects it, fall back to plain text. |
| `json_object` | Always request a plain JSON object (the schema is described in the prompt rather than enforced by the API). |
| `off` | Never request structured output; use the plain-text path. |

Set `structured_output: off` when a backend or proxy mangles or rejects the `response_format` parameter, or when you simply don't want the danger-level annotation. Responses that come back as invalid JSON are transparently treated as plain-text commands, so a misbehaving backend degrades gracefully instead of failing.

Structured output is used only for command generation, regeneration and fixing. Explanations, STDIN processing and `nlgc` always use plain text, and verbose runs (`-v`/`-vv`) use the classic streaming path so reasoning tokens stay visible.

### On-Demand Tools

Instead of packing every piece of context into the prompt up front, backends that support OpenAI-style function calling can let the model request context only when it needs it. When tool calling is active, the up-front context is reduced to the cheap tools (`SystemInfo` and `ToolAvailability`) and the model may call these local functions:

| Tool | What it does |
| --- | --- |
| `list_directory` | Lists entries (name, type, size) of a directory. Skips hidden entries, never reads file contents. 1–200 entries, 50 by default. |
| `read_env_var` | Reads a single **whitelisted** environment variable. Non-whitelisted names (e.g. secrets) are refused. `PATH` returns a capped preview. |
| `which` | Resolves a binary name to its path on `PATH`. |
| `help_snippet` | Runs `<binary> --help` (falling back to `-h`) and returns the output. |
| `man_summary` | Runs `man <binary>` with pagers disabled and returns the output. |

Safety properties of these tools:

* **Read-only.** None of them modify files, environment or system state.
* **No shell.** Subprocesses are invoked with an argument list, never through a shell, so the model cannot inject shell syntax.
* **Validated arguments.** Environment variable and binary names must match strict patterns and, for env vars, the whitelist; invalid input returns an error string instead of executing anything.
* **Capped.** Every result is truncated to 4000 characters, subprocesses time out after 3 seconds, and at most 5 tool-call rounds are performed per request before a final answer is forced.

The per-backend `tool_calling` key controls this feature:

| Value | Behavior |
| --- | --- |
| `auto` (default) | Offer tools; if the backend rejects the `tools` parameter, silently fall back to the regular path for the rest of the run. |
| `on` | Always offer tools; if the backend rejects them, fail with an error suggesting `tool_calling: off`. |
| `off` | Never offer tools; always send the full up-front context. |

Notes:

* Verbose mode (`-v`/`-vv`) always uses the classic path with the full up-front context — tool calling is skipped so reasoning-token streaming is preserved.
* Tool calling applies to command generation, regeneration and fixing only (not explanations, STDIN processing or `nlgc`).
* With `--log-file`, each logged entry includes a `tool_calls` summary listing the tool name, its arguments and the *length* of the result — never the result content itself.
* The tool registry is transport-agnostic by design; MCP-backed tools are a possible future addition.

### System Context Tools

`nlsh` uses a set of system tools to gather context information about your environment. This context is included in the prompt sent to the LLM, enabling it to generate more accurate and relevant shell commands tailored to your specific system.

These tools include:

* **SystemInfo**: Operating system and release, Linux distribution or macOS version, architecture, Python version, the current date/time with timezone (useful for relative-date commands), and the configured shell with its version when it can be determined cheaply.

* **ToolAvailability**: Which common CLI tools (e.g. `git`, `docker`, `jq`, `rg`, `systemctl`) are actually present on your `PATH`, so the model doesn't suggest commands you don't have installed.

* **EnvInspector**: A small **whitelisted** subset of environment variables — `SHELL`, `TERM`, `LANG`, `LC_ALL`, `EDITOR`, `PAGER`, `HOME`, `PWD`, `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `VIRTUAL_ENV`, `CONDA_DEFAULT_ENV` — plus a preview of the first 15 `PATH` entries. No other environment variables are read or sent.

* **DirLister**: The current directory path and its non-hidden entries with type and size (directories first, then files, alphabetically), capped at 50 entries.

The context from these tools is automatically included in the prompts sent to the LLM, requiring no user configuration. When tool calling is active, only `SystemInfo` and `ToolAvailability` are sent up front and the rest is fetched on demand (see [On-Demand Tools](#on-demand-tools)).

### Request Logging

You can log all requests to the LLM and its responses to a file:

```bash
nlsh --log-file ~/.nlsh/logs/requests.log find all python files modified in the last week
```

The log file will contain JSON entries with timestamps, backend information (name, model, URL), the prompt, the system context, and the raw response. Entries generated via tool calling also include a `tool_calls` summary (tool name, arguments, and result length only).

### Verbose Mode

Use `-v` for reasoning tokens and `-vv` for additional debug information:

```bash
# Show reasoning (single verbose)
nlsh -v find all python files modified in the last week
# Example output:
# Reasoning: I need to find Python files that were modified in the last 7 days.
# The command to find files by extension is 'find' with the '-name' option.
# To filter by modification time, I'll use '-mtime -7' which means "modified less than 7 days ago".
# Suggested: find . -name "*.py" -mtime -7
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: find . -name "*.py" -mtime -7
# (command output appears here)

# Show reasoning and debug info (double verbose)
nlsh -vv count lines in python files
# Example output:
# Reasoning: Let's break this down...
# (Plus stack traces and debug info in case of errors)
```

Single verbose mode (`-v`) shows the model's reasoning process, while double verbose mode (`-vv`) additionally displays stack traces and debug information when errors occur. The reasoning tokens are displayed in real-time as they're generated, giving you insight into how the model arrived at its answer.

Verbose runs use the classic streaming path: structured output and tool calling are skipped, and the full system context is sent up front. This means the ⚠️ destructive-command warning does not appear in verbose mode.

### Custom Prompts (`nlsh` only)

Use `--prompt-file` with `nlsh` for complex tasks:

```bash
nlsh --prompt-file migration_task.txt
```

### `nlgc` Specific Options

*   `--full-files`: Forces `nlgc` to include the full content of changed files in the prompt, overriding the `nlgc.include_full_files` config setting.
*   `--no-full-files`: Forces `nlgc` to exclude the full content of changed files from the prompt, overriding the config setting. Useful if you encounter context length errors.
*   `-a`, `--all`: Makes `nlgc` analyze all tracked, modified files, not just the ones staged for commit. The commit itself still includes only staged changes.
*   `--language`, `-l`: Specifies the language for commit message generation (e.g., `--language Spanish`), overriding the `nlgc.language` config setting and `NLSH_NLGC_LANGUAGE` environment variable.

--------

## Security

**Nothing runs without your confirmation**

* Command execution always requires explicit confirmation (`y/N/e/r/x` for `nlsh`, `y/N/e/r` for `nlgc`).
* Commands are only displayed, never executed automatically. You can inspect (`x`) or edit (`e`) any suggestion before running it.
* `nlsh` executes confirmed commands with `subprocess.Popen(..., shell=True)`. This is necessary to interpret pipes, redirections and other shell syntax, but it means a malicious command would run with your privileges if you confirm it. The confirmation step is the primary safeguard — always review suggested commands carefully.

**What gets sent to the LLM**

* Only a whitelisted subset of environment variables is ever included in the context (see [System Context Tools](#system-context-tools)). Arbitrary environment variables — including API tokens and other secrets — are never collected or sent.
* The same whitelist applies to the `read_env_var` tool, so the model cannot read secrets even when it asks for them by name.
* Prompts instruct the model never to include secrets, API keys or passwords in generated commands.
* Directory listings contain names, types and sizes only — file contents are never read for context.

**Model-callable tools are read-only**

* The local tools available to the model (`list_directory`, `read_env_var`, `which`, `help_snippet`, `man_summary`) cannot modify anything.
* They validate their own arguments, never interpolate arguments into a shell string, invoke subprocesses only as argument lists (never with a shell), restrict subprocesses to short timeouts, and cap their output size.

**Prompt-injection guardrails**

* Content piped into `nlsh` is wrapped in explicit `INPUT_START`/`INPUT_END` markers, and the system prompt instructs the model to treat it strictly as data and ignore any instructions embedded in it.
* The same "treat as data" rule is applied to commands passed to `-e/--explain` and to diffs and file contents processed by `nlgc`.
* These are mitigations, not guarantees: a determined injection may still influence a suggestion, which is another reason every command requires confirmation.

**Danger levels are advisory**

* The `danger_level` reported with structured output — and the ⚠️ warning derived from it — comes from the model, not from static analysis. It can be wrong in both directions. Treat it as a hint and review commands yourself.

--------

## Development

If you want to develop or debug `nlsh` locally without installing it system-wide, follow these steps to set up a virtual environment:

### Setting Up a Virtual Environment

```bash
# Clone the repository if you haven't already
git clone https://github.com/eqld/nlsh.git
cd nlsh

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install the package in editable mode with development dependencies
pip install -e ".[dev]"
# Equivalent, via the requirements file (it already includes `-e .`)
# pip install -r requirements-dev.txt
```

### Running the Development Version

Once you have set up your virtual environment and installed the package in development mode, you can run the development version of `nlsh`:

```bash
# Make sure your virtual environment is activated
python -m nlsh.main your prompt here

# Or use the entry points directly
nlsh your prompt here
nlgc
nlt -f somefile.txt
```

### Tests, Linting and Type Checking

```bash
# Run the test suite
pytest -q

# Run a single test file, class or test
pytest tests/test_config.py
pytest tests/test_config.py::TestDefaults
pytest tests/test_config.py::TestDefaults::test_missing_config_file

# Coverage report
pytest --cov=nlsh --cov-report=term-missing

# Lint, format check and type check
ruff check nlsh/
black --check nlsh/
mypy nlsh/
```

The tests mock all OpenAI API calls and all subprocess/shell executions, so they need no network access, no API keys, and never touch your real config (`~/.nlsh/config.yml`) or run real commands.

A `Makefile` wraps the common tasks: `make install-dev`, `make test`, `make coverage`, `make lint`, `make format`, `make typecheck`, `make clean`.

### Continuous Integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pushes to `main`/`master` and on every pull request:

* **lint** job: `ruff check nlsh/` and `black --check nlsh/` on Python 3.12.
* **test** job: installs `requirements-dev.txt` and runs `pytest -q` on a matrix of Ubuntu and macOS × Python 3.9–3.14.

Releases are published to PyPI by [`.github/workflows/python-publish.yml`](.github/workflows/python-publish.yml) when a GitHub release is created.

### Debugging

For debugging, you can use your preferred IDE's debugging tools. For example, with VS Code:

1. Set breakpoints in the code
2. Create a launch configuration in `.vscode/launch.json`. Use `"module": "nlsh.git_commit"` for `nlgc` or `"nlsh.token_count"` for `nlt`, passing flags in `args` instead of a prompt:
   ```json
   {
     "version": "0.2.0",
     "configurations": [
       {
         "name": "Debug nlsh",
         "type": "debugpy",
         "request": "launch",
         "module": "nlsh.main",
         "args": ["Your test prompt"],
         "console": "integratedTerminal",
         "justMyCode": false,
         "env": { "PYTHONPATH": "${workspaceFolder}" }
       }
     ]
   }
   ```
3. Start debugging from the VS Code debug panel

## Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style and what's expected in a pull request. In short: set up a development environment as described above, and make sure `pytest -q` passes and the linters are clean before submitting.

Notable changes are recorded in [CHANGELOG.md](CHANGELOG.md).

--------

## License

MIT © 2025 eqld

--------

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=eqld/nlsh&type=Date)](https://www.star-history.com/#eqld/nlsh&Date)

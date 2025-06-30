# Neural Shell (`nlsh`)

[![PyPI Downloads](https://static.pepy.tech/badge/neural-shell)](https://pepy.tech/projects/neural-shell)

**nlsh** (*Neural Shell*) is an AI-driven command-line assistant that generates shell commands and one-liners tailored to your system context.

## Features

* 🔄 **Multi-Backend LLM Support**\
Configure multiple OpenAI-compatible endpoints (e.g., local Ollama, DeepSeek API, Mistral API) and switch them using -0, -1, etc.
* 🧠 **System-Aware Context**\
Automatically gathers information about your environment to generate commands tailored to your system.
* 🐚 **Shell-Aware Generation**\
Set your shell (bash/zsh/fish/powershell) via config/env to ensure syntax compatibility.
* 🛡️ **Safety First**\
Never executes commands automatically, works in interactive confirmation mode.
* ⚙️ **Configurable**\
YAML configuration for backends and shell preferences.

--------

## Installation

1. Clone the repository
   ```bash
   git clone https://github.com/eqld/nlsh.git
   cd nlsh
   ```

2. Install the package
   ```bash
   # Option 1: Install in development mode with all dependencies
   pip install -r requirements.txt
   pip install -e .
   
   # Option 2: Simple installation
   pip install .
   ```

3. Create a configuration file
   ```bash
   # Option 1: Use the built-in initialization command
   nlsh --init
   # or
   nlgc --init
   
   # Option 2: Manually create the directory and copy the example
   mkdir -p ~/.nlsh
   cp examples/config.yml ~/.nlsh/config.yml  # Edit this file with your API keys
   ```

4. Set up your API keys
   ```bash
   # Edit the config file to add your API keys
   nano ~/.nlsh/config.yml
   
   # Or set them as environment variables
   export OPENAI_API_KEY=sk-...
   export GROQ_KEY=gsk_...
   export DEEPSEEK_API_KEY=...
   ```

It is also available in `pip`:

```bash
pip install neural-shell
```

See: https://pypi.org/project/neural-shell/.

PyPI project statistics:
* https://pypistats.org/packages/neural-shell
* https://pepy.tech/projects/neural-shell

## Usage

### Command Generation Mode

Basic usage for generating shell commands:
```bash
nlsh -1 find all pdfs modified in the last 2 days and compress them
# Example output:
# Suggested: find . -name "*.pdf" -mtime -2 -exec tar czvf archive.tar.gz {} +
# [Confirm] Run this command? (y/N/e/r/x) y 
# Executing:
# (command output appears here)

# Edit the suggested command before running:
nlsh -1 list all files in the current directory
# Example output:
# Suggested: ls -la
# [Confirm] Run this command? (y/N/e/r/x) e
# (Opens your $EDITOR with 'ls -la')
# (Edit the command, e.g., to 'ls -l')
# (Save and close editor)
# Edited command: ls -l
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing: ls -l
# (command output appears here)
```

With verbose mode for reasoning models:
```bash
nlsh -v -2 count lines of code in all javascript files
# Example output:
# Reasoning: To count lines of code in JavaScript files, I can use the 'find' command to locate all .js files,
# then pipe the results to 'xargs wc -l' to count the lines in each file.
# Suggested: find . -name "*.js" -type f | xargs wc -l
# [Confirm] Run this command? (y/N/e/r/x) y 
# Executing:
# (command output appears here)
```

**Note on Command Execution:** `nlsh` executes commands using non-blocking I/O with the `select` module to read from stdout/stderr. This approach ensures compatibility with a wide range of commands, including those with pipes (`|`) and redirections. The non-blocking implementation prevents deadlocks that can occur with piped commands where one process might be waiting for input before producing output. While this works well for most commands, highly interactive commands (like those with progress bars or TUI applications) might not render perfectly.

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
```

In STDIN processing mode:
- No command confirmation is required
- Output goes directly to STDOUT for easy piping
- The LLM processes the input content according to your instructions
- Perfect for automation and scripting workflows

### Using `nlgc` for Commit Messages

The package also includes `nlgc` (Neural Git Commit) to generate commit messages based on your staged changes:

```bash
# Stage your changes first
git add .

# Generate a commit message (using default backend)
nlgc
# Example output:
# Suggested commit message:
# --------------------
# feat: Add nlgc command for AI-generated commit messages
# 
# Implements the nlgc command which analyzes staged git diffs
# and uses an LLM to generate conventional commit messages.
# Includes configuration options and CLI flags to control
# whether full file content is included in the prompt.
# --------------------
# [Confirm] Use this message? (y/N/e/r) y
# Executing: git commit -m "feat: Add nlgc command..."
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
# Using edited message:
# ...
# Commit with this message? (y/N) y
```

`nlgc` analyzes the diff of staged files and, optionally, their full content to generate a conventional commit message. You can confirm, edit (`e`), or regenerate (`r`) the message.

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
   This will prompt you to choose where to create the config file (if XDG_CONFIG_HOME is set) and create a default configuration file with placeholders for API keys.

2. **Manual creation**:
   Create `~/.nlsh/config.yml` manually:

```yaml
shell: "zsh"  # Override with env $NLSH_SHELL
backends:
  - name: "local-ollama"
    url: "http://localhost:11434/v1"
    api_key: "ollama"
    model: "llama3"
  - name: "groq-cloud"
    url: "https://api.groq.com/v1"
    api_key: $GROQ_KEY
    model: "llama3-70b-8192"
  - name: "deepseek-reasoner"
    url: "https://api.deepseek.com/v1"
    api_key: $DEEPSEEK_API_KEY
    model: "deepseek-reasoner"
    is_reasoning_model: true  # Mark as a reasoning model for verbose mode
default_backend: 0

# Configuration for the 'nlgc' (Neural Git Commit) command
# Override with environment variable: NLSH_NLGC_INCLUDE_FULL_FILES (true/false)
nlgc:
  # Whether to include the full content of changed files in the prompt
  # sent to the LLM for commit message generation. Provides more context
  # but increases token usage significantly. Can be overridden with
  # --full-files or --no-full-files flags.
  include_full_files: true
  
  # Language for commit message generation (e.g., "Spanish", "French", "German")
  # Set to null or omit for default behavior (English)
  # Can be overridden with --language/-l flag or NLSH_NLGC_LANGUAGE env var
  language: null
```

*   The `is_reasoning_model` flag is used by `nlsh` to identify models that provide reasoning tokens in their responses. When this flag is set to `true` and verbose mode (`-v`) is enabled, the tool will display the model's reasoning process.
*   The `nlgc.include_full_files` setting controls whether `nlgc` sends the full content of changed files to the LLM by default. This provides more context but uses more tokens. Use the `--full-files` or `--no-full-files` flags with `nlgc` to override this setting for a single run. If the context becomes too large for the model, `nlgc` will suggest using `--no-full-files`. Note that `nlgc` currently truncates individual files larger than ~100KB before adding them to the prompt to help prevent context overflows.

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
*   `NLSH_NLGC_INCLUDE_FULL_FILES`: Overrides `nlgc.include_full_files` (`true` or `false`).
*   `NLSH_NLGC_LANGUAGE`: Overrides `nlgc.language` (e.g., `export NLSH_NLGC_LANGUAGE=Spanish`).
*   `[BACKEND_NAME]_API_KEY`: Sets the API key for a named backend (e.g., `export OPENAI_API_KEY=sk-...`). This takes precedence over `$VAR` references in the config file.
*   `NLSH_BACKEND_[INDEX]_API_KEY`: Sets the API key for a backend by its index (e.g., `export NLSH_BACKEND_0_API_KEY=sk-...`).

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
# This command searches for log files larger than 10MB in the current directory and its subdirectories.
# 
# Breaking it down:
# - `find .` - Starts the find command to search from the current directory (.)
# - `-name "*.log"` - Looks for files with names ending in .log
# - `-size +10M` - Filters for files larger than 10MB
# 
# The command will recursively search through all subdirectories and display the paths of matching files.
# ----------------------------------------
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing:
# (command output appears here)
```

This feature helps you understand complex commands before executing them, which is especially useful for learning new shell commands or verifying that a suggested command does what you expect.

### Command Regeneration

You can ask for a different command by responding with 'r':

```bash
nlsh -i find large files
# Example output:
# Suggested: find . -type f -size +100M
# [Confirm] Run this command? (y/N/e/r/x) r
# Note for regeneration (optional): Use 'du' instead
# Regenerating command...
# Suggested: du -h -d 1 | sort -hr
# [Confirm] Run this command? (y/N/e/r/x) y
# (command output appears here)
```

When you choose to regenerate a command, you can optionally provide a note explaining why you rejected the previous command or what approach you'd prefer. This note helps the AI understand your requirements better and generate more suitable alternatives.

**How it works:**
- The system uses a special regeneration prompt that includes your original request
- All previously rejected commands are listed with their rejection reasons (if provided)
- The AI receives specific guidance about what didn't work and what you're looking for
- Empty notes work exactly like the previous system - just press Enter to skip

To encourage more diverse suggestions with each regeneration attempt, the temperature parameter (which controls randomness) is automatically increased by 0.1 for each regeneration, starting from 0.2 and capping at 1.0. This applies to both `nlsh` command generation and `nlgc` commit message generation.

### Command Fixing

You can have `nlsh` automatically fix failed commands by responding with 'y' when prompted after a command fails:

```bash
nlsh find files modified today
# Example output:
# Suggested: find . -mtime 0
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing:
# find: unknown option -- m
# find: `find .mtime' is not a valid expression
# 
# ----------------
# Command execution failed with code 1
# Failed command: find . -mtime 0
# Try to fix? If you confirm, the command output and exit code will be sent to LLM.
# [Confirm] Try to fix this command? (y/N) y
# Fixing...
# Suggested: find . -type f -mtime 0
# [Confirm] Run this command? (y/N/e/r/x) y
# Executing:
# (command output appears here)
```

This feature helps you quickly recover from command errors by:
1. Analyzing the error output and exit code of the failed command
2. Considering your original intent (the natural language prompt)
3. Generating a corrected version of the command or an alternative approach

The LLM receives the original prompt, the failed command, its exit code, and output, allowing it to understand what went wrong and how to fix it. This is especially useful for syntax errors, missing flags, or incorrect parameter formats.

### System Context Tools

`nlsh` uses a set of system tools to gather context information about your environment. This context is included in the prompt sent to the LLM, enabling it to generate more accurate and relevant shell commands tailored to your specific system.

These tools include:

* **DirLister**: Lists non-hidden files in the current directory with metadata (file type, size, modification time). This helps the LLM understand what files are available in your working directory.

* **EnvInspector**: Reports environment variables (with sensitive information redacted) to ensure compatibility with your system. This includes shell information, PATH entries, and other important environment variables that might affect command execution.

* **SystemInfo**: Provides OS, kernel, and architecture context. This includes information about your operating system, version, distribution (for Linux), architecture, and Python environment, helping the LLM generate commands that are compatible with your system.

The context from these tools is automatically included in every prompt sent to the LLM, requiring no user configuration. This system-aware approach allows `nlsh` to generate commands that are more likely to work correctly on your specific system configuration.

### Request Logging

You can log all requests to the LLM and its responses to a file:

```bash
nlsh --log-file ~/.nlsh/logs/requests.log find all python files modified in the last week
```

The log file will contain JSON entries with timestamps, backend information, prompts, system context, and responses.

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
# (command output appears here)

# Show reasoning and debug info (double verbose)
nlsh -vv count lines in python files
# Example output:
# Reasoning: Let's break this down...
# (Plus stack traces and debug info in case of errors)
```

Single verbose mode (-v) shows the model's reasoning process, while double verbose mode (-vv) additionally displays stack traces and debug information when errors occur. The reasoning tokens are displayed in real-time as they're generated, giving you insight into how the model arrived at its answer.

### Custom Prompts (`nlsh` only)

Use `--prompt-file` with `nlsh` for complex tasks:

```bash
nlsh --prompt-file migration_task.txt
```

### `nlgc` Specific Options

*   `--full-files`: Forces `nlgc` to include the full content of changed files in the prompt, overriding the `nlgc.include_full_files` config setting.
*   `--no-full-files`: Forces `nlgc` to exclude the full content of changed files from the prompt, overriding the config setting. Useful if you encounter context length errors.
*   `-a`, `--all`: Makes `nlgc` consider all tracked, modified files, not just the ones staged for commit.
*   `--language`, `-l`: Specifies the language for commit message generation (e.g., `--language Spanish`), overriding the `nlgc.language` config setting and `NLSH_NLGC_LANGUAGE` environment variable.

--------

## Security

* Command execution requires explicit user confirmation (`y/N/e/r/x` for `nlsh` or `y/N/e/r` for `nlgc`).
* Commands are only displayed and never executed automatically.
* All generated commands are shown to the user before any execution.
* `nlsh` uses `subprocess.Popen` with `shell=True` to execute the generated commands. While necessary for interpreting complex shell syntax, this carries inherent risks if a user confirms a malicious command. The mandatory confirmation step is the primary safeguard against accidental execution of harmful commands. Always review suggested commands carefully.

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

# Install development dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

### Running the Development Version

Once you have set up your virtual environment and installed the package in development mode, you can run the development version of `nlsh`:

```bash
# Make sure your virtual environment is activated
python -m nlsh.main your prompt here

# Or use the entry points directly
nlsh your prompt here
nlgc
```

### Debugging

For debugging, you can use your preferred IDE's debugging tools. For example, with VS Code:

1. Set breakpoints in the code
2. Create a launch configuration in `.vscode/launch.json`:
   ```json
   {
     "version": "0.2.0",
     "configurations": [
       {
         "name": "Debug nlsh",
         "type": "debugpy",
         "request": "launch",
         "module": "nlsh.main", # Or nlsh.git_commit for nlgc
         "args": ["Your test prompt"], # Leave empty for nlgc or provide flags
         "console": "integratedTerminal"
       }
     ]
   }
   ```
3. Start debugging from the VS Code debug panel

## Contributing

PRs welcome! Please make sure to set up a development environment as described above, and ensure all tests pass before submitting a pull request.

--------

## License

MIT © 2025 eqld

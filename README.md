# Neural Shell (`nlsh`)

**nlsh** (*Neural Shell*) is an AI-driven command-line assistant that generates shell commands and one-liners tailored to your system context. It leverages LLMs while respecting your shell environment and system state through read-only inspection tools.

## Features

* 🔄 **Multi-Backend LLM Support**\
Configure multiple OpenAI-compatible endpoints (e.g., local Ollama, Groq, Mistral API) and switch them using -0, -1, etc.
* 🐚 **Shell-Aware Generation**\
Set your shell (bash/zsh/fish/powershell) via config/env to ensure syntax compatibility.
* 🔧 **Read-Only System Tools**\
Augment AI context with tools like history inspection, directory listing, and process monitoring.
* 🛡️ **Safety First**\
Never executes commands automatically. Optional interactive confirmation mode.
* ⚙️ **Configurable**\
YAML configuration for backends, default tools, and shell preferences.

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

3. Create a configuration file (optional)
   ```bash
   mkdir -p ~/.nlsh
   cp examples/config.yml ~/.nlsh/config.yml  # Edit this file with your API keys
   ```

4. Set up your API keys
   ```bash
   # For OpenAI
   export OPENAI_API_KEY=your_api_key_here
   
   # For other backends, see the Configuration section
   ```

In the future it will be available in `pip`:

```bash
pip install nlsh
```

## Usage

Basic usage:
```bash
nlsh -2 find all pdfs modified in the last 2 days and compress them
# Example output:
# find . -name "*.pdf" -mtime -2 -exec tar czvf archive.tar.gz {} +
```

With interactive mode:
```bash
nlsh -i list all processes using port 8080
# Suggested: lsof -i :8080
# [Confirm] Run this command? (y/N) 
```

With verbose mode for reasoning models:
```bash
nlsh -v -2 count lines of code in all javascript files
# Preflight reasoning:
# (reasoning tokens for tool selection)
# Selected tools: DirLister, SystemInfo
# 
# Reasoning: To count lines of code in JavaScript files, I can use the 'find' command to locate all .js files,
# then pipe the results to 'xargs wc -l' to count the lines in each file.
# find . -name "*.js" -type f | xargs wc -l
```

--------

## Configuration

Create `~/.nlsh/config.yml`:

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
tools:
  enabled:
    - ShellHistoryInspector
    - DirLister
    - ProcessSniffer
    - EnvInspector
    - SystemInfo
    - NetworkInfo
```

The `is_reasoning_model` flag is used to identify models that provide reasoning tokens in their responses. When this flag is set to `true` and verbose mode is enabled, the tool will display the model's reasoning process in real-time. If not explicitly set, models with "reason" in their name are automatically detected as reasoning models.

--------

## System Tools

Enhance LLM context with these read-only utilities (enable in config):

| **Tool Name** | **Description** |
| -------- | -------- |
| `ShellHistoryInspector` | Analyzes recent command history to avoid redundant suggestions. |
| `DirLister` | Lists non-hidden files in current directory with basic metadata. |
| `ProcessSniffer` | Identifies running processes that might conflict with generated commands. |
| `EnvInspector` | Reports environment variables (PATH, SHELL, etc.) for compatibility checks. |
| `SystemInfo` | Provides OS, kernel, and architecture context. |
| `NetworkInfo` | Lists open ports and active connections relevant to network commands. |
| `GitRepoInfo` | Supplements context with Git repository information (branch, commits, changes). |

--------

## Advanced Features

### Interactive Mode

Append `-i` to confirm before executing the suggested command:

```bash
nlsh -i delete old log files
# Suggested: find /var/log -name "*.log" -mtime +30 -delete
# [Confirm] Run this command? (y/N/r) y
# Executing: find /var/log -name "*.log" -mtime +30 -delete
# (command output appears here)
```

If you confirm with 'y' or 'yes', the command will be executed directly. If you decline, the command will not be run.

### Command Regeneration

In both interactive mode and follow-up mode, you can ask for a different command by responding with 'r':

```bash
nlsh -i find large files
# Suggested: find . -type f -size +100M
# [Confirm] Run this command? (y/N/r) r
# Regenerating command...
# Suggested: du -h -d 1 | sort -hr
# [Confirm] Run this command? (y/N/r) y
# ...
```

This tells the model not to suggest the same command again and to try a different approach.

### Follow-up Mode

Use `-f` in combination with `-i` to enable follow-up mode, which maintains context between commands:

```bash
nlsh -i -f setup a python virtual environment
# Suggested: python -m venv myenv
# [Confirm] Run this command? (y/N/r) y
# Executing: python -m venv myenv
# ...
# Enter next prompt (Ctrl+C to exit): activate the virtual environment
# Selected tools: EnvInspector, SystemInfo
# Suggested: source myenv/bin/activate
# [Confirm] Run this command? (y/N/r) y
# ...
```

In follow-up mode:
- The tool remembers previous prompts, commands, and their outputs
- You can continue with related prompts without repeating context
- Press Ctrl+C to exit the session

### Intelligent Tool Selection

The tool automatically analyzes your prompt and selects only the tools that are relevant:

```bash
nlsh list files in the current directory
# Selected tools: DirLister
# find . -type f -maxdepth 1

nlsh check if port 8080 is in use
# Selected tools: ProcessSniffer, NetworkInfo
# lsof -i :8080
```

This makes responses faster and more focused by only including relevant system context. The tool selection process is robust and falls back to default tools if needed.

### Tool Management

You can list all available tools and their status:

```bash
nlsh --list-tools
# Available tools:
# - DirLister: enabled
# - EnvInspector: enabled
# - SystemInfo: enabled
# - ShellHistoryInspector: enabled
# - ProcessSniffer: disabled
# - NetworkInfo: disabled
# - GitRepoInfo: disabled
```

You can enable or disable specific tools for a single request:

```bash
nlsh --enable-tool GitRepoInfo show me information about this git repository
```

You can also enable or disable multiple tools:

```bash
nlsh --enable-tool GitRepoInfo --enable-tool ProcessSniffer --disable-tool DirLister show me information about this git repository
```

### Request Logging

You can log all requests to the LLM and its responses to a file:

```bash
nlsh --log-file ~/.nlsh/logs/requests.log find all python files modified in the last week
```

The log file will contain JSON entries with timestamps, backend information, prompts, system context, and responses.

### Verbose Mode

Use `-v` or `--verbose` to display reasoning tokens and tool selection process:

```bash
nlsh -v -2 find all python files modified in the last week
# Preflight reasoning:
# (reasoning tokens for tool selection)
# Selected tools: DirLister, SystemInfo
# 
# Reasoning: I need to find Python files that were modified in the last 7 days.
# The command to find files by extension is 'find' with the '-name' option.
# To filter by modification time, I'll use '-mtime -7' which means "modified less than 7 days ago".
# find . -name "*.py" -mtime -7
```

This is particularly useful with reasoning models, which show their step-by-step thinking process. The reasoning tokens are displayed in real-time as they're generated, giving you insight into how the model arrived at its answer. In verbose mode, both the preflight reasoning (for tool selection) and the command generation reasoning are streamed to STDERR.

### Custom Prompts

Use `--prompt-file` for complex tasks:

```bash
nlsh --prompt-file migration_task.txt
```

--------

## Security

* Tools only perform read-only operations to gather system context.
* Command execution only happens in interactive mode (`-i` flag) and requires explicit user confirmation.
* In non-interactive mode (default), commands are only displayed and never executed automatically.
* All generated commands are shown to the user before any execution.

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

# Or use the entry point directly
nlsh your prompt here
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
         "module": "nlsh.main",
         "args": ["Your test prompt"],
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

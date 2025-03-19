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

```bash
nlsh -2 "Find all PDFs modified in the last 2 days and compress them"
# Example output:
# find . -name "*.pdf" -mtime -2 -exec tar czvf archive.tar.gz {} +
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
  - name: "groq-cloud"
    url: "https://api.groq.com/v1"
    api_key: $GROQ_KEY
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

--------

## Advanced Features

### Interactive Mode

Append `-i` to confirm before executing the suggested command:

```bash
nlsh -i "Delete old log files"
# Suggested: find /var/log -name "*.log" -mtime +30 -delete
# [Confirm] Run this command? (y/N) y
# Executing: find /var/log -name "*.log" -mtime +30 -delete
# (command output appears here)
```

If you confirm with 'y' or 'yes', the command will be executed directly. If you decline, the command will not be run.

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
python -m nlsh.main "Your prompt here"

# Or use the entry point directly
nlsh "Your prompt here"
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
         "type": "python",
         "request": "launch",
         "module": "nlsh.main",
         "args": ["Your test prompt"],
         "console": "integratedTerminal"
       }
     ]
   }
   ```
3. Start debugging from the VS Code debug panel

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=nlsh
```

--------

## Contributing

PRs welcome! Please make sure to set up a development environment as described above, and ensure all tests pass before submitting a pull request.

--------

## License

MIT © 2025 eqld

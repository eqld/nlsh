# Neural Shell (`nlsh`)

**nlsh** (*Neural Shell*) is an AI-driven command-line assistant that generates shell commands and one-liners tailored to your system context.

## Features

* 🔄 **Multi-Backend LLM Support**\
Configure multiple OpenAI-compatible endpoints (e.g., local Ollama, Groq, Mistral API) and switch them using -0, -1, etc.
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
   mkdir -p ~/.nlsh
   cp examples/config.yml ~/.nlsh/config.yml  # Edit this file with your API keys
   ```

4. Set up your API keys

In the future it will be available in `pip`:

```bash
pip install nlsh
```

## Usage

Basic usage:
```bash
nlsh -1 find all pdfs modified in the last 2 days and compress them
# Example output:
# Suggested: find . -name "*.pdf" -mtime -2 -exec tar czvf archive.tar.gz {} +
# [Confirm] Run this command? (y/N/r) y
# Executing:
# (command output appears here)
```

With verbose mode for reasoning models:
```bash
nlsh -v -2 count lines of code in all javascript files
# Example output:
# Reasoning: To count lines of code in JavaScript files, I can use the 'find' command to locate all .js files,
# then pipe the results to 'xargs wc -l' to count the lines in each file.
# Suggested: find . -name "*.js" -type f | xargs wc -l
# [Confirm] Run this command? (y/N/r) y
# Executing:
# (command output appears here)
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
```

The `is_reasoning_model` flag is used to identify models that provide reasoning tokens in their responses. When this flag is set to `true` and verbose mode is enabled, the tool will display the model's reasoning process in real-time. If not explicitly set, models with "reason" in their name are automatically detected as reasoning models.

--------

## Advanced Features

### Command Regeneration

You can ask for a different command by responding with 'r':

```bash
nlsh -i find large files
# Example output:
# Suggested: find . -type f -size +100M
# [Confirm] Run this command? (y/N/r) r
# Regenerating command...
# Suggested: du -h -d 1 | sort -hr
# [Confirm] Run this command? (y/N/r) y
# (command output appears here)
```

This tells the model not to suggest the same command again and to try a different approach.

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
# [Confirm] Run this command? (y/N/r) y
# (command output appears here)

# Show reasoning and debug info (double verbose)
nlsh -vv count lines in python files
# Example output:
# Reasoning: Let's break this down...
# (Plus stack traces and debug info in case of errors)
```

Single verbose mode (-v) shows the model's reasoning process, while double verbose mode (-vv) additionally displays stack traces and debug information when errors occur. The reasoning tokens are displayed in real-time as they're generated, giving you insight into how the model arrived at its answer.

### Custom Prompts

Use `--prompt-file` for complex tasks:

```bash
nlsh --prompt-file migration_task.txt
```

--------

## Security

* Command execution requires explicit user confirmation.
* Commands are only displayed and never executed automatically.
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

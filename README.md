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
2. TODO

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
# [Confirm] Run this command? (y/N)
```

### Custom Prompts

Use `--prompt-file` for complex tasks:

```bash
nlsh --prompt-file migration_task.txt
```

--------

## Security

* Tools only perform read-only operations.
* Command execution never happens without explicit user confirmation.

--------

## Contributing

PRs welcome!

--------

## License

MIT © 2025

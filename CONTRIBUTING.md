# Contributing to Neural Shell (nlsh)

Thanks for your interest in improving `nlsh`! This document covers the practical
details: how to set up a development environment, which checks to run, and what
is expected in a pull request.

## Development setup

Requires Python 3.9 or newer.

```bash
git clone https://github.com/eqld/nlsh.git
cd nlsh

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Editable install with all development dependencies
pip install -e ".[dev]"
# Equivalent, via the requirements file (it already includes `-e .`)
# pip install -r requirements-dev.txt
```

Run the development version:

```bash
python -m nlsh.main your prompt here
# or use the entry points
nlsh your prompt here
nlgc
nlt -f somefile.txt
```

## Code style

The project uses [ruff](https://docs.astral.sh/ruff/) for linting and import
sorting, [black](https://black.readthedocs.io/) for formatting, and
[mypy](https://mypy.readthedocs.io/) for type checking. All three are configured
in `pyproject.toml` (line length 100, target Python 3.9).

```bash
ruff check nlsh/          # lint
black --check nlsh/       # formatting check
black nlsh/               # apply formatting
mypy nlsh/                # type check
```

Or via the `Makefile`:

```bash
make lint        # ruff check + black --check
make format      # ruff check --fix + black
make typecheck   # mypy
```

Guidelines:

* Target Python 3.9 syntax. Builtin generics (`list[str]`, `dict[str, Any]`) and
  `Optional[...]` are fine; avoid `match` statements and runtime `X | Y` unions.
* Keep public functions and classes documented with docstrings in the existing
  Google-ish style (`Args:` / `Returns:` / `Raises:`).
* Don't add new runtime dependencies without a good reason — the runtime set is
  intentionally small (`openai`, `pyyaml`, `tiktoken`, `pillow`).
* Preserve backward compatibility of existing config keys, CLI flags,
  `NLSH_*` environment variables, interactive prompts and exit codes.

## Tests

```bash
pytest -q                                   # whole suite
pytest tests/test_config.py                 # one file
pytest tests/test_config.py::TestDefaults   # one class
pytest tests/test_config.py::TestDefaults::test_missing_config_file
pytest --cov=nlsh --cov-report=term-missing # coverage
# or: make test / make coverage
```

Testing conventions:

* Use `pytest`, `pytest-asyncio` (async mode is enabled automatically) and
  `unittest.mock` — please don't introduce additional test libraries.
* **Mock all OpenAI API calls and all subprocess/shell executions.** Tests must
  not hit the network, require API keys, run real commands, open a real editor,
  or mutate a real git repository.
* The autouse `isolated_env` fixture in `tests/conftest.py` isolates `HOME`,
  `NLSH_*` and `*_API_KEY` variables — keep tests hermetic and don't rely on the
  developer's real `~/.nlsh/config.yml`.
* Tests must pass on both macOS and Linux; guard platform-specific behavior with
  `pytest.mark.skipif`.

## Pull requests

Before opening a PR:

1. `pytest -q` passes.
2. `ruff check nlsh/` and `black --check nlsh/` are clean.
3. `mypy nlsh/` is clean (it currently reports no errors — please keep it that way).
4. New behavior is covered by tests.
5. User-visible changes are reflected in `README.md`, `examples/config.yml`
   (if a config key changed) and `CHANGELOG.md` under `## [Unreleased]`.

Please keep commits focused and write messages in the
[Conventional Commits](https://www.conventionalcommits.org/) style used in this
repository (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, …) —
`nlgc` can generate them for you.

Continuous integration (`.github/workflows/ci.yml`) runs ruff, black and mypy on
Python 3.12 (with the tool versions pinned in `requirements-dev.txt`), and
`pytest -q` on Ubuntu and macOS across Python 3.9–3.14.

## Releases

Maintainers only:

1. The version lives in a single place: `__version__` in `nlsh/__init__.py`.
   `pyproject.toml` reads it dynamically, so it must not be duplicated there.
2. Move the `## [Unreleased]` entries in `CHANGELOG.md` under the new version.
3. Tag the release (`vX.Y.Z`) and publish a GitHub release — the
   `.github/workflows/python-publish.yml` workflow builds the distributions and
   publishes them to PyPI.

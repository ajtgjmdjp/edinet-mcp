# Contributing to edinet-mcp

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/ajtgjmdjp/edinet-mcp
cd edinet-mcp
uv sync --dev
```

## Running Tests

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```

## Pull Request Process

1. Fork the repository and create a feature branch
2. Write tests for new functionality
3. Ensure all checks pass (`pytest`, `ruff`, `mypy`)
4. Submit a PR with a clear description of changes

## Code Style

- Follow existing patterns in the codebase
- All code must pass `ruff check` and `ruff format`
- All public APIs must have type annotations and docstrings
- Target Python 3.10+

## Reporting Issues

Please use GitHub Issues with:
- A clear description of the problem
- Steps to reproduce (if applicable)
- Expected vs actual behavior

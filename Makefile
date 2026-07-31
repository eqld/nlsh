.PHONY: install install-dev lint format typecheck test coverage clean

install:
	pip install .

install-dev:
	pip install -r requirements-dev.txt

lint:
	ruff check nlsh/ tests/ || ruff check nlsh/
	black --check nlsh/

format:
	ruff check --fix nlsh/
	black nlsh/

typecheck:
	mypy nlsh/

test:
	pytest -q

coverage:
	pytest --cov=nlsh --cov-report=term-missing

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
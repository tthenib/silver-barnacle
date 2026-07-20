.PHONY: install lint typecheck test test-acceptance check simulate

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests scripts

format:
	ruff format src tests scripts

typecheck:
	mypy

test:
	pytest

test-acceptance:
	pytest -m acceptance

check: lint typecheck test

simulate:
	python scripts/run_simulation.py

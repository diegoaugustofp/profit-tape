.PHONY: install dev lint fmt type test cov docs clean

install:
	pip install -e .

dev:
	pip install -e ".[dev,db]"

lint:
	ruff check src tests

fmt:
	ruff format src tests && ruff check --fix src tests

type:
	mypy src

test:
	pytest

cov:
	pytest --cov=profittape --cov-report=term-missing

docs:
	python tools/gera_referencia_cli.py
	python tools/valida_ancoras.py docs/RESEARCH_PLANO.md docs/EA_ARQUITETURA.md docs/OPERACAO.md

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +

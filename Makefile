.PHONY: install test coverage lint audit live demo html clean

install:
	pip install -e ".[dev]"

test:
	pytest -q

coverage:
	pytest -q --cov=citeaudit --cov-report=term-missing

lint:
	python -m pyflakes src/citeaudit scripts tests
	python -m mypy src/citeaudit --ignore-missing-imports

audit:
	python scripts/audit_mismatches.py evidence/preprints/checks.csv

live:
	pytest -q -m live -rs

demo:
	citeaudit examples/demo.md --show-verified

html:
	citeaudit examples/demo.md --format html -o docs/index.html

clean:
	rm -rf .citeaudit-cache .pytest_cache citeaudit.json citeaudit-report.html
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

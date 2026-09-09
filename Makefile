.PHONY: install test live demo html clean lint

install:
	pip install -e ".[dev]"

test:
	pytest -q

live:
	pytest -q -m live -rs

demo:
	citeaudit examples/demo.md --show-verified

html:
	citeaudit examples/demo.md --format html -o docs/index.html

clean:
	rm -rf .citeaudit-cache .pytest_cache citeaudit.json citeaudit-report.html
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

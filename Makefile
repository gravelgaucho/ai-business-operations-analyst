PYTHON := .venv/bin/python

.PHONY: setup data server ask classify analytics analyze qualify qualify-analytics qualify-tools test lint

setup:
	/opt/homebrew/bin/python3.13 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e '.[dev]'

data:
	$(PYTHON) scripts/fetch_enterprise_bench.py

server:
	./scripts/start_server.sh

ask:
	$(PYTHON) -m business_ops.cli "$(QUESTION)"

classify:
	$(PYTHON) -m business_ops.classify_cli "$(QUESTION)"

analytics:
	$(PYTHON) -m business_ops.analytics_cli account-risk

analyze:
	$(PYTHON) -m business_ops.analyst_cli "$(QUESTION)"

qualify:
	$(PYTHON) scripts/qualify.py

qualify-analytics:
	$(PYTHON) scripts/qualify_analytics.py

qualify-tools:
	$(PYTHON) scripts/qualify_tools.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

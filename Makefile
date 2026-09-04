PYTHON := .venv/bin/python

.PHONY: setup data database server ask classify analytics analyze investigate qualify qualify-analytics qualify-tools qualify-investigation qualify-database test lint

setup:
	/opt/homebrew/bin/python3.13 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e '.[dev]'

data:
	$(PYTHON) scripts/fetch_enterprise_bench.py

database:
	$(PYTHON) -m business_ops.database_cli

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

investigate:
	$(PYTHON) -m business_ops.investigation_cli "$(QUESTION)"

qualify:
	$(PYTHON) scripts/qualify.py

qualify-analytics:
	$(PYTHON) scripts/qualify_analytics.py

qualify-tools:
	$(PYTHON) scripts/qualify_tools.py

qualify-investigation:
	$(PYTHON) scripts/qualify_investigation.py

qualify-database:
	$(PYTHON) scripts/qualify_database.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

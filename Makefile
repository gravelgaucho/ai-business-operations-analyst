PYTHON := .venv/bin/python

.PHONY: setup server ask classify qualify test lint

setup:
	/opt/homebrew/bin/python3.13 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e '.[dev]'

server:
	./scripts/start_server.sh

ask:
	$(PYTHON) -m business_ops.cli "$(QUESTION)"

classify:
	$(PYTHON) -m business_ops.classify_cli "$(QUESTION)"

qualify:
	$(PYTHON) scripts/qualify.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

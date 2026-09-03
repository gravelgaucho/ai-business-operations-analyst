PYTHON := .venv/bin/python

.PHONY: setup server qualify test lint

setup:
	/opt/homebrew/bin/python3.13 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e '.[dev]'

server:
	./scripts/start_server.sh

qualify:
	$(PYTHON) scripts/qualify.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .


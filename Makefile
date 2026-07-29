.PHONY: test unit integration security contract migrations eval coverage release-check scenario-check

PYTHON ?= python3
PYTHONPATH ?= src

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/unit tests/integration tests/security tests/contract tests/migrations -q

unit:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/unit -q

integration:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/integration -q

security:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/security -q

contract:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/contract -q

migrations:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/migrations -q

eval:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m agent_memory.cli.main eval run --path datasets

coverage:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m coverage run --source=src/agent_memory -m pytest tests/unit tests/integration tests/security tests/contract tests/migrations tests/property -q

scenario-check:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m agent_memory.cli.main scenario run datasets/extraction/role-filtering.yaml

release-check: coverage
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m agent_memory.cli.main release check

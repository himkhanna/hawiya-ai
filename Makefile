# Hawiya AI — developer Makefile
# Targets are documented in CLAUDE.md §8.
# Cross-platform: works with GNU Make on Linux/macOS/WSL and on Windows
# (mingw32-make from MSYS2 / git-bash, or chocolatey's `make`).

PYTHON ?= python
VENV   ?= .venv

ifeq ($(OS),Windows_NT)
    VENV_BIN := $(VENV)/Scripts
    RM_RF    := powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
else
    VENV_BIN := $(VENV)/bin
    RM_RF    := rm -rf
endif

PY        := $(VENV_BIN)/python
PIP       := $(VENV_BIN)/pip
RUFF      := $(VENV_BIN)/ruff
MYPY      := $(VENV_BIN)/mypy
PYTEST    := $(VENV_BIN)/pytest
ALEMBIC   := $(VENV_BIN)/alembic
UVICORN   := $(VENV_BIN)/uvicorn
PRECOMMIT := $(VENV_BIN)/pre-commit
BANDIT    := $(VENV_BIN)/bandit
PIPAUDIT  := $(VENV_BIN)/pip-audit

.PHONY: help install lint format test test-fast test-tenancy run-dev \
        migrate migrate-create seed-dev-tenant build-image build-airgap \
        benchmark dedupe-dry-run security loadtest clean

help:
	@echo "Hawiya AI — common targets"
	@echo "  install         create venv and install deps"
	@echo "  lint            ruff + mypy"
	@echo "  format          ruff format"
	@echo "  test            full test suite"
	@echo "  test-fast       unit tests only"
	@echo "  test-tenancy    multi-tenant isolation tests (CI gate)"
	@echo "  run-dev         local dev server with hot reload"
	@echo "  migrate         alembic upgrade head"
	@echo "  migrate-create  alembic revision -m 'msg' --autogenerate"
	@echo "  seed-dev-tenant create a dev tenant and print its UUID"
	@echo "  build-image     docker build of the service image"
	@echo "  build-airgap    package an offline installer bundle (Phase 1 wk 4)"
	@echo "  security        bandit + pip-audit"
	@echo "  loadtest        50 RPS for 30s against http://localhost:8000/v1/health"

install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PIP) install -e ".[dev]"
	$(PRECOMMIT) install

lint:
	$(RUFF) check src tests
	$(MYPY)

format:
	$(RUFF) format src tests
	$(RUFF) check --fix src tests

test:
	$(PYTEST)

test-fast:
	$(PYTEST) tests/unit

test-tenancy:
	$(PYTEST) -m tenancy

run-dev:
	$(UVICORN) hawiya.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	$(ALEMBIC) upgrade head

migrate-create:
	@test -n "$(m)" || (echo "Usage: make migrate-create m='describe change'"; exit 1)
	$(ALEMBIC) revision -m "$(m)" --autogenerate

seed-dev-tenant:
	$(PY) -m scripts.seed_dev_tenant

build-image:
	docker build -t hawiya-ai:dev -f deploy/Dockerfile .

build-airgap:
	bash deploy/air-gap/build.sh

benchmark:
	$(PY) -m scripts.benchmark_extraction

loadtest:
	$(PY) -m scripts.load_test --rps 50 --duration 30

security:
	@echo "--- bandit ---"
	$(BANDIT) -c pyproject.toml -r src
	@echo "--- pip-audit ---"
	$(PIPAUDIT) --skip-editable

dedupe-dry-run:
	$(PY) -m scripts.dedupe_existing_data --dry-run

clean:
	$(RM_RF) $(VENV) .pytest_cache .ruff_cache .mypy_cache build dist

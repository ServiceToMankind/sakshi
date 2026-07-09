# Sakshi — Because the record must not forget.
#
# Developer entry points for the data pipeline and the static site.
# `make check` is the aggregate gate that CI enforces on every PR.
#
# Dual license: CODE = MIT · DATA (data/) = ODbL v1.0.

VENV        := .venv
PY          := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
SITE        := site

# Coverage thresholds. The overall pipeline gate is 85%; the PII gates
# (sanitize.py and pii_guard.py — the last lines of defence before disk) are
# held to 100% branch coverage. Do not loosen without a human-approved issue.
COV_OVERALL := 85

.DEFAULT_GOAL := check

.PHONY: setup check test lint fmt pii-guard validate lighthouse site-dev site-build clean

# ---------------------------------------------------------------------------
# setup — create the virtualenv and install python + node dependencies.
# ---------------------------------------------------------------------------
setup:
	python3.12 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	cd $(SITE) && npm install

# ---------------------------------------------------------------------------
# check — the aggregate gate. Runs every quality control in order and fails
# fast. Mirrors ci.yml. Do not loosen these without a human-approved issue.
# (Lighthouse runs on the built site in CI / via `make lighthouse`; it is not
# in this gate so a pipeline-only checkout need not build the frontend.)
# ---------------------------------------------------------------------------
check: lint
	$(PY) -m mypy
	$(PY) -m pytest \
		--cov=pipeline \
		--cov-fail-under=$(COV_OVERALL) \
		--cov-report=term-missing
	# PII gates must be exhaustively covered — the record must not leak.
	$(PY) -m pytest \
		--cov=pipeline.sanitize --cov=scripts.pii_guard \
		--cov-fail-under=100 \
		--cov-report=term-missing \
		pipeline/tests/test_sanitize.py pipeline/tests/test_pii_guard.py
	$(MAKE) validate
	$(MAKE) pii-guard
	cd $(SITE) && npm run lint
	cd $(SITE) && npm run format:check

# ---------------------------------------------------------------------------
# test — python test suite with coverage (thresholds from pyproject).
# ---------------------------------------------------------------------------
test:
	$(PY) -m pytest --cov=pipeline --cov-report=term-missing

# ---------------------------------------------------------------------------
# lint — ruff check + ruff format --check over the pipeline and scripts.
# ---------------------------------------------------------------------------
lint:
	$(PY) -m ruff check pipeline scripts
	$(PY) -m ruff format --check pipeline scripts

# ---------------------------------------------------------------------------
# fmt — auto-format python (ruff) and, best-effort, the site sources.
# ---------------------------------------------------------------------------
fmt:
	$(PY) -m ruff format pipeline scripts
	$(PY) -m ruff check --fix pipeline scripts
	cd $(SITE) && npm run format

# ---------------------------------------------------------------------------
# pii-guard — final assertion that no forbidden field name or PII-shaped value
# ever reached data/. Standalone so it can run in isolation.
# ---------------------------------------------------------------------------
pii-guard:
	$(PY) scripts/pii_guard.py data/

# ---------------------------------------------------------------------------
# validate — jsonschema-validate every shard against schemas/case.schema.json
# and assert the summary.json size budget.
# ---------------------------------------------------------------------------
validate:
	$(PY) -m pipeline.validate --all

# ---------------------------------------------------------------------------
# lighthouse — Lighthouse CI over the built site (Phase-4/5 frontend gate).
# ---------------------------------------------------------------------------
lighthouse:
	cd $(SITE) && npm run build && npm run lighthouse

# ---------------------------------------------------------------------------
# site-dev / site-build — the Vite static frontend.
# ---------------------------------------------------------------------------
site-dev:
	cd $(SITE) && npm run dev

site-build:
	cd $(SITE) && npm run build

# ---------------------------------------------------------------------------
# clean — remove build/venv/cache artefacts. Never touches data/.
# ---------------------------------------------------------------------------
clean:
	rm -rf $(VENV)
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf .coverage htmlcov
	rm -rf $(SITE)/node_modules $(SITE)/dist
	find pipeline scripts -type d -name __pycache__ -prune -exec rm -rf {} +

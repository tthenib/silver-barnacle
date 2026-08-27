.PHONY: help install verify verify-docs verify-strict regenerate-results ci

PYTHON ?= python
PIP ?= pip

help:
	@printf '%s\n' \
	  'Targets:' \
	  '  make install            Install research dependencies' \
	  '  make verify             Check docs and generated results; warn if deps missing' \
	  '  make verify-docs        Check local Markdown links only' \
	  '  make verify-strict      Require generated-result dependencies and freshness' \
	  '  make ci                 Install dependencies and run strict verification' \
	  '  make regenerate-results Rebuild committed analysis outputs'

install:
	$(PIP) install -r requirements.txt

verify:
	$(PYTHON) tools/check_repo_integrity.py

verify-docs:
	$(PYTHON) tools/check_repo_integrity.py --skip-generated

verify-strict:
	$(PYTHON) tools/check_repo_integrity.py --require-generated-dependencies

ci: install verify-strict

regenerate-results:
	$(PYTHON) research/analysis/return_target_feasibility.py > results/return_target_feasibility.md
	$(PYTHON) research/analysis/lot_granularity.py > results/lot_granularity.md

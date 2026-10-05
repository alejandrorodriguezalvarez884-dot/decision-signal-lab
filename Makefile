# Everything about the radar is started from here, by hand. Nothing runs on a timer.
#
#   make            list the targets
#   make check      what is new on EDGAR for the study companies, and what it would cost
#   make publish    fetch and score those filings, save them, redeploy the service
#
# The public service (site + on-demand analysis) runs on Cloud Run; `make deploy` builds and
# deploys it. `make serve` runs the same thing on this machine.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Most a single `make update` may spend on the API, in USD. Override: make update MAX_USD=1
MAX_USD ?= 0.25
.PHONY: help install test check update summary site api dev serve deploy deploy-hub save publish

help: ## List the targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

install: ## Install the Python and site dependencies
	uv sync
	cd site && npm ci

test: ## Run the tests
	uv run pytest

check: ## Look for new filings on EDGAR and show what scoring them would cost. Spends nothing
	uv run decisionsignal radar check

update: ## Fetch and score new filings into radar/. Spends on the API, up to MAX_USD
	DECIDER_MAX_USD=$(MAX_USD) uv run decisionsignal radar update

summary: ## Rebuild radar/summary.json from radar/releases.json
	uv run decisionsignal radar summary

site: ## Build the site into site/dist
	cd site && npm run build

api: ## Run the API alone at http://localhost:8000, with reload (pair it with `make dev`)
	RADAR_ALLOWED_ORIGINS=http://localhost:4321 uv run uvicorn decisionsignal.api:create_app --factory --reload --port 8000

dev: ## Run the site at http://localhost:4321 with reload (it calls the API on port 8000)
	cd site && npm run dev

serve: site ## Run site and API together at http://localhost:8080, as in production
	RADAR_STATIC_DIR=site/dist uv run uvicorn decisionsignal.api:create_app --factory --port 8080

deploy: ## Build and deploy the service to Cloud Run (see scripts/deploy-cloudrun.sh)
	./scripts/deploy-cloudrun.sh

deploy-hub: ## Deploy the copy inside Market Hub (radar.themarkethub.app, sign-in required)
	SERVICE_NAME=earnings-radar-hub HUB_URL=https://themarkethub.app ./scripts/deploy-cloudrun.sh

save: ## Commit radar/ if it changed and push the current branch
	@if git diff --quiet HEAD -- radar/; then echo "radar/: nothing to commit"; \
		else git commit -q -m "Radar: update data" -- radar/ && echo "radar/: committed"; fi
	git push origin HEAD

publish: update save deploy ## Update the study data, save it and redeploy the service

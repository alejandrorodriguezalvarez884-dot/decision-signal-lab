# Everything about the radar runs from here, on this machine. Nothing runs on a server or on a
# timer: the data changes when you run `make update`, the site when you run `make deploy`.
#
#   make            list the targets
#   make publish    the whole thing: fetch and score new filings, save them, publish the site

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Most a single `make update` may spend on the API, in USD. Override: make update MAX_USD=1
MAX_USD ?= 0.25
REMOTE := $(shell git remote get-url origin)
DEPLOY_DIR := .deploy

.PHONY: help install test check update summary site dev deploy save publish

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

dev: ## Preview the site locally at http://localhost:4321
	cd site && npm run dev

deploy: site ## Build the site and publish it (pushes site/dist to the gh-pages branch)
	rm -rf $(DEPLOY_DIR)
	cp -R site/dist $(DEPLOY_DIR)
	touch $(DEPLOY_DIR)/.nojekyll
	cd $(DEPLOY_DIR) && git init -q -b gh-pages && git add -A \
		&& git -c user.name="$$(git -C .. config user.name)" -c user.email="$$(git -C .. config user.email)" \
			commit -q -m "Deploy $$(git -C .. rev-parse --short HEAD)" \
		&& git push -f $(REMOTE) gh-pages
	rm -rf $(DEPLOY_DIR)

save: ## Commit radar/ if it changed and push the current branch
	@if git diff --quiet HEAD -- radar/; then echo "radar/: nothing to commit"; \
		else git commit -q -m "Radar: update data" -- radar/ && echo "radar/: committed"; fi
	git push origin HEAD

publish: update save deploy ## Update the data, save it and publish the site

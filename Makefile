# YouTube Galaxy: local pipeline, static site, Cloudflare Worker.
# Pipeline steps run in the uv env; Airflow has its own venv (.venv-airflow).
PY := uv run --group pipeline python
# Use the Node version pinned in .nvmrc when nvm is installed (wrangler 4 needs Node >= 22.12).
NPM := $(if $(wildcard $(HOME)/.nvm/nvm.sh),. $(HOME)/.nvm/nvm.sh >/dev/null && nvm use --silent >/dev/null &&,) npm
.DEFAULT_GOAL := help

.PHONY: help setup mlflow airflow pipeline scrape embed cluster build eval gate publish rollback \
        web-dev web-build worker-dev worker-deploy test clean

help:  ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup:  ## Install Python deps, npm deps, and the Airflow venv
	uv sync
	@[ -f .env ] || (cp .env.example .env && echo "Created .env from .env.example (fill it in)")
	@if [ -f web/package.json ]; then $(NPM) --prefix web install; fi
	@if [ -f worker/package.json ]; then $(NPM) --prefix worker install; fi
	./scripts/setup_airflow.sh

mlflow:  ## Local MLflow UI on :5001 (sqlite under data/mlflow)
	./scripts/start_mlflow.sh

airflow:  ## Local Airflow (standalone) on :8080
	./scripts/start_airflow.sh

pipeline: scrape embed cluster eval gate build  ## Full run without publishing

scrape:  ## Incremental Fandom scrape (FULL=1 for a complete crawl)
	$(PY) -m pipeline.scrape $(if $(FULL),--full,)

embed:  ## Embed new/changed creators
	$(PY) -m pipeline.embed

cluster:  ## KMeans + UMAP 2D/3D + neighbours + cluster names
	$(PY) -m pipeline.cluster

eval:  ## Retrieval eval (recall@k, MRR) logged to MLflow
	$(PY) -m pipeline.evaluate

gate:  ## Quality gate (non-zero exit on failure)
	$(PY) -m pipeline.gate

build:  ## Build the versioned artifact set under data/artifacts/
	$(PY) -m pipeline.build_artifacts

publish:  ## Gated publish: Worker first, then the site (DRY=1 for a dry run)
	$(PY) -m pipeline.publish $(if $(DRY),--dry-run,)

rollback:  ## Point the site back at an older data version: make rollback VERSION=...
	@test -n "$(VERSION)" || (echo "usage: make rollback VERSION=<version>" && exit 1)
	$(PY) -m pipeline.publish --rollback $(VERSION)

web-dev:  ## Local map with hot reload
	$(NPM) --prefix web run dev

web-build:  ## Build the static site into web/dist
	$(NPM) --prefix web run build

worker-dev:  ## Local Worker via wrangler
	$(NPM) --prefix worker run dev

worker-deploy:  ## Deploy the Worker (needs `npx wrangler login`)
	$(NPM) --prefix worker run deploy

test:  ## Python, Worker and web tests
	uv run pytest -q
	@if [ -f worker/package.json ]; then $(NPM) --prefix worker test; fi
	@if [ -f web/package.json ] && grep -q '"test"' web/package.json; then $(NPM) --prefix web test; fi

clean:  ## Remove build outputs (keeps data/raw, embeddings and MLflow)
	rm -rf web/dist worker/.wrangler .pytest_cache .ruff_cache data/artifacts/tmp-*

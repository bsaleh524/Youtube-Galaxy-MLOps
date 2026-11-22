# YouTube Galaxy — local commands. See README.md.
# Still to come in later plans: Worker deploy, eval, gate (and a scraper/importer, issue #4).

.PHONY: help setup mlflow airflow web-dev web-build worker-dev worker-deploy test clean \
	seed embed cluster recluster compare-k build pipeline \
	web-data stage preview publish-dry publish rollback

PY := uv run python -m
.DEFAULT_GOAL := help

help:        ## list pipeline targets
	@grep -E '^[a-z-]+: +##' $(MAKEFILE_LIST) | sed -E 's/: +## /\t/' | expand -t 12

# --- Local pipeline (data stays in data/, never committed) ---

seed:        ## snapshot the seed dataset + seed cluster names
	$(PY) pipeline.seed

embed:       ## embed new/changed creators (reuses cached vectors)
	$(PY) pipeline.embed

cluster:     ## weekly: place creators into the existing clusters (assign mode)
	$(PY) pipeline.cluster --mode assign

recluster:   ## manual only, never scheduled: full re-fit (K=N to override N_CLUSTERS), then review names
	$(PY) pipeline.cluster --mode fit $(if $(K),--k $(K))

compare-k:   ## compare cluster counts without touching the live model (KS=60,120,200)
	$(PY) pipeline.compare_k $(if $(KS),--ks $(KS))

build:       ## write data/artifacts/galaxy/<version>/ (site + Worker files)
	$(PY) pipeline.build_artifacts

pipeline:    ## embed -> cluster -> build; skips if nothing changed (FORCE=1 to rebuild)
	$(PY) pipeline.run $(if $(FORCE),--force)

# --- Website ---

web-data:    ## copy the newest build's site data into web/.devdata for make web-dev
	$(PY) pipeline.publish galaxy --data-only --to-dir web/.devdata

stage:       ## mirror the Hostinger tree into data/stage/public_html (needs make web-build)
	$(PY) pipeline.publish all --to-dir data/stage/public_html

preview:     ## stage, then serve the tree on :8080 (also reachable from a phone on the same wifi)
	$(MAKE) stage
	@echo "Open http://localhost:8080/  (phone: http://$$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | cut -d' ' -f1):8080/)"
	python3 -m http.server 8080 --bind 0.0.0.0 -d data/stage/public_html

# --- Publish to Hostinger (docs/DEPLOY.md). Never part of `make pipeline`. ---

publish-dry: ## show exactly what a publish would upload (connects read-only)
	$(PY) pipeline.publish all --dry-run

publish:     ## upload home + galaxy to Hostinger (manifest last), verify, prune
	$(PY) pipeline.publish all

rollback:    ## point the live site at an older data version: make rollback VERSION=...
	$(PY) pipeline.publish rollback $(VERSION)

setup:
	uv sync
	cd web && npm install
	cd worker && npm install
	./scripts/setup_airflow.sh

mlflow:
	./scripts/start_mlflow.sh

airflow:
	./scripts/start_airflow.sh

web-dev:
	cd web && npm run dev

web-build:   ## build the galaxy site into web/dist (SITE_BASE_PATH, default /galaxy/)
	cd web && SITE_BASE_PATH=$${SITE_BASE_PATH:-/galaxy/} npm run build

worker-dev:
	cd worker && npm run dev

worker-deploy:
	cd worker && npm run deploy

test:
	uv run pytest
	uv run ruff check .
	cd worker && npm test
	cd web && npm test

# Never touches data/ or .env.
clean:
	rm -rf web/dist worker/.wrangler .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -not -path "./.venv*" -prune -exec rm -rf {} +

# YouTube Galaxy — local commands. See README.md.
# Pipeline targets (scrape, embed, cluster, build, eval, gate, publish, pipeline,
# recluster, rollback) are added by later plans as each step is built.

.PHONY: setup mlflow airflow web-dev web-build worker-dev worker-deploy test clean

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

web-build:
	cd web && npm run build

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

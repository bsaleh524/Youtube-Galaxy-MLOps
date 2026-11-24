COMPUTE_BACKEND ?= cpu
LLM_BACKEND     ?= groq
NAMESPACE_PIPELINE := galaxy-pipeline
NAMESPACE_SERVING  := galaxy-serving

# ── Local cluster ─────────────────────────────────────────────────────────────

.PHONY: cluster-up
cluster-up:
	@echo "Starting local k3d cluster (COMPUTE_BACKEND=$(COMPUTE_BACKEND))..."
	k3d cluster create -c k3d-$(COMPUTE_BACKEND).yaml
	@$(MAKE) cluster-namespaces

.PHONY: cluster-down
cluster-down:
	k3d cluster delete galaxy-local

.PHONY: cluster-namespaces
cluster-namespaces:
	kubectl apply -f k8s/namespaces.yaml

# ── Local services (install via Helm) ─────────────────────────────────────────

.PHONY: install-airflow
install-airflow:
	helm repo add apache-airflow https://airflow.apache.org --force-update
	helm upgrade --install airflow apache-airflow/airflow \
	  --namespace $(NAMESPACE_PIPELINE) \
	  --values k8s/airflow/values.yaml \
	  --set env[0].name=COMPUTE_BACKEND,env[0].value=$(COMPUTE_BACKEND) \
	  --set env[1].name=LLM_BACKEND,env[1].value=$(LLM_BACKEND)

.PHONY: install-mlflow
install-mlflow:
	kubectl apply -f k8s/mlflow/ -n $(NAMESPACE_PIPELINE)

.PHONY: install-weaviate
install-weaviate:
	helm repo add weaviate https://weaviate.github.io/weaviate-helm --force-update
	helm upgrade --install weaviate weaviate/weaviate \
	  --namespace $(NAMESPACE_SERVING) \
	  --values k8s/weaviate/values.yaml

.PHONY: install-redis
install-redis:
	helm repo add bitnami https://charts.bitnami.com/bitnami --force-update
	helm upgrade --install redis bitnami/redis \
	  --namespace $(NAMESPACE_SERVING) \
	  --values k8s/redis/values.yaml

.PHONY: install-ollama
install-ollama:
ifeq ($(COMPUTE_BACKEND),gpu)
	kubectl apply -f k8s/ollama/ -n $(NAMESPACE_SERVING)
else
	@echo "Skipping Ollama (COMPUTE_BACKEND=$(COMPUTE_BACKEND)) — use LLM_BACKEND=groq instead"
endif

.PHONY: install-ingress
install-ingress:
	helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update
	helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
	  --namespace kube-system \
	  --values k8s/ingress/nginx-values.yaml

.PHONY: install-all-local
install-all-local: install-mlflow install-weaviate install-redis install-ollama install-airflow

# ── Oracle Cloud (production) ─────────────────────────────────────────────────

.PHONY: infra-init
infra-init:
	terraform -chdir=infra init

.PHONY: infra-plan
infra-plan:
	terraform -chdir=infra plan

.PHONY: infra-apply
infra-apply:
	terraform -chdir=infra apply

.PHONY: infra-destroy
infra-destroy:
	@read -p "Destroy ALL Oracle Cloud resources? [y/N] " c && [ "$$c" = "y" ]
	terraform -chdir=infra destroy

# ── Data operations ───────────────────────────────────────────────────────────

.PHONY: load-weaviate
load-weaviate:
	python scripts/load_weaviate.py \
	  --weaviate-url $${WEAVIATE_URL:-http://localhost:8080} \
	  --parquet-path $${PARQUET_PATH:-data/starmap_data.parquet}

.PHONY: feast-materialize
feast-materialize:
	cd features && feast materialize-incremental $$(date -u +%Y-%m-%dT%H:%M:%S)

# ── Build & push containers ───────────────────────────────────────────────────

REGISTRY ?= localhost:5000

.PHONY: build-training
build-training:
	docker build -t $(REGISTRY)/galaxy-training:latest training/

.PHONY: build-chatbot
build-chatbot:
	docker build -t $(REGISTRY)/galaxy-chatbot:latest serving/chatbot_api/

.PHONY: build-embedding
build-embedding:
	docker build -t $(REGISTRY)/galaxy-embedding:latest serving/embedding_service/

.PHONY: build-scraper
build-scraper:
	docker build -t $(REGISTRY)/galaxy-scraper:latest scrapers/

.PHONY: build-frontend
build-frontend:
	docker build -t $(REGISTRY)/galaxy-frontend:latest frontend/

.PHONY: build-all
build-all: build-training build-chatbot build-embedding build-scraper build-frontend

# ── Airflow DAG testing ───────────────────────────────────────────────────────

.PHONY: dag-test-scrape
dag-test-scrape:
	kubectl exec -n $(NAMESPACE_PIPELINE) deploy/airflow-scheduler -- \
	  airflow dags trigger fandom_scrape_dag

.PHONY: dag-test-train
dag-test-train:
	kubectl exec -n $(NAMESPACE_PIPELINE) deploy/airflow-scheduler -- \
	  airflow dags trigger training_pipeline_dag

# ── Port-forwarding (local development) ──────────────────────────────────────

.PHONY: forward-airflow
forward-airflow:
	kubectl port-forward -n $(NAMESPACE_PIPELINE) svc/airflow-webserver 8080:8080

.PHONY: forward-mlflow
forward-mlflow:
	kubectl port-forward -n $(NAMESPACE_PIPELINE) svc/mlflow 5000:5000

.PHONY: forward-weaviate
forward-weaviate:
	kubectl port-forward -n $(NAMESPACE_SERVING) svc/weaviate 8081:80

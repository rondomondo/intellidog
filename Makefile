# ============================================================
# intellidog — Makefile
# ============================================================
.DEFAULT_GOAL := help
MAKEFLAGS     += --no-print-directory
SHELL         := /bin/bash

# -- Colors ---------------------------------------------------
BOLD   := \033[1m
RED    := \033[31m
GREEN  := \033[32m
CYAN   := \033[36m
YELLOW := \033[33m
RESET  := \033[0m

# -- Tooling --------------------------------------------------
PYTHON   := python3
VENV     := .venv
PIP      := $(VENV)/bin/pip
PYTEST   := $(VENV)/bin/pytest
RUFF     := $(VENV)/bin/ruff
MYPY     := $(VENV)/bin/mypy
BLACK    := $(VENV)/bin/black
ISORT    := $(VENV)/bin/isort

# -- Docker config (override on the command line as needed) ---
IMAGE_NAME := intellidog
IMAGE_TAG  := latest
DOCKERFILE := .devcontainer/Dockerfile

# System packages that must be present before the venv can be used.
SYS_DEPS := git fzf jq python3

# -- Help ------------------------------------------------------
.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'


.PHONY: check-sys-deps
check-sys-deps: ## Verify required system packages are installed (Linux only; skipped on macOS)
	@if [ "$$(uname)" = "Darwin" ]; then \
	  echo "  check-sys-deps skipped (macOS)"; \
	  exit 0; \
	fi; \
	missing=""; \
	for pkg in $(SYS_DEPS); do \
	  if ! command -v $$pkg >/dev/null 2>&1; then \
	    missing="$$missing $$pkg"; \
	  fi; \
	done; \
	if [ -n "$$missing" ]; then \
	  printf "$(RED)ERROR:$(RESET) missing system packages:$$missing\n"; \
	  exit 1; \
	fi; \
	echo "  system deps OK"

.PHONY: venv
venv: ## Create Python virtual environment (recreates if interpreter path is stale)
	@stale=0; \
	if [ -d "$(VENV)" ]; then \
		interp=$$(head -1 $(VENV)/bin/pip 2>/dev/null | sed 's/^#!//'); \
		if [ -n "$$interp" ] && [ ! -f "$$interp" ]; then \
			printf "$(YELLOW)Stale venv (interpreter $$interp missing) — recreating...$(RESET)\n"; \
			rm -rf $(VENV); \
			stale=1; \
		fi; \
	fi; \
	if [ ! -d "$(VENV)" ]; then \
		printf "$(GREEN)Creating venv in $(VENV)...$(RESET)\n"; \
		$(PYTHON) -m venv $(VENV); \
		$(PIP) install --upgrade pip; \
		printf "$(GREEN)Venv created. Activate with: source $(VENV)/bin/activate$(RESET)\n"; \
	elif [ "$$stale" = "0" ]; then \
		printf "$(YELLOW)Venv already exists.$(RESET)\n"; \
	fi

.PHONY: install
install: check-sys-deps venv ## Install development dependencies
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install -e ".[dev]"
	@printf "$(GREEN)Dependencies installed.$(RESET)\n"

.PHONY: check-venv
check-venv: ## Verify venv exists
	@test -d $(VENV) || (printf "$(RED)ERROR:$(RESET) venv not found. Run: make install\n"; exit 1)

# -- Code quality ----------------------------------------------
.PHONY: format
format: check-venv ## Format Python code (black + isort)
	$(BLACK) src/ tests/
	$(ISORT) src/ tests/

.PHONY: lint
lint: check-venv ## Lint Python code (ruff + mypy)
	$(RUFF) check --fix src/ tests/
	$(MYPY) src/

.PHONY: typecheck
typecheck: check-venv ## Run mypy type checks
	$(MYPY) src/

.PHONY: test
test: check-venv ## Run Python tests with coverage
	$(PYTEST) tests/ -v --tb=short --cov=src --cov-report=term-missing

.PHONY: ci
ci: format lint typecheck test ## Run full CI pipeline
	@echo "CI passed"

# -- Intellidog app -------------------------------------------
TOOLS_DIR := tools

.PHONY: run
run: check-venv ## Start the Intellidog API server (local, no Docker)
	$(VENV)/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

.PHONY: up
up: ## Build and start all services (API + Redis + Grafana) via docker-compose
	@mkdir -p data rules
	docker compose up --build -d
	@printf "$(GREEN)Services started. API: http://localhost:8000  Grafana: http://localhost:3000$(RESET)\n"

.PHONY: down
down: ## Stop and remove all docker-compose services
	docker compose down

.PHONY: logs
logs: ## Tail docker-compose service logs
	docker compose logs --follow

.PHONY: ps
ps: ## Show docker-compose service status
	docker compose ps

.PHONY: generate
generate: check-venv ## Generate and POST synthetic events to the API (default 20 events + 10 logs)
	$(VENV)/bin/python $(TOOLS_DIR)/generate_events.py

.PHONY: generate-spike
generate-spike: check-venv ## Generate an error spike (all critical events)
	$(VENV)/bin/python $(TOOLS_DIR)/generate_events.py --spike --count 60

.PHONY: inject-anomaly
inject-anomaly: check-venv ## Inject a latency spike anomaly event
	$(VENV)/bin/python $(TOOLS_DIR)/inject_anomaly.py --type latency_spike

.PHONY: alert-scenario
alert-scenario: check-venv ## Run the 'spike' alert scenario
	$(VENV)/bin/python $(TOOLS_DIR)/generate_alerts.py --scenario spike

.PHONY: query
query: check-venv ## Query and print recent events from the API
	$(VENV)/bin/python $(TOOLS_DIR)/query_events.py events --limit 20

.PHONY: screenshots
screenshots: ## Capture UI screenshots via Playwright Docker image (requires services running)
	./scripts/run_screenshots.sh

.PHONY: gen-cert
gen-cert: check-venv ## Generate self-signed TLS certs for local HTTPS (output: certs/)
	mkdir -p certs
	openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
		-keyout certs/intellidog.key \
		-out certs/intellidog.crt \
		-subj "/CN=localhost" \
		-addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
	@printf "$(GREEN)Certs written to certs/$(RESET)\n"

# -- Docker ----------------------------------------------------
.PHONY: docker-build
docker-build: ## Build the devcontainer image locally (IMAGE_NAME, IMAGE_TAG, DOCKERFILE overridable)
	docker build \
		--file $(DOCKERFILE) \
		--tag $(IMAGE_NAME):$(IMAGE_TAG) \
		.

.PHONY: docker-run
docker-run: ## Run the image interactively, mounting the project root to /workspace
	docker run --rm -it \
		--volume "$(PWD):/workspace" \
		--workdir /workspace \
		$(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: docker-shell
docker-shell: ## Open a shell in the image (alias for docker-run with explicit bash)
	docker run --rm -it \
		--volume "$(PWD):/workspace" \
		--workdir /workspace \
		$(IMAGE_NAME):$(IMAGE_TAG) bash

# -- Clean ----------------------------------------------------
.PHONY: clean-pyc
clean-pyc: ## Remove Python bytecode and tool caches
	@printf "$(CYAN)Cleaning$(RESET) Python caches...\n"
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .mypy_cache  -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .ruff_cache  -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@printf "  $(GREEN)ok$(RESET)\n"

.PHONY: clean
clean: clean-pyc ## Remove build artifacts and caches
	@printf "$(CYAN)Cleaning$(RESET) build artifacts...\n"
	@find . -type d -name dist         -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name build        -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf coverage/ .coverage htmlcov/ 2>/dev/null || true
	@rm -rf $(VENV)
	@printf "  $(GREEN)ok$(RESET)\n"

# Replit — convenience targets for the local development stack.
#
# These are not required at runtime (production can use plain
# `docker compose` / Kubernetes manifests) but they handle the
# pre-flight that docker-compose.yml expects:
#
#   1. `make sandbox` builds the replit-sandbox image that the backend
#      spawns for every workspace.
#   2. `make up` resolves the host docker group gid automatically so
#      the backend's `node` user can read /var/run/docker.sock.
#   3. `make dev` runs the backend/frontend on the host with `npm run`
#      for fast iteration (no docker required).
#
# Run `make help` to see all targets.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Override these on the command line if needed:
#   make sandbox SANDBOX_TAG=mysandbox
SANDBOX_TAG  ?= replit-sandbox
BACKEND_TAG  ?= replit-backend
FRONTEND_TAG ?= replit-frontend
FRONTEND_PORT ?= 8080
COMPOSE      ?= docker compose

# Docker Hub namespace for `make pull` / `make up-published`. Override
# on the command line:  make pull DH_USER=yourname
DH_USER ?= suraim001

# When true, `make up` uses docker-compose.published.yml (pulls the
# three images from Docker Hub) instead of building them locally. Handy
# on a fresh host where you just want to run the published stack.
DH_USE_HUB ?= false

# Host docker group gid — passed to the backend so it can write the
# bind-mounted /var/run/docker.sock. Resolved lazily so it works on
# macOS/Windows where the socket is a named pipe (and group_add is a
# no-op there).
DOCKER_GID := $(shell stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 0)

# Pick the compose file list. The published override is layered on
# top of the base file when DH_USE_HUB is true (or when the explicit
# `up-published` target is used).
ifeq ($(DH_USE_HUB),true)
  COMPOSE_FILES := -f docker-compose.yml -f docker-compose.published.yml
  HUB_IMAGE_SUFFIX := $(DH_USER)/
else
  COMPOSE_FILES := -f docker-compose.yml
  HUB_IMAGE_SUFFIX :=
endif

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help text.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
# Sandbox image (the one the backend spawns for each user).
# ---------------------------------------------------------------------------

.PHONY: sandbox
sandbox: ## Build the replit-sandbox image from backend/Dockerfile.sandbox.
	docker build \
		-f backend/Dockerfile.sandbox \
		-t $(SANDBOX_TAG) \
		backend/

.PHONY: sandbox-rebuild
sandbox-rebuild: ## Rebuild the sandbox image from scratch (no cache).
	docker build --no-cache \
		-f backend/Dockerfile.sandbox \
		-t $(SANDBOX_TAG) \
		backend/

# ---------------------------------------------------------------------------
# Full stack via docker compose.
# ---------------------------------------------------------------------------

.PHONY: build
build: sandbox ## Build every service image in the compose file.
	$(COMPOSE) $(COMPOSE_FILES) build

.PHONY: pull
pull: ## Pull the three images from Docker Hub (DH_USER override).
	@echo "Pulling $(DH_USER)/{replit-sandbox,replit-backend,replit-frontend}..."
	@docker pull $(DH_USER)/replit-sandbox:latest
	@docker pull $(DH_USER)/replit-backend:latest
	@docker pull $(DH_USER)/replit-frontend:latest

.PHONY: up
up: ## Bring the full stack up. Set DH_USE_HUB=true to pull from Docker Hub.
ifeq ($(DH_USE_HUB),true)
up: pull
else
up: sandbox
endif
	@if [ "$(DOCKER_GID)" != "0" ]; then \
		echo "Host docker socket group gid: $(DOCKER_GID)"; \
	fi
	FRONTEND_PORT=$(FRONTEND_PORT) \
	SANDBOX_IMAGE=$(HUB_IMAGE_SUFFIX)$(SANDBOX_TAG) \
		$(COMPOSE) $(COMPOSE_FILES) up -d

.PHONY: up-published
up-published: ## Pull from Docker Hub and start the stack (suraim001 by default).
	$(MAKE) up DH_USE_HUB=true

.PHONY: down
down: ## Stop and remove the stack (keeps images).
	$(COMPOSE) $(COMPOSE_FILES) down

.PHONY: restart
restart: down up ## Restart the stack.

.PHONY: logs
logs: ## Tail logs from every service.
	$(COMPOSE) $(COMPOSE_FILES) logs -f --tail=200

.PHONY: ps
ps: ## Show running containers.
	$(COMPOSE) $(COMPOSE_FILES) ps

.PHONY: clean
clean: down ## Stop the stack AND remove sandbox/workspace containers.
	@echo "Pruning sandboxes ($(HUB_IMAGE_SUFFIX)$(SANDBOX_TAG))..."
	-@docker ps -aq --filter "ancestor=$(HUB_IMAGE_SUFFIX)$(SANDBOX_TAG)" | xargs -r docker rm -f >/dev/null 2>&1
	@echo "Removing replit images..."
	-@docker images -q $(HUB_IMAGE_SUFFIX)$(BACKEND_TAG) $(HUB_IMAGE_SUFFIX)$(FRONTEND_TAG) | xargs -r docker rmi -f >/dev/null 2>&1

# ---------------------------------------------------------------------------
# Native dev mode — no docker, no compose, fastest iteration.
# ---------------------------------------------------------------------------

.PHONY: dev
dev: ## Run backend + frontend on the host (no docker).
	@echo "Run 'npm run dev' in backend/ and frontend/ in separate terminals."

.PHONY: dev-backend
dev-backend: ## Run only the backend in the foreground.
	cd backend && npm run dev

.PHONY: dev-frontend
dev-frontend: ## Run only the frontend in the foreground.
	cd frontend && npm run dev

# ---------------------------------------------------------------------------
# Verification.
# ---------------------------------------------------------------------------

.PHONY: verify
verify: ## Smoke-check that the compose file parses and services wire up.
	@echo "→ docker compose config (base + published override)"
	@$(COMPOSE) -f docker-compose.yml config -q && echo "  base compose config: OK"
	@$(COMPOSE) -f docker-compose.yml -f docker-compose.published.yml config -q && echo "  published override: OK"
	@echo "→ backend boots without throwing"
	@cd backend && node -e "require('./src/server.js')" &
	@SERVER_PID=$$!; sleep 1; kill $$SERVER_PID 2>/dev/null || true; wait $$SERVER_PID 2>/dev/null || true
	@echo "→ frontend builds"
	@cd frontend && npm run build --silent
	@echo "All checks passed."

.PHONY: install dev test coverage lint up down infra ui ui-build ui-test ui-lint \
	temporal worker worker-local litellm start test-all lint-all e2e e2e-fake e2e-real e2e-run

install:
	uv sync
	cd ui && npm install

up:
	docker compose up -d postgres

infra:
	docker compose up -d postgres temporal

down:
	docker compose down

dev:
	uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload

# Start API (:8000) and UI (:5173) together; Ctrl-C stops both. Ensures Postgres is up.
start: up
	@echo "API  -> http://localhost:8000"
	@echo "UI   -> http://localhost:5173"
	@echo "(Ctrl-C stops both)"
	@trap 'kill 0' EXIT INT TERM; \
		uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload & \
		( cd ui && npm run dev ) & \
		wait

test:
	uv run pytest

coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80

# Backend + frontend unit tests
test-all: test ui-test

lint:
	uv run ruff check src tests

lint-all: lint ui-lint

ui:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

ui-test:
	cd ui && npm test

ui-lint:
	cd ui && npm run lint

# Playwright end-to-end tests (needs API :8000 + UI :5173 running)
e2e:
	cd ui && npm run e2e

# --- Full-stack agent-harness E2E (drives the API end-to-end against a dummy repo) ---
# e2e-fake : FakeAgentRuntime — free, deterministic, proves orchestration/DB/usage/events.
# e2e-real : ClaudeCodeRuntime — needs ANTHROPIC_API_KEY; a real agent edits the dummy repo.
# Both self-orchestrate: infra + their own API (:8000) + worker, then tear down on exit.
# Stop any running 'make start'/'make dev'/'make worker-local' first (port + task-queue clashes).
E2E_PORT    ?= 8000
E2E_API     ?= http://localhost:$(E2E_PORT)
E2E_REPO    ?= /tmp/yaah-dummy
E2E_RUNTIME ?= fake
E2E_AUTONOMY ?= full_auto
E2E_POLL    ?= 40
E2E_SLEEP   ?= 1

e2e-fake:
	@$(MAKE) --no-print-directory e2e-run E2E_RUNTIME=fake E2E_AUTONOMY=full_auto E2E_POLL=40 E2E_SLEEP=1

e2e-real:
	@$(MAKE) --no-print-directory e2e-run E2E_RUNTIME=claude_code E2E_AUTONOMY=full_auto E2E_POLL=120 E2E_SLEEP=5

e2e-run:
	@command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required (brew install jq)"; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is required"; exit 1; }
	@if [ "$(E2E_RUNTIME)" = "claude_code" ] && [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "ERROR: e2e-real needs ANTHROPIC_API_KEY exported in your shell"; exit 1; fi
	@if curl -sf $(E2E_API)/health >/dev/null 2>&1; then \
		echo "ERROR: $(E2E_API) is already serving — stop 'make start'/'make dev'/another worker first"; exit 1; fi
	@echo ">> bringing up infra (postgres + temporal)…"
	@docker compose up -d --wait postgres temporal
	@set -e; \
	API=$(E2E_API); REPO=$(E2E_REPO); RT=$(E2E_RUNTIME); \
	echo ">> dummy git repo: $$REPO"; \
	rm -rf "$$REPO"; mkdir -p "$$REPO"; \
	git -C "$$REPO" init -q; \
	git -C "$$REPO" symbolic-ref HEAD refs/heads/main; \
	printf '# Dummy Project\n\nThrowaway repo for yaah E2E validation.\n' > "$$REPO/README.md"; \
	git -C "$$REPO" add -A; \
	git -C "$$REPO" -c user.email=e2e@yaah.local -c user.name=e2e commit -qm init; \
	echo ">> starting API (:$(E2E_PORT))…"; \
	YAAH_PROFILE=local uv run uvicorn --app-dir src interactors.api.app:create_app --factory --port $(E2E_PORT) >/tmp/yaah-e2e-api.log 2>&1 & API_PID=$$!; \
	WK_PID=""; \
	trap 'kill $$API_PID $$WK_PID 2>/dev/null || true' EXIT INT TERM; \
	printf '>> waiting for API'; \
	for i in $$(seq 1 30); do curl -sf $$API/health >/dev/null 2>&1 && break || true; printf '.'; sleep 1; done; echo; \
	if ! curl -sf $$API/health >/dev/null 2>&1; then echo "ERROR: API did not start — log:"; tail -30 /tmp/yaah-e2e-api.log; exit 1; fi; \
	echo ">> starting worker (runtime=$$RT)…"; \
	PYTHONPATH=src YAAH_PROFILE=local YAAH_AGENT_RUNTIME=$$RT uv run python -m interactors.temporal.worker >/tmp/yaah-e2e-worker.log 2>&1 & WK_PID=$$!; \
	post() { curl -s -X POST "$$API$$1" -H 'content-type: application/json' -d "$$2"; }; \
	echo ">> creating project / team / epic→feature→task…"; \
	PID=$$(post /projects "{\"name\":\"e2e-$$RT\",\"local_path\":\"$$REPO\",\"autonomy\":\"$(E2E_AUTONOMY)\"}" | jq -r .data.id); \
	TEAM=$$(post /teams/default "" | jq -r .data.team.id); \
	curl -s -X PATCH "$$API/projects/$$PID" -H 'content-type: application/json' -d "{\"team_id\":\"$$TEAM\"}" >/dev/null; \
	EPIC=$$(post /projects/$$PID/work-items "{\"kind\":\"epic\",\"title\":\"e2e epic\"}" | jq -r .data.id); \
	FEAT=$$(post /projects/$$PID/work-items "{\"kind\":\"feature\",\"title\":\"e2e feature\",\"parent_id\":\"$$EPIC\"}" | jq -r .data.id); \
	TASK=$$(post /projects/$$PID/work-items "{\"kind\":\"task\",\"title\":\"Add hello.txt containing the word hello\",\"parent_id\":\"$$FEAT\",\"acceptance_criteria\":[\"hello.txt exists at the repo root\",\"hello.txt contains the text hello\"]}" | jq -r .data.id); \
	post /work-items/$$TASK/status "{\"status\":\"ready\"}" >/dev/null; \
	RUN=$$(post /work-items/$$TASK/runs "" | jq -r .data.id); \
	echo "   project=$$PID task=$$TASK run=$$RUN"; \
	echo ">> polling run (max $(E2E_POLL)×$(E2E_SLEEP)s)…"; \
	STATUS=pending; \
	for i in $$(seq 1 $(E2E_POLL)); do \
		R=$$(curl -s $$API/runs/$$RUN); \
		STATUS=$$(echo "$$R" | jq -r .data.status); \
		STAGE=$$(echo "$$R" | jq -r .data.stage); \
		echo "   [$$i] status=$$STATUS stage=$$STAGE"; \
		case "$$STATUS" in done|failed|blocked|cancelled) break;; esac; \
		sleep $(E2E_SLEEP); \
	done; \
	echo ">> run summary:"; \
	curl -s $$API/runs/$$RUN | jq '.data | {status,stage,branch,cost_usd,input_tokens,output_tokens}'; \
	echo ">> events:"; \
	curl -s $$API/runs/$$RUN/events | jq -r '.data[] | "   \(.stage)  \(.type)  \(.message)"'; \
	echo ">> usage totals:"; \
	curl -s $$API/runs/$$RUN/usage | jq '.data.totals'; \
	if [ "$$RT" = "claude_code" ]; then \
		echo ">> audit (capability grants):"; \
		curl -s $$API/runs/$$RUN/audit | jq -r '.data[] | "   \(.stage)  \(.actor)  tools=\(.detail.tools)"'; \
		WS="$$PWD/data/workspaces/runs/$$RUN"; \
		echo ">> workspace $$WS:"; \
		ls -la "$$WS" 2>/dev/null || true; \
		git -C "$$WS" show --stat HEAD 2>/dev/null || echo "   (no commit in workspace)"; \
	fi; \
	echo "----------------------------------------"; \
	if [ "$$STATUS" = "done" ]; then \
		echo "PASS: run reached status=done"; \
	elif [ "$$RT" = "claude_code" ] && [ "$$STATUS" = "blocked" ]; then \
		echo "PARTIAL: harness ran the real agent but VERIFY blocked after retries — inspect events above"; \
	else \
		echo "FAIL: terminal status=$$STATUS (worker log below)"; tail -30 /tmp/yaah-e2e-worker.log; exit 1; \
	fi

temporal:
	docker compose up -d temporal

worker:
	docker compose up -d --build worker

# Run the Temporal worker as a host process (real Claude Code + local repo access).
# Pin the runtime with YAAH_AGENT_RUNTIME=fake|claude_code; set ANTHROPIC_API_KEY for real agents.
worker-local: infra
	PYTHONPATH=src uv run python -m interactors.temporal.worker

litellm:
	docker compose up -d litellm

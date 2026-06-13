# E2E Local Validation — Agent Harness Smoke Test

**Date:** 2026-06-13
**Goal:** Validate, on a single laptop, that the yaah agent harness runs a ticket end-to-end:
API → Temporal workflow → per-stage activities → agent runtime → DB persistence (status,
events, usage). Two tiers — Tier 1 proves the plumbing for free and deterministically;
Tier 2 proves the real Claude Code agent actually edits a repo.

This is a **validation runbook**, not a code change. You execute it manually and check
each observation against the pass/fail table at the end.

---

## What is real vs fake right now (phases A1–A5d done)

| Component | State |
|---|---|
| Control plane (API, DB, domain models, owner-scoping) | **Real** |
| Temporal `RunWorkflow` orchestration (PLAN→PROVISION→IMPLEMENT→VERIFY→PR→LEARN) | **Real** |
| Gates / approve / reject / cancel signals | **Real** |
| `FakeAgentRuntime` (deterministic events, fake usage, writes `IMPLEMENTED.md`) | **Real fake** |
| `ClaudeCodeRuntime` (spawns `claude -p … --output-format stream-json`) | **Real** |
| `LocalGit` worktree/commit (local profile) | **Real** |
| Usage/token tracking + rollups (`/usage` endpoints) | **Real** |
| Capability audit log (`/runs/{id}/audit`) | **Real** |
| GitHub PR open (push + forge API) | Only in `remote` profile; **local profile records branch, no push** |
| Per-run Docker sandbox / egress proxy (A4 hardening) | **Not wired** (process-level isolation only) |
| Notifications (A5e), refinement chat + memory (A6) | **Out of scope** |

**Runtime selection** (`src/interactors/temporal/worker.py:41-51`): with
`YAAH_AGENT_RUNTIME=auto`, the worker uses `ClaudeCodeRuntime` when `ANTHROPIC_API_KEY` is
set **and** the `claude` binary is on PATH, else `FakeAgentRuntime`. We pin it explicitly
per tier (`fake` / `claude_code`) to remove ambiguity.

---

## Design decisions for this runbook

- **Worker runs as a host process, not the Docker `worker` service.** Reasons: (1) the
  local profile provisions via `git worktree` off `project.local_path`, so the dummy repo
  must be on a writable filesystem the worker shares; the Docker worker is `read_only:true`
  and would require path-matched volume mounts. (2) Real Claude Code needs the host `claude`
  binary + your `ANTHROPIC_API_KEY`. A host worker shares your filesystem and PATH with zero
  mounting friction. Postgres and Temporal still run in Docker.
- **API server and worker share one Postgres** (both default to `:5433`, both run
  `Base.metadata.create_all`). Start Postgres before either.
- **Profile = `local`** throughout (no GitHub App needed). PR stage records the branch only.
- Use two autonomy levels to exercise both paths: `full_auto` (runs to `done` unattended)
  and `gated_all` (pauses at PLAN and PR → you send approve signals).

---

## Prerequisites (one-time)

```bash
cd /Users/noel/projects/yaah
uv sync
command -v jq   >/dev/null || brew install jq      # used for assertions below
command -v claude                                  # Tier 2 only: expect /Users/noel/.local/bin/claude
```

Helper env used throughout (paste into each terminal):

```bash
export API=http://localhost:8000
export PGURL=postgresql+psycopg://yaah:yaah@localhost:5433/yaah
post() { curl -s -X POST "$API$1" -H 'content-type: application/json' -d "${2:-{}}"; }
get()  { curl -s "$API$1"; }
```

---

## Tier 0 — Infrastructure & API health (shared by both tiers)

**Terminal A — infra:**
```bash
cd /Users/noel/projects/yaah
docker compose up -d postgres temporal
# wait for healthy
docker compose ps
```
Temporal Web UI: http://localhost:8233 (watch workflows here).

**Terminal B — API server:**
```bash
cd /Users/noel/projects/yaah
YAAH_PROFILE=local YAAH_DATABASE_URL=$PGURL \
  uv run uvicorn --app-dir src interactors.api.app:create_app --factory --reload
```

**Check (Terminal C):**
```bash
get /health | jq            # expect {"success":true,"data":{"status":"ok"},...}
```

✅ **Gate 0:** `/health` returns `success:true`. Temporal UI reachable. Schema auto-created
(API startup ran `create_all`).

---

## Tier 1 — Plumbing smoke (FakeAgentRuntime, free, deterministic)

Proves: workflow orchestration, all 6 stages, activity DB writes, event stream, usage
rollup, status lifecycle, and the gate/approval path — **without any model call or repo.**

### 1A. Start the worker pinned to the fake runtime

**Terminal D — worker:**
```bash
cd /Users/noel/projects/yaah
PYTHONPATH=src YAAH_PROFILE=local YAAH_DATABASE_URL=$PGURL \
  YAAH_AGENT_RUNTIME=fake \
  uv run python -m interactors.temporal.worker
```
Expect log lines showing the worker polling task queue `yaah-runs`. Leave it running.

### 1B. Drive the API: full_auto run

> **Note:** `local_path` must point at a **real git repo** even in the fake tier — the
> `provision` activity runs `git worktree add` via `LocalGit` regardless of runtime. Create
> the dummy repo first (see Tier 2 step 2A, or just run `make e2e-fake` which does it for you).

```bash
# Project (full_auto so it runs to completion unattended).
PID=$(post /projects '{"name":"e2e-fake","local_path":"/tmp/yaah-dummy","autonomy":"full_auto"}' | jq -r .data.id)

# Default team (lead + engineer + QA) and assign it
TEAM=$(post /teams/default | jq -r .data.team.id)
curl -s -X PATCH "$API/projects/$PID" -H 'content-type: application/json' \
  -d "{\"team_id\":\"$TEAM\"}" | jq .success

# Epic → Feature → Task
EPIC=$(post /projects/$PID/work-items '{"kind":"epic","title":"E2E epic"}' | jq -r .data.id)
FEAT=$(post /projects/$PID/work-items "{\"kind\":\"feature\",\"title\":\"E2E feature\",\"parent_id\":\"$EPIC\"}" | jq -r .data.id)
TASK=$(post /projects/$PID/work-items "{\"kind\":\"task\",\"title\":\"Add a hello file\",\"parent_id\":\"$FEAT\",\"acceptance_criteria\":[\"hello.txt exists\"]}" | jq -r .data.id)

# Move task DRAFT → READY (runs require READY)
post /work-items/$TASK/status '{"status":"ready"}' | jq -r .data.status   # expect "ready"

# Start the run
RUN=$(post /work-items/$TASK/runs '{}' | jq -r .data.id)
echo "RUN=$RUN"
```

### 1C. Observe to completion

```bash
# Poll status (fake runtime completes in seconds)
for i in $(seq 1 20); do
  S=$(get /runs/$RUN | jq -r .data.status); echo "status=$S"; \
  [ "$S" = "done" ] && break; sleep 1; done

get /runs/$RUN | jq '.data | {status,stage,cost_usd,input_tokens,output_tokens}'
get /runs/$RUN/events | jq -r '.data[] | "\(.stage)\t\(.type)\t\(.message)"'
get /runs/$RUN/usage  | jq '.data.totals'
get /runs/$RUN/usage  | jq -r '.data.breakdown[] | "\(.stage)\t\(.model_id)\t\(.input_tokens)/\(.output_tokens)"'
get /work-items/$TASK | jq -r .data.status     # task should have advanced past READY
```

✅ **Gate 1A (full_auto):**
- Run status reaches `done`.
- Events show each stage (`plan, provision, implement, verify, pr, learn`) with
  `stage_completed` / agent events.
- `usage.totals.input_tokens` > 0 (fake = 1000 in / 200 out per stage) and
  `cost_usd` > 0 (fake = 0.25/stage).
- Breakdown has one row per stage that ran the agent.
- Temporal UI shows the workflow `Completed`.

### 1D. Gated path — exercise approvals

```bash
PID2=$(post /projects '{"name":"e2e-gated","local_path":"/tmp/yaah-dummy","autonomy":"gated_all"}' | jq -r .data.id)
curl -s -X PATCH "$API/projects/$PID2" -H 'content-type: application/json' -d "{\"team_id\":\"$TEAM\"}" >/dev/null
EP2=$(post /projects/$PID2/work-items '{"kind":"epic","title":"g"}' | jq -r .data.id)
FE2=$(post /projects/$PID2/work-items "{\"kind\":\"feature\",\"title\":\"g\",\"parent_id\":\"$EP2\"}" | jq -r .data.id)
TK2=$(post /projects/$PID2/work-items "{\"kind\":\"task\",\"title\":\"gated task\",\"parent_id\":\"$FE2\"}" | jq -r .data.id)
post /work-items/$TK2/status '{"status":"ready"}' >/dev/null
RUN2=$(post /work-items/$TK2/runs '{}' | jq -r .data.id)

# Wait for the PLAN gate
for i in $(seq 1 20); do S=$(get /runs/$RUN2 | jq -r .data.status); echo $S; \
  [ "$S" = "awaiting_approval" ] && break; sleep 1; done

post /runs/$RUN2/approve | jq '.data.status'      # 202; resumes
# It will pause again at the PR gate — approve once more:
for i in $(seq 1 20); do S=$(get /runs/$RUN2 | jq -r .data.status); echo $S; \
  [ "$S" = "awaiting_approval" ] && break; [ "$S" = "done" ] && break; sleep 1; done
post /runs/$RUN2/approve | jq '.data.status'
for i in $(seq 1 20); do S=$(get /runs/$RUN2 | jq -r .data.status); echo $S; \
  [ "$S" = "done" ] && break; sleep 1; done
```

✅ **Gate 1B (gated_all):** Run pauses at PLAN (`awaiting_approval`), resumes on approve,
pauses again at PR, resumes on second approve, reaches `done`. (Optional: repeat with
`/reject` on a fresh run → expect terminal `failed`; with `/cancel` mid-run → `cancelled`.)

---

## Tier 2 — Real agent (ClaudeCodeRuntime against a dummy repo)

Proves: a real `claude` subprocess reads the ticket, edits a real git repo in a worktree,
the change is committed on a branch, and **real token usage** is recorded.

> ⚠️ Costs tokens. Keep the task tiny. `YAAH_CLAUDE_MAX_TURNS` defaults to 30.

### 2A. Create a dummy git repo (the "project")

```bash
rm -rf /tmp/yaah-dummy && mkdir -p /tmp/yaah-dummy && cd /tmp/yaah-dummy
git init -q && git checkout -q -b main
printf '# Dummy Project\n\nA throwaway repo for yaah E2E validation.\n' > README.md
git add . && git -c user.email=e2e@yaah -c user.name=e2e commit -qm "init"
git log --oneline    # expect one commit on main
```

### 2B. Restart the worker pinned to Claude Code

Stop the Tier-1 worker (Ctrl-C in Terminal D), then:

```bash
cd /Users/noel/projects/yaah
PYTHONPATH=src YAAH_PROFILE=local YAAH_DATABASE_URL=$PGURL \
  YAAH_AGENT_RUNTIME=claude_code \
  ANTHROPIC_API_KEY=sk-ant-...your-key... \
  uv run python -m interactors.temporal.worker
```
(Optional: route through LiteLLM instead — `docker compose up -d litellm` and add
`YAAH_MODEL_GATEWAY=litellm YAAH_LITELLM_BASE_URL=http://localhost:4000`.)

### 2C. Drive a tiny real run

```bash
PID3=$(post /projects '{"name":"e2e-real","local_path":"/tmp/yaah-dummy","autonomy":"full_auto"}' | jq -r .data.id)
curl -s -X PATCH "$API/projects/$PID3" -H 'content-type: application/json' -d "{\"team_id\":\"$TEAM\"}" >/dev/null
EP3=$(post /projects/$PID3/work-items '{"kind":"epic","title":"real epic"}' | jq -r .data.id)
FE3=$(post /projects/$PID3/work-items "{\"kind\":\"feature\",\"title\":\"real feature\",\"parent_id\":\"$EP3\"}" | jq -r .data.id)
TK3=$(post /projects/$PID3/work-items "{\"kind\":\"task\",\"title\":\"Add hello.txt containing the word hello\",\"parent_id\":\"$FE3\",\"acceptance_criteria\":[\"A file hello.txt exists at repo root\",\"It contains the text hello\"]}" | jq -r .data.id)
post /work-items/$TK3/status '{"status":"ready"}' >/dev/null
RUN3=$(post /work-items/$TK3/runs '{}' | jq -r .data.id)
echo "RUN3=$RUN3"
```

### 2D. Observe (slower — real model turns)

```bash
# Poll up to ~5 min
for i in $(seq 1 60); do S=$(get /runs/$RUN3 | jq -r .data.status); \
  echo "status=$S stage=$(get /runs/$RUN3 | jq -r .data.stage)"; \
  case "$S" in done|failed|blocked|cancelled) break;; esac; sleep 5; done

get /runs/$RUN3 | jq '.data | {status,stage,branch,cost_usd,input_tokens,output_tokens,cache_read_tokens}'
get /runs/$RUN3/events | jq -r '.data[] | "\(.stage)\t\(.type)\t\(.message)"' | head -50
get /runs/$RUN3/audit  | jq -r '.data[] | "\(.stage)\t\(.actor)\t\(.detail.model_alias)\ttools=\(.detail.tools)"'
get /runs/$RUN3/usage  | jq '.data.totals'

# Inspect what the agent actually wrote (worktree under the run workspace)
ls -la /Users/noel/projects/yaah/data/workspaces/runs/$RUN3/
git -C /Users/noel/projects/yaah/data/workspaces/runs/$RUN3 log --oneline 2>/dev/null
git -C /Users/noel/projects/yaah/data/workspaces/runs/$RUN3 show --stat HEAD 2>/dev/null
```

✅ **Gate 2 (real agent):**
- Run reaches `done` (or `blocked` after 3 failed VERIFY loops — still a valid harness
  result; inspect events to see why).
- `usage.totals` reflects **real, non-round** token counts (not the fake 1000/200), and
  `cost_usd` > 0 derived from the Claude stream.
- `/runs/{id}/audit` shows a `capability_granted` row per stage with the agent's
  tools/model_alias (e.g. IMPLEMENT granted `Read,Edit,Write,Bash`).
- The run workspace contains a committed change on a `yaah/...` branch including the
  agent's edit (e.g. `hello.txt`). PR stage event says `branch … ready` (local profile =
  no push), and `data.branch` is populated on the run.

---

## Pass/fail summary

| # | Check | Pass criterion |
|---|---|---|
| 0 | API + infra | `/health` ok; Temporal UI up; schema auto-created |
| 1A | Fake full_auto | status `done`; all 6 stages in events; usage>0; cost>0 |
| 1B | Fake gated_all | pauses at PLAN & PR; resumes on approve; ends `done` |
| 1B′ | reject / cancel (optional) | reject→`failed`; cancel→`cancelled` |
| 2 | Real Claude run | status `done`/`blocked`; real token counts; audit rows; committed edit on branch |

If Tier 1 passes but Tier 2 fails, the harness wiring is sound and the issue is isolated to
the real runtime (claude invocation, prompt, worktree provisioning, or VERIFY). Treat any
ordering anomaly (e.g. PLAN running before PROVISION provisions the repo) as a **finding to
report**, not a test you must make pass.

---

## Teardown

```bash
# stop API (Terminal B) and worker (Terminal D) with Ctrl-C
docker compose down            # add -v to also wipe pgdata/temporaldata/workspaces volumes
rm -rf /tmp/yaah-dummy
rm -rf /Users/noel/projects/yaah/data/workspaces/runs/*   # clear run worktrees
```

---

## Troubleshooting

- **Worker won't import** `interactors.temporal.worker` → ensure `PYTHONPATH=src` is set
  (the `pythonpath=["src"]` in pyproject only applies to pytest, not `python -m`).
- **Run stays `pending`** → worker not polling, or API and worker point at different DBs.
  Confirm both use `$PGURL`; check Temporal UI for a started `RunWorkflow` with id = run id.
- **`POST /runs` → 409** → task not `READY`, or project has no `team_id` assigned.
- **Tier 2 picks the fake runtime anyway** → `YAAH_AGENT_RUNTIME` not `claude_code`, or
  `ANTHROPIC_API_KEY` not exported in the worker's terminal, or `claude` not on PATH.
- **`git worktree` provision error** → dummy repo has no commit / not on `main`; redo 2A.
- **VERIFY loops then `blocked`** → expected when the agent's change doesn't satisfy the
  acceptance criteria within 3 loops; read `/runs/{id}/events` to see the agent's reasoning.

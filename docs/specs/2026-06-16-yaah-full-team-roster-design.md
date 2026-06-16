# yaah — Full Team Roster (all 6 roles) — Design

> Status: approved design, pre-implementation. Authored 2026-06-16.
> Finishes the **default team** so it contains every role the orchestration machinery
> already supports, with differentiated personas, tool grants, and tiered model aliases.

## 1. Problem

The orchestration layer already supports all six roles end to end:

- `AgentRole` enumerates `LEAD, ARCHITECT, BACKEND, FRONTEND, QA, DEVOPS`.
- `build_orchestrator_prompt` advertises the team's `available_roles` to the lead.
- `decision_to_messages` routes each dispatch to the matching team agent (and **silently
  skips** any role not present on the team — `role_to_agent_id.get(...)` returns `None`).
- `_manifest_for_role` selects the `AgentDefinition` for a role and composes its
  system prompt + allowed tools + skill/MCP/secret grants for the runtime.

But `domain/teams.default_team()` instantiates only **three** agents — `LEAD`, a single
`BACKEND` "Engineer", and `QA`. Architect, Frontend, and Devops have no `AgentDefinition`,
so the lead can never dispatch to them: those dispatches are dropped on the floor.

**Goal:** make the default team the full virtual team (all 6 roles), each with a
distinct persona, tool allowlist, and tiered model alias, and make the lead aware of
when to use each role — **without changing the orchestration loop**.

## 2. Scope

In scope:

1. Expand `default_team()` to all six roles with per-role persona, `allowed_tools`, and
   tiered `model_alias`.
2. Migrate flat aliases (`lead-model`/`engineer-model`/`qa-model`) to tier aliases
   (`frontier`/`mid`/`cheap`) in the team factory and the LiteLLM config.
3. Add a pure, static role guide to `orchestration/prompts.py` so the lead's prompt
   describes *when to dispatch* each role (not just the role names).
4. Update/extend the affected tests.

Explicitly **out of scope** (YAGNI / belongs to other specs):

- No orchestration-loop behavior changes. Architect-as-mandatory-plan-reviewer and
  devops-as-CI-triage-automation are **not** implemented; the lead dispatches these roles
  judgmentally via the existing `CONTINUE → dispatch → verify` loop.
- Custom roles; parallel same-role engineers (separate Phase B parallel-engineers spec).
- Role-memory curation changes (the `role-memory.md` pointer infra already exists in
  `domain/agent/prompts.memory_pointer`).
- Skill/MCP/secret grants remain **empty** for the default team (as today). There are no
  seeded skills to grant; per-role grants are added later via the Capabilities/Models UI.

## 3. Design

### 3.1 Roster

`default_team()` returns the team plus six `AgentDefinition`s, in this order:

| Role | `model_alias` | `allowed_tools` | Persona (system prompt intent) |
|---|---|---|---|
| `LEAD` | `frontier` | `Read, Write` | Orchestrates the team and plans the work; does not write code itself. |
| `ARCHITECT` | `frontier` | `Read, Write` | Reviews the plan and the design for soundness; records decisions under `docs/adr/`. **Reads and writes docs only — never edits source, never runs Bash.** |
| `BACKEND` | `mid` | `Read, Edit, Write, Bash` | Implements server/domain code; keeps changes focused; runs tests. |
| `FRONTEND` | `mid` | `Read, Edit, Write, Bash` | Implements the `ui/` SPA; uses `pnpm` (never `npm`) via Bash. |
| `QA` | `cheap` | `Read, Bash` | Adversarially verifies against acceptance criteria; runs tests/build; **does not modify source.** |
| `DEVOPS` | `cheap` | `Read, Edit, Write, Bash` | Owns CI/Docker/deploy config; triages CI failures. Thin in v1 — invoked only when the task touches infra or CI is red. |

Notes on tool grants:

- **Architect** intentionally lacks `Edit` and `Bash`: it is a review/design role. This is
  enforced outside the model by the existing PreToolUse allowlist hook.
- **QA** stays read-only (`Read, Bash`) — unchanged from today.
- Frontend and Backend share the same toolset; their difference is persona + working area
  (`ui/` vs `src/`), expressed in the system prompt.

`team_id`, `purpose`, and `system_prompt` are populated for every agent (the existing
`AgentDefinition` invariants). Persona prompts stay concise (one to three sentences) and
follow the voice of the current three.

### 3.2 Tiered model aliases

Three logical tier aliases replace the flat per-role aliases:

| Tier alias | Roles | Real model (LiteLLM config) |
|---|---|---|
| `frontier` | lead, architect | `anthropic/claude-sonnet-4-6` |
| `mid` | backend, frontend | `anthropic/claude-sonnet-4-6` |
| `cheap` | qa, devops | `anthropic/claude-haiku-4-5-20251001` |

`frontier` and `mid` map to the same model today (single-user local economy); they remain
**distinct aliases** so `frontier` can be bumped to opus later by editing
`infra/litellm/config.yaml` only — no code change.

`infra/litellm/config.yaml` `model_list` is rewritten to define `frontier`, `mid`, `cheap`
(keeping the existing `sonnet` default entry). The old `lead-model`/`engineer-model`/
`qa-model` entries are removed.

**Default (Anthropic) path is unaffected:** `AnthropicProvider.model_id` returns the single
configured model for any alias that does not start with `claude-`, so `frontier`/`mid`/
`cheap` all resolve to the configured Anthropic model when no gateway is used. Tiering only
takes effect under the LiteLLM gateway, which resolves the aliases via its config.

### 3.3 Lead role-awareness

Today `build_orchestrator_prompt` renders only role *names*
(`roles = ", ".join(r.value for r in available_roles)`). With four more roles available,
the lead needs to know *when* to use each. Add a pure, static map in
`domain/orchestration/prompts.py`:

```python
_ROLE_GUIDE: dict[AgentRole, str] = {
    AgentRole.ARCHITECT: "review the plan/design and record decisions (no code)",
    AgentRole.BACKEND:   "implement server/domain code",
    AgentRole.FRONTEND:  "implement the ui/ frontend",
    AgentRole.QA:        "verify the work against acceptance criteria (read-only)",
    AgentRole.DEVOPS:    "CI/Docker/deploy config and CI-failure triage",
    AgentRole.LEAD:      "you — orchestrate; do not dispatch yourself",
}
```

The prompt renders, for each available role, `"- <role>: <guide>"` instead of a bare
comma-joined list. This is pure and unit-testable; it does not thread `AgentDefinition`
data through the activity. Roles missing from the guide fall back to the bare name.

## 4. Data flow (unchanged)

```
default_team() → 6 AgentDefinitions persisted (seed/CLI)
   → run starts → OrchestratorWorkflow
       → invoke_lead activity builds prompt with available_roles + role guide
       → lead returns OrchestrationDecision (dispatches by target_role)
       → decision_to_messages routes to role_to_agent_id (now all 6 resolve)
       → AgentWorkflow actor runs _run_instructed_agent
           → _manifest_for_role picks the role's AgentDefinition
           → composes system_prompt + allowed_tools (+ empty grants)
           → runtime resolves model_alias via provider
```

No new tables, activities, workflows, or ports. The change is data (more agents on the
team) plus one prompt enrichment.

## 5. Error handling

- A dispatch to a role still not on the team continues to be skipped by
  `decision_to_messages` (defensive; should not happen with the full roster).
- Architect/QA tool violations (e.g. an attempted `Edit`) are denied by the existing
  PreToolUse allowlist hook and recorded in the audit log — no new handling needed.
- Empty skill/MCP grants compose to a manifest with empty lists, exactly as today.

## 6. Testing

Unit:

- `test_teams.py`
  - roster is exactly `[LEAD, ARCHITECT, BACKEND, FRONTEND, QA, DEVOPS]` (defined order);
  - aliases: lead/architect → `frontier`, backend/frontend → `mid`, qa/devops → `cheap`;
  - tool grants: architect has neither `Edit` nor `Bash`; frontend has `Edit` and `Bash`;
    devops has `Edit`; qa is read-only (no `Edit`); every agent has `purpose` +
    `system_prompt`.
- `test_litellm_infra.py` — assert config lists `frontier`, `mid`, `cheap`.
- `test_agent_invocation.py` — update any flat-alias references.
- New orchestration-prompts test — `build_orchestrator_prompt` output contains a role-guide
  line for each available role (e.g. the architect's "no code" hint when architect is
  available).

Integration:

- `test_teams_api.py` — expectations updated from 3 to 6 agents.

Coverage stays ≥ 80% (the change is mostly data; new branches are the role-guide rendering,
covered by the new prompt test).

## 7. Rollout

Single PR, `feat: full default team roster (all 6 roles) with tiered model aliases`.
Existing seeded teams in a running DB are unaffected by code; re-seeding (`make db-reset`)
produces the full roster. No migration (no schema change).

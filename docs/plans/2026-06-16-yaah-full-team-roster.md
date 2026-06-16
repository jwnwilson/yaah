# Full Team Roster (all 6 roles) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand yaah's `default_team()` to all six roles (Lead, Architect, Backend, Frontend, QA, Devops) with differentiated personas, tool grants, and tiered model aliases, and teach the lead's orchestrator prompt when to dispatch each role.

**Architecture:** The orchestration loop already routes dispatches by role and composes each role's manifest from its `AgentDefinition` — so this is almost entirely *data* (more agents on the team) plus one *pure prompt enrichment*. No new tables, activities, workflows, or ports. Flat per-role model aliases (`lead-model`/`engineer-model`/`qa-model`) are replaced by three logical tier aliases (`frontier`/`mid`/`cheap`).

**Tech Stack:** Python 3.12, Pydantic v2, pytest, FastAPI TestClient, LiteLLM YAML config.

**Design spec:** `docs/specs/2026-06-16-yaah-full-team-roster-design.md`

**Working directory:** worktree `../yaah-full-team-roster` on branch `feat/full-team-roster`.

---

## File Structure

- `infra/litellm/config.yaml` — **modify**: replace flat aliases with `frontier`/`mid`/`cheap` tier entries (keep `sonnet` default).
- `src/domain/teams.py` — **modify**: `_DEFAULT_AGENTS` grows from 3 to 6 entries; tier aliases; updated docstring.
- `src/domain/orchestration/prompts.py` — **modify**: add pure static `_ROLE_GUIDE` map; render per-role "when to dispatch" lines in `build_orchestrator_prompt`.
- `tests/unit/test_litellm_infra.py` — **modify**: assert tier aliases.
- `tests/unit/test_teams.py` — **modify**: assert full roster, tier aliases, per-role tool grants.
- `tests/integration/test_teams_api.py` — **modify**: expect 6 agents.
- `tests/unit/test_orchestration_prompts.py` — **modify**: add a test that the role guide is rendered.
- `tests/unit/test_agent_invocation.py` — **modify**: update the one flat-alias literal for consistency.

Each task is independently committable and leaves the suite green.

---

## Task 1: Tiered model aliases in the LiteLLM config

**Files:**
- Modify: `infra/litellm/config.yaml`
- Test: `tests/unit/test_litellm_infra.py`

- [ ] **Step 1: Update the failing test**

Replace the `test_litellm_config_lists_aliases` body in `tests/unit/test_litellm_infra.py` so it asserts the new tier aliases:

```python
def test_litellm_config_lists_aliases():
    cfg = Path("infra/litellm/config.yaml").read_text()
    for alias in ("frontier", "mid", "cheap"):
        assert alias in cfg
```

Leave `test_litellm_service_in_compose` unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_litellm_infra.py::test_litellm_config_lists_aliases -v`
Expected: FAIL — `assert "frontier" in cfg` is False (config still lists `lead-model` etc.).

- [ ] **Step 3: Rewrite the config**

Replace the entire contents of `infra/litellm/config.yaml` with:

```yaml
model_list:
  - model_name: frontier
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: mid
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: cheap
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
```

(`frontier` and `mid` map to the same model today; they stay distinct so `frontier` can be bumped to opus later by editing this file alone. `sonnet` remains as the gateway default.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_litellm_infra.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add infra/litellm/config.yaml tests/unit/test_litellm_infra.py
git commit -m "feat: define frontier/mid/cheap tier aliases in litellm config"
```

---

## Task 2: Full team roster in `default_team()`

**Files:**
- Modify: `src/domain/teams.py`
- Test: `tests/unit/test_teams.py`

- [ ] **Step 1: Rewrite the failing tests**

Replace the three `default_team` tests in `tests/unit/test_teams.py` (keep `test_run_defaults` and the existing imports). The final file's team tests should be:

```python
from domain.models import AgentRole, Run, RunStatus, Team
from domain.teams import default_team


def test_default_team_has_all_six_roles_in_order():
    team, agents = default_team(owner_id="dev-user")
    assert isinstance(team, Team)
    roles = [a.role for a in agents]
    assert roles == [
        AgentRole.LEAD,
        AgentRole.ARCHITECT,
        AgentRole.BACKEND,
        AgentRole.FRONTEND,
        AgentRole.QA,
        AgentRole.DEVOPS,
    ]
    assert all(a.team_id == team.id for a in agents)


def test_default_team_model_aliases_follow_tier_rubric():
    _, agents = default_team(owner_id="dev-user")
    by_role = {a.role: a.model_alias for a in agents}
    assert by_role[AgentRole.LEAD] == "frontier"
    assert by_role[AgentRole.ARCHITECT] == "frontier"
    assert by_role[AgentRole.BACKEND] == "mid"
    assert by_role[AgentRole.FRONTEND] == "mid"
    assert by_role[AgentRole.QA] == "cheap"
    assert by_role[AgentRole.DEVOPS] == "cheap"


def test_default_team_tool_grants_match_role_responsibilities():
    _, agents = default_team(owner_id="u")
    by_role = {a.role: a for a in agents}
    assert all(a.purpose and a.system_prompt for a in agents)
    # Architect is a review/design role: docs only, no source edits, no shell.
    assert "Edit" not in by_role[AgentRole.ARCHITECT].allowed_tools
    assert "Bash" not in by_role[AgentRole.ARCHITECT].allowed_tools
    # Engineers and devops edit and run commands.
    assert {"Edit", "Bash"} <= set(by_role[AgentRole.BACKEND].allowed_tools)
    assert {"Edit", "Bash"} <= set(by_role[AgentRole.FRONTEND].allowed_tools)
    assert "Edit" in by_role[AgentRole.DEVOPS].allowed_tools
    # QA is read-only.
    assert "Edit" not in by_role[AgentRole.QA].allowed_tools
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_teams.py -v`
Expected: FAIL — roster is still `[LEAD, BACKEND, QA]` and aliases are still `lead-model`/`engineer-model`/`qa-model`.

- [ ] **Step 3: Rewrite the team factory**

Replace the entire contents of `src/domain/teams.py` with:

```python
from domain.models import AgentDefinition, AgentRole, Team

# role, name, model alias (tier), purpose, system prompt, allowed tools
_DEFAULT_AGENTS: list[tuple[AgentRole, str, str, str, str, list[str]]] = [
    (AgentRole.LEAD, "Lead", "frontier",
     "Plan the work and coordinate the team.",
     "You are the team lead and orchestrator. Read the ticket, plan the work, and "
     "dispatch the right agents. You coordinate; you do not write code yourself.",
     ["Read", "Write"]),
    (AgentRole.ARCHITECT, "Architect", "frontier",
     "Review the plan and design; record architectural decisions.",
     "You are the architect. Review the plan and design for soundness and record "
     "decisions under docs/adr/. You read and write docs only — never edit source "
     "files, never run shell commands.",
     ["Read", "Write"]),
    (AgentRole.BACKEND, "Backend Engineer", "mid",
     "Implement server-side and domain code.",
     "You are a senior backend engineer. Implement the ticket in src/, keep changes "
     "focused, and run the tests.",
     ["Read", "Edit", "Write", "Bash"]),
    (AgentRole.FRONTEND, "Frontend Engineer", "mid",
     "Implement the ui/ frontend.",
     "You are a senior frontend engineer. Implement the ticket in ui/. Use pnpm "
     "(never npm) for all package and script commands.",
     ["Read", "Edit", "Write", "Bash"]),
    (AgentRole.QA, "QA", "cheap",
     "Verify the implementation against the acceptance criteria.",
     "You are QA. Adversarially verify the work; run tests; do not modify source.",
     ["Read", "Bash"]),
    (AgentRole.DEVOPS, "Devops", "cheap",
     "Own CI/Docker/deploy config and triage CI failures.",
     "You are devops. Own CI, Docker, and deploy configuration, and triage CI "
     "failures. Touch infra and pipeline config, not application logic.",
     ["Read", "Edit", "Write", "Bash"]),
]


def default_team(owner_id: str, name: str = "Default Team") -> tuple[Team, list[AgentDefinition]]:
    """The full virtual team: lead + architect + backend + frontend + QA + devops
    (spec docs/specs/2026-06-16-yaah-full-team-roster-design.md)."""
    team = Team(owner_id=owner_id, name=name)
    agents = [
        AgentDefinition(
            team_id=team.id,
            role=role,
            name=agent_name,
            model_alias=alias,
            purpose=purpose,
            system_prompt=system_prompt,
            allowed_tools=tools,
        )
        for role, agent_name, alias, purpose, system_prompt, tools in _DEFAULT_AGENTS
    ]
    return team, agents
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_teams.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add src/domain/teams.py tests/unit/test_teams.py
git commit -m "feat: full default team roster (all 6 roles) with tiered aliases"
```

---

## Task 3: Update the teams API integration test

**Files:**
- Test: `tests/integration/test_teams_api.py`

- [ ] **Step 1: Update the failing test**

In `tests/integration/test_teams_api.py`, replace both role-list assertions in `test_create_default_team_and_fetch_agents` so they expect the full roster:

```python
    expected_roles = ["lead", "architect", "backend", "frontend", "qa", "devops"]
    assert [a["role"] for a in agents] == expected_roles

    assert c.get("/teams").json()["data"][0]["id"] == team["id"]
    fetched = c.get(f"/teams/{team['id']}").json()["data"]
    assert fetched["team"]["id"] == team["id"]
    assert [a["role"] for a in fetched["agents"]] == expected_roles
```

Leave `test_get_missing_team_404` unchanged.

- [ ] **Step 2: Run test to verify it passes**

The route already returns whatever `default_team()` produces, so with Task 2 done this test passes immediately. Run it to confirm:

Run: `uv run pytest tests/integration/test_teams_api.py -v`
Expected: PASS (both tests). If you run this task *before* Task 2, it fails with the old 3-role list — that is the expected RED.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_teams_api.py
git commit -m "test: expect full 6-role roster from /teams/default"
```

---

## Task 4: Lead role-awareness in the orchestrator prompt

**Files:**
- Modify: `src/domain/orchestration/prompts.py`
- Test: `tests/unit/test_orchestration_prompts.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/unit/test_orchestration_prompts.py` (the file already imports `build_orchestrator_prompt`, `AgentRole`, and `OrchestrationState`):

```python
def test_prompt_describes_when_to_use_each_available_role():
    prompt = build_orchestrator_prompt(
        task_title="T",
        acceptance_criteria=[],
        body="",
        state=OrchestrationState(),
        available_roles=[AgentRole.ARCHITECT, AgentRole.FRONTEND],
    )
    # Each available role is rendered with a "when to dispatch" guide, not just its name.
    assert "architect: review the plan/design and record decisions (no code)" in prompt
    assert "frontend: implement the ui/ frontend" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestration_prompts.py::test_prompt_describes_when_to_use_each_available_role -v`
Expected: FAIL — the prompt currently lists role names comma-joined with no guide text.

- [ ] **Step 3: Add the role guide and render it**

In `src/domain/orchestration/prompts.py`, add the static guide near the top, after the `_INTENTS` definition:

```python
# Pure "when to dispatch" hints, rendered next to the available roles so the lead
# knows what each role is for. Roles absent here fall back to their bare name.
_ROLE_GUIDE: dict[AgentRole, str] = {
    AgentRole.LEAD: "you — orchestrate; do not dispatch yourself",
    AgentRole.ARCHITECT: "review the plan/design and record decisions (no code)",
    AgentRole.BACKEND: "implement server/domain code",
    AgentRole.FRONTEND: "implement the ui/ frontend",
    AgentRole.QA: "verify the work against acceptance criteria (read-only)",
    AgentRole.DEVOPS: "CI/Docker/deploy config and CI-failure triage",
}
```

Then, inside `build_orchestrator_prompt`, replace this line:

```python
    roles = ", ".join(r.value for r in available_roles) or "(none)"
```

with:

```python
    roles = "\n".join(
        f"- {r.value}: {_ROLE_GUIDE.get(r, r.value)}" for r in available_roles
    ) or "- (none)"
```

And in the returned f-string, replace:

```python
        f"Available agent roles you may dispatch: {roles}\n\n"
```

with:

```python
        f"Available agent roles you may dispatch:\n{roles}\n\n"
```

- [ ] **Step 4: Run the prompt tests to verify they pass**

Run: `uv run pytest tests/unit/test_orchestration_prompts.py -v`
Expected: PASS — the new test passes, and the existing `test_prompt_mentions_ticket_roles_and_state` still passes (it only checks `"backend"`/`"qa"` substrings, which the new lines still contain).

- [ ] **Step 5: Commit**

```bash
git add src/domain/orchestration/prompts.py tests/unit/test_orchestration_prompts.py
git commit -m "feat: orchestrator prompt describes when to dispatch each role"
```

---

## Task 5: Update the flat-alias literal in the invocation test

**Files:**
- Test: `tests/unit/test_agent_invocation.py`

This test proves `model_id` is passed verbatim to `--model`; it uses an arbitrary alias literal. Update it to a tier alias so no stale `engineer-model` reference remains.

- [ ] **Step 1: Update the test**

In `tests/unit/test_agent_invocation.py`, replace the body of `test_model_id_is_used_verbatim` (currently lines ~116-120):

```python
def test_model_id_is_used_verbatim():
    man = AgentManifest(allowed_tools=["Read"])
    inv = build_invocation(_ctx(agent=man), model_id="mid")
    i = inv.argv.index("--model")
    assert inv.argv[i + 1] == "mid"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_agent_invocation.py::test_model_id_is_used_verbatim -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_agent_invocation.py
git commit -m "test: use tier alias in model-id verbatim invocation test"
```

---

## Task 6: Full verification, lint, and PR

**Files:** none (verification only).

- [ ] **Step 1: Search for any remaining stale aliases**

Run: `grep -rn "lead-model\|engineer-model\|qa-model" src tests infra`
Expected: no matches in `src/`, `tests/`, or `infra/`. (Matches under `docs/plans/` or `docs/specs/` describing *past* increments are historical and fine to leave.)

- [ ] **Step 2: Run the full test suite with the coverage gate**

Run: `make coverage`
Expected: all tests pass; total coverage ≥ 80%.

- [ ] **Step 3: Lint**

Run: `make lint`
Expected: clean.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/full-team-roster
gh pr create --title "feat: full default team roster (all 6 roles)" \
  --body "$(cat <<'EOF'
## Summary
- Expand `default_team()` from 3 to all 6 roles: Lead, Architect, Backend, Frontend, QA, Devops, each with a distinct persona and tool allowlist (architect is docs-only — no Edit/Bash; QA is read-only).
- Replace flat model aliases (`lead-model`/`engineer-model`/`qa-model`) with tiered logical aliases `frontier`/`mid`/`cheap`; define them in `infra/litellm/config.yaml` (frontier/mid → sonnet, cheap → haiku; distinct so frontier can be bumped to opus later with no code change).
- Teach the lead's orchestrator prompt *when* to dispatch each role via a pure static role guide.
- No orchestration-loop changes — the machinery already routes by role; this is data + one prompt enrichment.

Spec: `docs/specs/2026-06-16-yaah-full-team-roster-design.md`

## Test plan
- [ ] `make coverage` green (≥80%)
- [ ] `make lint` green
- [ ] `tests/unit/test_teams.py` — full roster, tier aliases, per-role tool grants
- [ ] `tests/integration/test_teams_api.py` — `/teams/default` returns 6 agents
- [ ] `tests/unit/test_orchestration_prompts.py` — role guide rendered
- [ ] `tests/unit/test_litellm_infra.py` — tier aliases present
EOF
)"
```

- [ ] **Step 5: Confirm CI is green on the PR**

Run: `gh pr checks --watch`
Expected: all checks pass.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- §3.1 roster → Task 2. §3.2 tier aliases → Tasks 1 + 2. §3.3 lead role-awareness → Task 4. §6 testing → Tasks 1–5 (unit + integration) and Task 6 (coverage/lint). §7 rollout (single PR, no migration) → Task 6. No gaps.

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"write tests for the above" — every code and test block is concrete.

**Type consistency:** `_DEFAULT_AGENTS` tuple shape unchanged from current code (only rows added + alias values changed), so `default_team()`'s comprehension is untouched. `_ROLE_GUIDE` keys are `AgentRole` members (all six exist in `domain/models.AgentRole`). Alias strings `frontier`/`mid`/`cheap` are identical across `teams.py`, the LiteLLM config, and every test assertion.

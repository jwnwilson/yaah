# ADR-0001: Local dev reset clears Temporal state, not just Postgres

**Date**: 2026-06-14
**Status**: accepted
**Deciders**: noel

## Context

yaah persists state in two independent stores: Postgres (domain rows — projects, runs, work items) and Temporal's own database (workflow execution state, in the `temporaldata` Docker volume). A `db-reset` that only wiped the Postgres schema left orphaned Temporal workflows alive. One such workflow (started with an older input shape) kept retrying and failing with `KeyError: 'project_id'` at the `capture_memory` step, because its run row no longer existed. A reset that addresses only one persistence layer produces a broken, not clean, local environment.

## Decision

`make db-reset` resets **both** persistence layers and then re-seeds startup data: it drops/recreates the Postgres schema and re-runs migrations, stops Temporal and removes its `temporaldata` volume (killing orphaned/stuck workflows), brings Temporal back fresh, and runs `make seed`. Startup data is created by a standalone, idempotent script (`src/interactors/seed.py`) that writes through the same owner-scoped UnitOfWork the API uses.

## Alternatives Considered

### Alternative 1: Wipe Postgres only
- **Pros**: Simplest; one command, one store.
- **Cons**: Leaves orphaned Temporal workflows retrying forever against missing data.
- **Why not**: It's the exact failure that motivated this ADR — a DB-only reset is not actually a reset.

### Alternative 2: Terminate stuck workflows via the Temporal CLI instead of wiping the volume
- **Pros**: Targeted; preserves unrelated workflow history.
- **Cons**: Requires enumerating/identifying bad workflows; history-replay non-determinism issues persist; more moving parts.
- **Why not**: For a local "give me a clean slate" command, nuking the volume is simpler and more reliable than surgical termination.

### Alternative 3: Seed via the live API (curl), as the `e2e-run` target does
- **Pros**: Reuses an existing pattern; exercises the real HTTP path.
- **Cons**: Requires the API to be running; couples reset to server startup ordering.
- **Why not**: A DB-only seeder (UoW) runs without the API up and keeps reset self-contained.

## Consequences

What becomes easier or more difficult to do because of this change?

### Positive
- `db-reset` yields a genuinely clean, immediately usable environment (clean DB + fresh Temporal + seeded board).
- The two-persistence-layer reality is now explicit and documented.
- The seed script is a reusable, idempotent source of startup data for any local workflow.

### Negative
- Removing the `temporaldata` volume discards *all* local workflow history, not just the broken run.
- Reset now depends on Docker volume operations (label lookup) in addition to SQL.

### Risks
- Volume-name coupling: mitigated by resolving the volume via the `com.docker.compose.volume=temporaldata` label rather than a hardcoded `<project>_temporaldata` name, so it works across worktrees / compose project names.

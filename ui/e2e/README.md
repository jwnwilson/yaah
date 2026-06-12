# E2E (Playwright)

Prereqs:
1. Backend running on `:8000` with the dev auth bypass (→ `dev-user`):
   ```bash
   YAAH_DATABASE_URL="sqlite:///:memory:" \
     uv run uvicorn --app-dir src interactors.api.app:create_app --factory --port 8000
   ```
   (or `make dev` against Postgres).
2. The frontend dev server is started automatically by Playwright (`webServer`,
   `reuseExistingServer: true` — it reuses one already on `:5173`).
3. Install the browser once: `npx playwright install chromium`.

Run: `cd ui && npm run e2e`

The happy path exercises: create project → open board → create an epic in the
hierarchy tree. It hits the real API through the Vite proxy (which strips the
`/api` prefix), so it also guards the proxy-rewrite regression that unit tests
(which mock `/api/*` directly) cannot catch.

Because it mutates real data, run against a disposable dev DB (the in-memory
SQLite command above resets on restart).

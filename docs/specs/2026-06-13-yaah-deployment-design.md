# yaah Deployment — Design

**Date:** 2026-06-13
**Status:** Draft (awaiting review)
**Reference implementation:** `/Users/noel/projects/llm_api` (ECR + S3/CloudFront + K8s + GitHub Actions OIDC)

## Goal

Deploy yaah's frontend (React/Vite UI) and full backend (FastAPI API, Temporal
server + worker, LiteLLM gateway, Postgres) to the **existing self-hosted
Kubernetes cluster**, using Terraform for AWS resources, GitHub Actions for
CI/CD, K8s YAML manifests for cluster workloads, and AWS S3 + CloudFront for the
static UI. The approach ports the battle-tested `llm_api` infrastructure,
scoped down to yaah's needs.

## Decisions (locked)

| Decision | Choice |
| --- | --- |
| Service scope | Full backend stack (API, Temporal server, worker, LiteLLM, Postgres) + UI |
| Cluster | Reuse the existing `llm_api` cluster (ingress-nginx, cert-manager, Route53 already present) |
| Namespace | **Shared namespace that the existing ECR refresher already covers** (assumed `default`; confirm) — no dedicated namespace |
| Database | In-cluster Postgres 16 StatefulSet + PVC |
| Domain | UI `yaah.jwnwilson.co.uk`, API `api.yaah.jwnwilson.co.uk` (Route53) |
| Registry | AWS ECR (private), ARM64 images |
| ECR pull creds | **Existing cluster refresher owns `ecr-credentials`** — yaah does not create or refresh it |
| Auth | `YAAH_AUTH_MODE=dev` (single `dev-user` owner) initially; Auth0 is a documented follow-up |

### Naming: `yaah-` prefix on everything

Because yaah shares a namespace with `llm_api`, every yaah K8s object is
prefixed to avoid collisions (the bare names `temporal`, `temporal-db`,
`postgres`, etc. are already owned by `llm_api`):

`yaah-api`, `yaah-db`, `yaah-temporal`, `yaah-temporal-db`,
`yaah-temporal-worker`, `yaah-litellm`, plus secrets `yaah-secrets` /
`yaah-db-secret` and ingress host `api.yaah.jwnwilson.co.uk`.

yaah runs its **own** Temporal server (`yaah-temporal`) rather than coupling to
`llm_api`'s, keeping the two systems independent.

## Architecture

```
Route53                                        AWS
  yaah.jwnwilson.co.uk ───────► CloudFront ───► S3 (Vite dist)            [UI]
  api.yaah.jwnwilson.co.uk ──┐
                             │   (cluster ingress public IP via Route53 A record)
                             ▼
  ingress-nginx ──► yaah-api Service ──► yaah-api Deployment (FastAPI, /health)
                                              │
  K8s shared namespace (default):             │ TEMPORAL_ADDRESS=yaah-temporal:7233
    ├─ yaah-temporal (temporalio/auto-setup) + yaah-temporal-db (StatefulSet)
    ├─ yaah-temporal-worker  Deployment  (infra/worker/Dockerfile)
    ├─ yaah-litellm          Deployment + Service + ConfigMap
    └─ yaah-db               Postgres 16 StatefulSet + PVC + headless Service

  ecr-credentials secret ........ provided by the existing cluster refresher
```

### Image flow (how logic lands on the cluster)

1. **Terraform** creates ECR repos `yaah-api` and `yaah-worker` (with lifecycle
   retention).
2. **GitHub Actions `deploy.yml`** authenticates to AWS via OIDC, logs into ECR,
   and builds + pushes ARM64 images tagged `:${GITHUB_SHA}` and `:latest`
   (buildx, registry build cache, `paths-filter` to skip unchanged images).
3. **Deploy step** `sed`-stamps the manifest placeholders
   (`<ECR_API_IMAGE>`, `<ECR_WORKER_IMAGE>`) with the freshly pushed refs, then
   `kubectl apply`s. Pods pull using the cluster-managed `ecr-credentials`
   secret referenced via `imagePullSecrets`.

## Components

### 1. API Dockerfile — `infra/api/Dockerfile` (new)

Slim FastAPI image, distinct from the worker (no node/claude-code):

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src ./src
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "--app-dir", "src", \
     "interactors.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
```

Built `linux/arm64` to match the cluster nodes.

### 2. Terraform — `infra/terraform/`

Ported and trimmed from the reference. Modules reused: `ecr`, `s3_static`,
`acm`, `dns`, `iam`. State in an S3 backend (bootstrap mirrors the reference).

- `module "ecr_api"` → repo `yaah-api`
- `module "ecr_worker"` → repo `yaah-worker`
- `module "acm_ui"` → ACM cert for `yaah.jwnwilson.co.uk` (us-east-1, for CloudFront)
- `module "s3_ui"` → S3 bucket + CloudFront distribution for the UI
- `module "dns"` → Route53: `yaah.jwnwilson.co.uk` (CloudFront alias) and
  `api.yaah.jwnwilson.co.uk` (A record → cluster ingress IP)
- `module "iam"` → GitHub-OIDC assumable role with policies for: ECR push/pull
  (both repos), S3 sync to the UI bucket, CloudFront invalidation

Outputs consumed by CI: ECR registry/repo names, UI bucket name, CloudFront
distribution ID, the OIDC role ARN.

> Terraform is **applied manually / out-of-band** (bootstrap once), not on every
> push. CI only runs `terraform fmt -check` + `validate` + `plan` on infra
> changes as a guardrail.

### 3. K8s manifests — `infra/k8s/yaah/`

All objects live in the shared namespace; no `namespace.yaml`.

| File | Contents |
| --- | --- |
| `api/deployment.yaml` | `yaah-api` Deployment, 2 replicas, RollingUpdate, `imagePullSecrets: ecr-credentials`, env from `yaah-secrets` + `yaah-db-secret`, `/health` liveness + readiness probes, image placeholder `<ECR_API_IMAGE>` |
| `api/service.yaml` | `yaah-api` ClusterIP Service → port 8000 |
| `api/ingress.yaml` | ingress-nginx + cert-manager TLS for `api.yaah.jwnwilson.co.uk` |
| `api/hpa.yaml` | HPA on CPU (e.g. 2–5 replicas) |
| `api/network-policy.yaml` | restrict ingress to nginx + intra-namespace egress (ported pattern) |
| `postgres.yaml` | `yaah-db` StatefulSet (postgres:16-alpine) + PVC (`local-path`) + headless Service; applied & waited on before the API |
| `temporal.yaml` | `yaah-temporal` (temporalio/auto-setup) + `yaah-temporal-db` StatefulSet + Services |
| `worker.yaml` | `yaah-temporal-worker` Deployment, image placeholder `<ECR_WORKER_IMAGE>`, `TEMPORAL_ADDRESS=yaah-temporal:7233` |
| `litellm.yaml` | `yaah-litellm` Deployment + Service + ConfigMap built from `infra/litellm/config.yaml` |

### 4. GitHub Actions — `.github/workflows/`

**`test.yml`** — the deploy gate. Runs on push/PR:
- Backend: `uv sync` + `uv run pytest` (existing 80% coverage gate)
- UI: `npm ci` + `npm test` + `npm run lint` (tsc)

**`deploy.yml`** — `on: workflow_run: [Test] completed` on `main` (+ manual):
1. `paths-filter` detects whether `src/**`, `pyproject.toml`, `uv.lock`,
   `infra/api/**`, `infra/worker/**`, or `infra/k8s/yaah/**` changed.
2. OIDC → AWS; `amazon-ecr-login`; buildx ARM64 build + push for `yaah-api`
   and `yaah-worker` (digest-pin when unchanged, registry cache).
3. Write kubeconfig from `KUBE_CONFIG` secret; `kubectl get nodes` connectivity check.
4. Sync runtime secrets: `yaah-db-secret` and `yaah-secrets` via
   `kubectl create secret … --dry-run=client -o yaml | kubectl apply -f -`.
   **(No `ecr-credentials` step — the cluster refresher owns it.)**
5. `sed`-stamp image placeholders; `kubectl apply` Postgres first and
   `kubectl rollout status statefulset/yaah-db` before applying the rest.
6. `kubectl rollout status` for `yaah-api`, `yaah-temporal-worker`.
7. Smoke test: `curl -fsS https://api.yaah.jwnwilson.co.uk/health` must return 200.
- `concurrency: { group: yaah-deploy, cancel-in-progress: false }` to serialize rollouts.

**`deploy-ui.yml`** — `on: workflow_run: [Test] completed` on `main` (+ manual):
1. `npm ci` + `npm run build` with `VITE_API_BASE_URL=https://api.yaah.jwnwilson.co.uk`.
2. OIDC → AWS; `aws s3 sync ui/dist/ s3://<bucket> --delete`.
3. `aws cloudfront create-invalidation --paths "/*"`.

### 5. App-code change — UI API base URL

Single touch in `ui/src/lib/api/client.ts`:

```ts
const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
```

Dev keeps the Vite `/api` proxy; production builds bake the absolute API host.
No other UI changes; yaah's UI has no Auth0 wiring today.

## Secrets & configuration

No secrets in git. Runtime secrets are minted in-cluster from GitHub Actions
secrets during `deploy.yml`:

- `yaah-db-secret`: `database-url`
  (`postgresql+psycopg://yaah:<pw>@yaah-db:5432/yaah`)
- `yaah-secrets`: `YAAH_ANTHROPIC_API_KEY`, `YAAH_SECRET_KEY`, GitHub App creds
  (`YAAH_GITHUB_APP_ID`, `YAAH_GITHUB_PRIVATE_KEY`, `YAAH_GITHUB_INSTALLATION_ID`,
  `YAAH_GITHUB_REPO`), LiteLLM keys (`YAAH_LITELLM_API_KEY`,
  `LITELLM_MASTER_KEY`) as applicable.

Required GitHub repo secrets: `AWS_ROLE_ARN`, `KUBE_CONFIG` (base64),
`UI_BUCKET`, `UI_CF_DISTRIBUTION_ID`, plus the runtime secret values above.

The API Deployment sets `YAAH_PROFILE=remote`, `YAAH_AUTH_MODE=dev`,
`YAAH_TEMPORAL_ADDRESS=yaah-temporal:7233`,
`YAAH_LITELLM_BASE_URL=http://yaah-litellm:4000`, and pulls `YAAH_DATABASE_URL`
from `yaah-db-secret`.

## Error handling & operability

- **Ordering:** Postgres StatefulSet applied and `rollout status`-gated before
  the API so first-boot table creation/migration resolves `yaah-db`.
- **Health:** `/health` liveness + readiness; HPA on CPU.
- **Idempotent secrets:** `--dry-run=client | kubectl apply` upserts safely.
- **Skip-on-no-change:** `paths-filter` avoids rebuilds for docs/UI-only pushes;
  unchanged images are redeployed by digest.
- **Serialized deploys:** concurrency group prevents racing rollouts.
- **Fail-closed:** the post-deploy `/health` smoke test fails the workflow on a
  bad rollout.

## Testing strategy

- `test.yml` (pytest 80% gate + UI tests/lint) is the mandatory gate before any
  deploy workflow runs.
- `terraform validate` + `plan` on infra-path changes (no auto-apply).
- Post-deploy `/health` smoke test in `deploy.yml`.

## Out of scope (documented follow-ups)

- Auth0 wiring (UI + API) — deployment ships in `dev` auth mode.
- Temporal Web UI exposure/ingress for yaah.
- RDS / managed Postgres migration.
- Staging environment / multi-env split.
- Observability stack (metrics/log shipping) beyond what the cluster provides.

## Open items to confirm on review

1. **Namespace name** — assumed `default` (the namespace your ECR refresher
   covers). Confirm the actual name.
2. **ARM64 vs AMD64** — assumed ARM64 to match the reference cluster nodes.
   Confirm node architecture.
3. **LiteLLM inclusion** — included as part of the full stack; drop if yaah will
   call Anthropic directly in this environment.

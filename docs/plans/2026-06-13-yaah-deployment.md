# yaah Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy yaah's React/Vite UI to S3+CloudFront and its full backend (FastAPI API, Temporal server + worker, LiteLLM, Postgres) to the existing Kubernetes cluster, provisioned by Terraform and shipped by GitHub Actions.

**Architecture:** Terraform creates AWS resources (ECR repos, UI S3+CloudFront+ACM, Route53 records, a GitHub-OIDC IAM role). GitHub Actions builds ARM64 images, pushes to ECR, and `kubectl apply`s manifests into the cluster's **`default` namespace** (every object prefixed `yaah-` to avoid collisions with the co-resident `llm_api` workloads). The cluster's existing ECR-credential refresher and ingress-nginx/cert-manager/Route53 are reused; yaah creates none of them.

**Tech Stack:** Terraform (AWS provider), GitHub Actions (OIDC), Docker buildx (ARM64), Kubernetes (Deployments/StatefulSets/Ingress/HPA/NetworkPolicy), AWS ECR/S3/CloudFront/Route53, FastAPI, React/Vite, Temporal, LiteLLM, Postgres 16.

**Reference:** `/Users/noel/projects/llm_api` — the proven implementation these files are ported from.

---

## Conventions used in this plan

- **Namespace:** `default` (the namespace the existing ECR refresher populates). All `kubectl` commands target it implicitly.
- **Resource prefix:** `yaah-`. Pod label key is `app`, e.g. `app: yaah-api`.
- **Domains:** UI `yaah.jwnwilson.co.uk`, API `api.yaah.jwnwilson.co.uk`. Route53 zone `jwnwilson.co.uk`.
- **Image arch:** `linux/arm64`.
- **Image placeholders** in manifests: `<ECR_API_IMAGE>`, `<ECR_WORKER_IMAGE>` (stamped by `sed` in `deploy.yml`).
- **Pull secret:** `ecr-credentials` (already present in `default`, refreshed by the cluster). Referenced, never created.
- **Commit style:** `<type>: <description>` (feat/fix/refactor/docs/test/chore/ci).

### Required GitHub repo secrets (set once, before `deploy.yml` runs)

| Secret | Purpose |
| --- | --- |
| `AWS_ROLE_ARN` | OIDC role ARN (Terraform output `github_actions_role_arn`) |
| `KUBE_CONFIG` | base64-encoded kubeconfig for the cluster |
| `UI_BUCKET` | UI S3 bucket name (Terraform output `ui_bucket_name`) |
| `UI_CF_DISTRIBUTION_ID` | CloudFront distribution id (Terraform output `ui_distribution_id`) |
| `YAAH_DB_PASSWORD` | Postgres password for `yaah-db` |
| `YAAH_SECRET_KEY` | Fernet key for secret-at-rest cipher |
| `ANTHROPIC_API_KEY` | Anthropic key (worker + LiteLLM) |
| `LITELLM_MASTER_KEY` | LiteLLM gateway master key |
| `YAAH_GITHUB_APP_ID`, `YAAH_GITHUB_PRIVATE_KEY`, `YAAH_GITHUB_INSTALLATION_ID`, `YAAH_GITHUB_REPO` | GitHub App creds for the forge adapter (optional in `dev`/fake mode — set empty string if unused) |

> These are **GitHub Actions secrets**, distinct from the in-cluster K8s Secrets that `deploy.yml` mints from them.

---

## File structure

```
ui/src/lib/api/client.ts            # MODIFY — API base URL from env
ui/src/vite-env.d.ts                # CREATE — type VITE_API_BASE_URL
ui/src/lib/api/client.test.ts       # CREATE — base-URL behavior test

infra/api/Dockerfile                # CREATE — slim FastAPI image

infra/terraform/
  versions.tf                       # CREATE — provider + backend pins
  backend.tf                        # CREATE — S3 remote state
  variables.tf                      # CREATE
  main.tf                           # CREATE — ecr/acm/s3/dns/iam wiring
  outputs.tf                        # CREATE
  modules/ecr/{main,variables,outputs}.tf
  modules/s3_static/{main,variables,outputs}.tf
  modules/acm/{main,variables,outputs}.tf
  modules/dns/{main,variables,outputs}.tf
  modules/iam/{main,variables,outputs}.tf

infra/k8s/yaah/
  postgres.yaml                     # yaah-db StatefulSet + Service + NetworkPolicy
  temporal.yaml                     # yaah-temporal + yaah-temporal-db
  api/deployment.yaml
  api/service.yaml
  api/ingress.yaml
  api/hpa.yaml
  worker.yaml                       # yaah-temporal-worker
  litellm.yaml                      # yaah-litellm Deployment + Service

.github/workflows/
  test.yml                          # deploy gate
  deploy.yml                        # backend build + k8s apply
  deploy-ui.yml                     # UI build + S3/CloudFront

docs/deployment.md                  # CREATE — bootstrap + ops runbook
```

---

## Task 1: UI API base URL from environment

**Files:**
- Modify: `ui/src/lib/api/client.ts:1`
- Create: `ui/src/vite-env.d.ts`
- Create: `ui/src/lib/api/client.test.ts`

- [ ] **Step 1: Write the failing test**

Create `ui/src/lib/api/client.test.ts`:

```typescript
import { describe, expect, it, vi, afterEach } from "vitest";

describe("api client base URL", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults to the /api dev proxy when no env override is set", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ success: true, data: { status: "ok" }, error: null }), {
          status: 200,
        }),
      );
    const { apiGet } = await import("./client");
    await apiGet("/health");
    expect(fetchSpy).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("uses VITE_API_BASE_URL as an absolute base when set", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.yaah.jwnwilson.co.uk");
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ success: true, data: { status: "ok" }, error: null }), {
          status: 200,
        }),
      );
    const { apiGet } = await import("./client");
    await apiGet("/health");
    expect(fetchSpy).toHaveBeenCalledWith(
      "https://api.yaah.jwnwilson.co.uk/health",
      expect.anything(),
    );
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ui && npx vitest run src/lib/api/client.test.ts`
Expected: FAIL — the second case calls `fetch("/api/health", …)` because `BASE` is hardcoded to `/api`.

- [ ] **Step 3: Implement the change**

Edit `ui/src/lib/api/client.ts` line 1, replacing:

```typescript
const BASE = "/api";
```

with:

```typescript
const BASE = import.meta.env.VITE_API_BASE_URL || "/api";
```

Create `ui/src/vite-env.d.ts`:

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ui && npx vitest run src/lib/api/client.test.ts`
Expected: PASS (both cases).

- [ ] **Step 5: Verify the type-check and full UI suite still pass**

Run: `cd ui && npm run lint && npx vitest run`
Expected: no TS errors; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add ui/src/lib/api/client.ts ui/src/vite-env.d.ts ui/src/lib/api/client.test.ts
git commit -m "feat: make UI API base URL configurable via VITE_API_BASE_URL"
```

---

## Task 2: Slim FastAPI API Dockerfile

**Files:**
- Create: `infra/api/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

Create `infra/api/Dockerfile`:

```dockerfile
# Slim API image — serves the FastAPI app only (no node/claude-code, unlike the worker).
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

- [ ] **Step 2: Build the image locally to verify it compiles**

Run: `cd /Users/noel/projects/yaah && docker build -f infra/api/Dockerfile -t yaah-api:local .`
Expected: build succeeds through all stages (the final `CMD` is not executed during build).

- [ ] **Step 3: Smoke-test the container against an ephemeral SQLite DB**

The app calls `create_all` on `YAAH_DATABASE_URL` at startup, so point it at an ephemeral SQLite file to confirm the image boots and `/health` responds:

```bash
docker run --rm -d --name yaah-api-smoke -p 8001:8000 \
  -e YAAH_DATABASE_URL="sqlite+pysqlite:////tmp/yaah.db" \
  yaah-api:local
sleep 5
curl -fsS http://localhost:8001/health
docker rm -f yaah-api-smoke
```

Expected: `{"success":true,"data":{"status":"ok"},"error":null}`.
(If `sqlite+pysqlite` is unavailable in the locked deps, skip the run and rely on the Step 2 build + the in-cluster Postgres smoke test in Task 12.)

- [ ] **Step 4: Commit**

```bash
git add infra/api/Dockerfile
git commit -m "feat: add slim FastAPI API Dockerfile"
```

---

## Task 3: Terraform — providers, backend, ECR module

**Files:**
- Create: `infra/terraform/versions.tf`
- Create: `infra/terraform/backend.tf`
- Create: `infra/terraform/variables.tf`
- Create: `infra/terraform/modules/ecr/main.tf`
- Create: `infra/terraform/modules/ecr/variables.tf`
- Create: `infra/terraform/modules/ecr/outputs.tf`

- [ ] **Step 1: Create `infra/terraform/versions.tf`**

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
```

- [ ] **Step 2: Create `infra/terraform/backend.tf`**

```hcl
# Remote state in S3. Create the bucket once, out-of-band, before `terraform init`:
#   aws s3 mb s3://yaah-terraform-state --region us-east-1
#   aws s3api put-bucket-versioning --bucket yaah-terraform-state \
#     --versioning-configuration Status=Enabled
terraform {
  backend "s3" {
    bucket = "yaah-terraform-state"
    key    = "yaah/terraform.tfstate"
    region = "us-east-1"
  }
}
```

- [ ] **Step 3: Create `infra/terraform/variables.tf`**

```hcl
variable "aws_region" {
  description = "AWS region for ECR/IAM. CloudFront+ACM for the UI are us-east-1 regardless."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "owner/name of the GitHub repo allowed to assume the OIDC role"
  type        = string
}

variable "zone_name" {
  description = "Route53 hosted zone name"
  type        = string
  default     = "jwnwilson.co.uk"
}

variable "ui_domain" {
  description = "Fully-qualified domain for the UI (CloudFront alias)"
  type        = string
  default     = "yaah.jwnwilson.co.uk"
}

variable "api_domain" {
  description = "Fully-qualified domain for the API ingress"
  type        = string
  default     = "api.yaah.jwnwilson.co.uk"
}

variable "cluster_ip" {
  description = "Public IP the cluster ingress is reachable on (for the api A record)"
  type        = string
}

variable "image_retention_count" {
  description = "Number of tagged images to retain per ECR repo"
  type        = number
  default     = 10
}
```

- [ ] **Step 4: Create the ECR module**

Create `infra/terraform/modules/ecr/variables.tf`:

```hcl
variable "repo_name" {
  type = string
}

variable "image_retention_count" {
  type    = number
  default = 10
}

variable "untagged_retention_days" {
  type    = number
  default = 7
}
```

Create `infra/terraform/modules/ecr/main.tf`:

```hcl
resource "aws_ecr_repository" "this" {
  name                 = var.repo_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than ${var.untagged_retention_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_retention_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Retain last ${var.image_retention_count} images (any tag)"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.image_retention_count
        }
        action = { type = "expire" }
      }
    ]
  })
}

data "aws_iam_policy_document" "ecr_push" {
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.this.arn]
  }
}

resource "aws_iam_policy" "ecr_push" {
  name   = "${var.repo_name}-ecr-push"
  policy = data.aws_iam_policy_document.ecr_push.json
}
```

Create `infra/terraform/modules/ecr/outputs.tf`:

```hcl
output "repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  value = aws_ecr_repository.this.arn
}

output "ecr_push_policy_arn" {
  value = aws_iam_policy.ecr_push.arn
}
```

- [ ] **Step 5: Wire the ECR repos into root `main.tf` (partial)**

Create `infra/terraform/main.tf` with just the ECR modules for now (later tasks append to it):

```hcl
module "ecr_api" {
  source                = "./modules/ecr"
  repo_name             = "yaah-api"
  image_retention_count = var.image_retention_count
}

module "ecr_worker" {
  source                = "./modules/ecr"
  repo_name             = "yaah-worker"
  image_retention_count = var.image_retention_count
}
```

- [ ] **Step 6: Validate**

Run:
```bash
cd /Users/noel/projects/yaah/infra/terraform
terraform fmt -recursive
terraform init -backend=false
terraform validate
```
Expected: `terraform validate` prints `Success! The configuration is valid.`
(`-backend=false` skips needing the real S3 state bucket for validation.)

- [ ] **Step 7: Commit**

```bash
git add infra/terraform/versions.tf infra/terraform/backend.tf infra/terraform/variables.tf \
  infra/terraform/main.tf infra/terraform/modules/ecr
git commit -m "feat: terraform ECR repos for yaah-api and yaah-worker"
```

---

## Task 4: Terraform — ACM, S3+CloudFront, DNS

**Files:**
- Create: `infra/terraform/modules/acm/{main,variables,outputs}.tf`
- Create: `infra/terraform/modules/s3_static/{main,variables,outputs}.tf`
- Create: `infra/terraform/modules/dns/{main,variables,outputs}.tf`
- Modify: `infra/terraform/main.tf` (append)

- [ ] **Step 1: Create the ACM module**

Create `infra/terraform/modules/acm/variables.tf`:

```hcl
variable "domain" {
  type = string
}

variable "zone_name" {
  type = string
}
```

Create `infra/terraform/modules/acm/main.tf`:

```hcl
# CloudFront requires its ACM cert in us-east-1. This module must be instantiated
# with a us-east-1 provider.
data "aws_route53_zone" "zone" {
  name         = var.zone_name
  private_zone = false
}

resource "aws_acm_certificate" "this" {
  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "validation" {
  for_each = {
    for dvo in aws_acm_certificate.this.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id         = data.aws_route53_zone.zone.zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for r in aws_route53_record.validation : r.fqdn]
}
```

Create `infra/terraform/modules/acm/outputs.tf`:

```hcl
output "certificate_arn" {
  value = aws_acm_certificate_validation.this.certificate_arn
}
```

- [ ] **Step 2: Create the s3_static module**

Create `infra/terraform/modules/s3_static/variables.tf`:

```hcl
variable "name" {
  description = "S3 bucket name (also used as CloudFront origin id)"
  type        = string
}

variable "domain" {
  description = "CloudFront alias domain"
  type        = string
}

variable "acm_certificate_arn" {
  type = string
}
```

Create `infra/terraform/modules/s3_static/main.tf`:

```hcl
resource "aws_s3_bucket" "this" {
  bucket = var.name
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "this" {
  name                              = var.name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  default_root_object = "index.html"
  aliases             = [var.domain]

  origin {
    domain_name              = aws_s3_bucket.this.bucket_regional_domain_name
    origin_id                = "s3-${var.name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${var.name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
  }

  # SPA routing: S3+OAC returns 403 for missing keys, not 404.
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  price_class = "PriceClass_100"
}

data "aws_iam_policy_document" "cf_oac" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket     = aws_s3_bucket.this.id
  policy     = data.aws_iam_policy_document.cf_oac.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}
```

Create `infra/terraform/modules/s3_static/outputs.tf`:

```hcl
output "bucket_name" {
  value = aws_s3_bucket.this.id
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.this.domain_name
}

output "distribution_id" {
  value = aws_cloudfront_distribution.this.id
}

output "distribution_arn" {
  value = aws_cloudfront_distribution.this.arn
}
```

- [ ] **Step 3: Create the DNS module**

Create `infra/terraform/modules/dns/variables.tf`:

```hcl
variable "zone_name" {
  type = string
}

variable "ui_domain" {
  type = string
}

variable "api_domain" {
  type = string
}

variable "ui_cf_domain" {
  description = "CloudFront distribution domain for the UI CNAME"
  type        = string
}

variable "cluster_ip" {
  description = "Public IP for the API A record"
  type        = string
}
```

Create `infra/terraform/modules/dns/main.tf`:

```hcl
data "aws_route53_zone" "zone" {
  name         = var.zone_name
  private_zone = false
}

resource "aws_route53_record" "ui" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = var.ui_domain
  type    = "CNAME"
  ttl     = 300
  records = [var.ui_cf_domain]
}

resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = var.api_domain
  type    = "A"
  ttl     = 300
  records = [var.cluster_ip]
}
```

Create `infra/terraform/modules/dns/outputs.tf`:

```hcl
output "ui_fqdn" {
  value = aws_route53_record.ui.fqdn
}

output "api_fqdn" {
  value = aws_route53_record.api.fqdn
}
```

- [ ] **Step 4: Append the UI/DNS wiring to root `main.tf`**

Append to `infra/terraform/main.tf`:

```hcl
# CloudFront + its ACM cert must live in us-east-1, independent of var.aws_region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

module "acm_ui" {
  source    = "./modules/acm"
  providers = { aws = aws.us_east_1 }
  domain    = var.ui_domain
  zone_name = var.zone_name
}

module "s3_ui" {
  source              = "./modules/s3_static"
  providers           = { aws = aws.us_east_1 }
  name                = "yaah-ui"
  domain              = var.ui_domain
  acm_certificate_arn = module.acm_ui.certificate_arn
}

module "dns" {
  source       = "./modules/dns"
  zone_name    = var.zone_name
  ui_domain    = var.ui_domain
  api_domain   = var.api_domain
  ui_cf_domain = module.s3_ui.cloudfront_domain
  cluster_ip   = var.cluster_ip
}
```

- [ ] **Step 5: Validate**

Run:
```bash
cd /Users/noel/projects/yaah/infra/terraform
terraform fmt -recursive
terraform init -backend=false
terraform validate
```
Expected: `Success! The configuration is valid.`

- [ ] **Step 6: Commit**

```bash
git add infra/terraform/modules/acm infra/terraform/modules/s3_static \
  infra/terraform/modules/dns infra/terraform/main.tf
git commit -m "feat: terraform ACM cert, S3+CloudFront UI hosting, Route53 records"
```

---

## Task 5: Terraform — GitHub OIDC IAM role and outputs

**Files:**
- Create: `infra/terraform/modules/iam/{main,variables,outputs}.tf`
- Modify: `infra/terraform/main.tf` (append)
- Create: `infra/terraform/outputs.tf`

- [ ] **Step 1: Create the IAM module variables**

Create `infra/terraform/modules/iam/variables.tf`:

```hcl
variable "github_repo" {
  description = "owner/name allowed to assume the role"
  type        = string
}

variable "ecr_push_policy_arns" {
  description = "ECR push policy ARNs to attach to the CI role"
  type        = list(string)
}

variable "ui_bucket_arn" {
  type = string
}

variable "ui_distribution_arn" {
  type = string
}

variable "tf_state_bucket" {
  type    = string
  default = "yaah-terraform-state"
}
```

- [ ] **Step 2: Create the IAM module main**

Create `infra/terraform/modules/iam/main.tf`:

```hcl
# GitHub Actions OIDC — lets the workflow assume this role without long-lived keys.
# If the OIDC provider already exists in the account (e.g. created by another
# project), import it instead of recreating: `terraform import module.iam.aws_iam_openid_connect_provider.github <arn>`.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repo}:ref:refs/heads/main",
        "repo:${var.github_repo}:pull_request",
      ]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "yaah-github-actions"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "ecr" {
  count      = length(var.ecr_push_policy_arns)
  role       = aws_iam_role.github_actions.name
  policy_arn = var.ecr_push_policy_arns[count.index]
}

data "aws_iam_policy_document" "ui_deploy" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.ui_bucket_arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.ui_bucket_arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [var.ui_distribution_arn]
  }
}

resource "aws_iam_policy" "ui_deploy" {
  name   = "yaah-ui-deploy"
  policy = data.aws_iam_policy_document.ui_deploy.json
}

resource "aws_iam_role_policy_attachment" "ui_deploy" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.ui_deploy.arn
}

# Read/write the Terraform remote state so CI can run `plan`.
data "aws_iam_policy_document" "tf_state" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.tf_state_bucket}"]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::${var.tf_state_bucket}/yaah/terraform.tfstate"]
  }
}

resource "aws_iam_policy" "tf_state" {
  name   = "yaah-terraform-state"
  policy = data.aws_iam_policy_document.tf_state.json
}

resource "aws_iam_role_policy_attachment" "tf_state" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.tf_state.arn
}
```

Create `infra/terraform/modules/iam/outputs.tf`:

```hcl
output "role_arn" {
  value = aws_iam_role.github_actions.arn
}
```

- [ ] **Step 3: Append IAM wiring to root `main.tf`**

Append to `infra/terraform/main.tf`:

```hcl
module "iam" {
  source      = "./modules/iam"
  github_repo = var.github_repo
  ecr_push_policy_arns = [
    module.ecr_api.ecr_push_policy_arn,
    module.ecr_worker.ecr_push_policy_arn,
  ]
  ui_bucket_arn       = module.s3_ui.bucket_arn
  ui_distribution_arn = module.s3_ui.distribution_arn
}
```

- [ ] **Step 4: Create root `outputs.tf`**

Create `infra/terraform/outputs.tf`:

```hcl
output "ecr_api_repository_url" {
  value = module.ecr_api.repository_url
}

output "ecr_worker_repository_url" {
  value = module.ecr_worker.repository_url
}

output "ui_bucket_name" {
  value = module.s3_ui.bucket_name
}

output "ui_distribution_id" {
  value = module.s3_ui.distribution_id
}

output "ui_cloudfront_domain" {
  value = module.s3_ui.cloudfront_domain
}

output "github_actions_role_arn" {
  value = module.iam.role_arn
}
```

- [ ] **Step 5: Validate**

Run:
```bash
cd /Users/noel/projects/yaah/infra/terraform
terraform fmt -recursive
terraform init -backend=false
terraform validate
```
Expected: `Success! The configuration is valid.`

- [ ] **Step 6: Commit**

```bash
git add infra/terraform/modules/iam infra/terraform/main.tf infra/terraform/outputs.tf
git commit -m "feat: terraform GitHub OIDC IAM role and stack outputs"
```

---

## Task 6: K8s — Postgres for yaah

**Files:**
- Create: `infra/k8s/yaah/postgres.yaml`

- [ ] **Step 1: Create the manifest**

Create `infra/k8s/yaah/postgres.yaml`:

```yaml
# --- PostgreSQL for the yaah application ---
apiVersion: v1
kind: Service
metadata:
  name: yaah-db
spec:
  clusterIP: None
  selector:
    app: yaah-db
  ports:
    - port: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: yaah-db
spec:
  serviceName: yaah-db
  replicas: 1
  selector:
    matchLabels:
      app: yaah-db
  template:
    metadata:
      labels:
        app: yaah-db
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          env:
            - name: POSTGRES_USER
              value: yaah
            - name: POSTGRES_DB
              value: yaah
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: yaah-db-secret
                  key: postgres-password
          ports:
            - containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "yaah"]
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: local-path
        resources:
          requests:
            storage: 5Gi
---
# Only yaah-api and yaah-temporal-worker pods may reach the DB.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: yaah-db-ingress-only
spec:
  podSelector:
    matchLabels:
      app: yaah-db
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: yaah-api
        - podSelector:
            matchLabels:
              app: yaah-temporal-worker
      ports:
        - port: 5432
```

- [ ] **Step 2: Validate the manifest syntax (no cluster needed)**

Run: `kubectl apply --dry-run=client -f infra/k8s/yaah/postgres.yaml`
Expected: each object prints `… (dry run)` with no errors.

- [ ] **Step 3: Commit**

```bash
git add infra/k8s/yaah/postgres.yaml
git commit -m "feat: k8s Postgres StatefulSet for yaah"
```

---

## Task 7: K8s — Temporal server for yaah

**Files:**
- Create: `infra/k8s/yaah/temporal.yaml`

- [ ] **Step 1: Create the manifest**

Create `infra/k8s/yaah/temporal.yaml`:

```yaml
# --- PostgreSQL backing Temporal ---
apiVersion: v1
kind: Service
metadata:
  name: yaah-temporal-db
spec:
  clusterIP: None
  selector:
    app: yaah-temporal-db
  ports:
    - port: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: yaah-temporal-db
spec:
  serviceName: yaah-temporal-db
  replicas: 1
  selector:
    matchLabels:
      app: yaah-temporal-db
  template:
    metadata:
      labels:
        app: yaah-temporal-db
    spec:
      containers:
        - name: postgres
          image: postgres:15-alpine
          env:
            - name: POSTGRES_USER
              value: temporal
            - name: POSTGRES_PASSWORD
              value: temporal
            - name: POSTGRES_DB
              value: temporal
          ports:
            - containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "temporal"]
            initialDelaySeconds: 5
            periodSeconds: 5
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: local-path
        resources:
          requests:
            storage: 5Gi
---
# --- Temporal server (auto-setup creates schema + the "default" namespace) ---
apiVersion: v1
kind: Service
metadata:
  name: yaah-temporal
spec:
  selector:
    app: yaah-temporal
  ports:
    - name: grpc
      port: 7233
      targetPort: 7233
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yaah-temporal
spec:
  replicas: 1
  selector:
    matchLabels:
      app: yaah-temporal
  template:
    metadata:
      labels:
        app: yaah-temporal
    spec:
      containers:
        - name: temporal
          image: temporalio/auto-setup:1.27
          ports:
            - containerPort: 7233
          env:
            - name: DB
              value: postgres12
            - name: DB_PORT
              value: "5432"
            - name: POSTGRES_USER
              value: temporal
            - name: POSTGRES_PWD
              value: temporal
            - name: POSTGRES_SEEDS
              value: yaah-temporal-db
          readinessProbe:
            tcpSocket:
              port: 7233
            initialDelaySeconds: 20
            periodSeconds: 10
```

- [ ] **Step 2: Validate**

Run: `kubectl apply --dry-run=client -f infra/k8s/yaah/temporal.yaml`
Expected: all objects print `… (dry run)` with no errors.

- [ ] **Step 3: Commit**

```bash
git add infra/k8s/yaah/temporal.yaml
git commit -m "feat: k8s Temporal server + backing Postgres for yaah"
```

---

## Task 8: K8s — API Deployment, Service, Ingress, HPA

**Files:**
- Create: `infra/k8s/yaah/api/deployment.yaml`
- Create: `infra/k8s/yaah/api/service.yaml`
- Create: `infra/k8s/yaah/api/ingress.yaml`
- Create: `infra/k8s/yaah/api/hpa.yaml`

- [ ] **Step 1: Create the Deployment**

Create `infra/k8s/yaah/api/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yaah-api
  labels:
    app: yaah-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: yaah-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: yaah-api
    spec:
      imagePullSecrets:
        - name: ecr-credentials
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: node-role.kubernetes.io/control-plane
                    operator: DoesNotExist
      containers:
        - name: yaah-api
          image: <ECR_API_IMAGE>
          ports:
            - containerPort: 8000
          env:
            - name: YAAH_PROFILE
              value: remote
            - name: YAAH_AUTH_MODE
              value: dev
            - name: YAAH_TEMPORAL_ADDRESS
              value: yaah-temporal:7233
            - name: YAAH_LITELLM_BASE_URL
              value: http://yaah-litellm:4000
            - name: YAAH_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: yaah-db-secret
                  key: database-url
            - name: YAAH_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: secret-key
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 20
            periodSeconds: 30
            timeoutSeconds: 10
            failureThreshold: 5
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 15
            timeoutSeconds: 10
            failureThreshold: 6
```

- [ ] **Step 2: Create the Service**

Create `infra/k8s/yaah/api/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: yaah-api
spec:
  selector:
    app: yaah-api
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: ClusterIP
```

- [ ] **Step 3: Create the Ingress**

Create `infra/k8s/yaah/api/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: yaah-api
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt"
    nginx.ingress.kubernetes.io/limit-rps: "10"
    nginx.ingress.kubernetes.io/limit-connections: "5"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.yaah.jwnwilson.co.uk
      secretName: yaah-api-tls
  rules:
    - host: "api.yaah.jwnwilson.co.uk"
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: yaah-api
                port:
                  number: 80
```

> The `letsencrypt` cluster-issuer name is the one the reference uses. If the
> shared cluster's issuer is named differently, fix the annotation here during
> bootstrap (confirm with `kubectl get clusterissuer`).

- [ ] **Step 4: Create the HPA**

Create `infra/k8s/yaah/api/hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: yaah-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: yaah-api
  minReplicas: 2
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

- [ ] **Step 5: Validate (the Deployment carries an image placeholder, so stamp before dry-run)**

Run:
```bash
sed 's|<ECR_API_IMAGE>|placeholder:latest|' infra/k8s/yaah/api/deployment.yaml \
  | kubectl apply --dry-run=client -f -
kubectl apply --dry-run=client -f infra/k8s/yaah/api/service.yaml
kubectl apply --dry-run=client -f infra/k8s/yaah/api/ingress.yaml
kubectl apply --dry-run=client -f infra/k8s/yaah/api/hpa.yaml
```
Expected: all objects print `… (dry run)` with no errors.

- [ ] **Step 6: Commit**

```bash
git add infra/k8s/yaah/api
git commit -m "feat: k8s API Deployment, Service, Ingress, HPA for yaah"
```

---

## Task 9: K8s — Temporal worker Deployment

**Files:**
- Create: `infra/k8s/yaah/worker.yaml`

- [ ] **Step 1: Create the manifest**

Create `infra/k8s/yaah/worker.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yaah-temporal-worker
  labels:
    app: yaah-temporal-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: yaah-temporal-worker
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: yaah-temporal-worker
    spec:
      imagePullSecrets:
        - name: ecr-credentials
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: node-role.kubernetes.io/control-plane
                    operator: DoesNotExist
      containers:
        - name: yaah-temporal-worker
          image: <ECR_WORKER_IMAGE>
          env:
            - name: YAAH_PROFILE
              value: remote
            - name: YAAH_TEMPORAL_ADDRESS
              value: yaah-temporal:7233
            - name: YAAH_LITELLM_BASE_URL
              value: http://yaah-litellm:4000
            - name: YAAH_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: yaah-db-secret
                  key: database-url
            - name: YAAH_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: secret-key
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: anthropic-api-key
            - name: YAAH_GITHUB_APP_ID
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: github-app-id
            - name: YAAH_GITHUB_PRIVATE_KEY
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: github-private-key
            - name: YAAH_GITHUB_INSTALLATION_ID
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: github-installation-id
            - name: YAAH_GITHUB_REPO
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: github-repo
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "4Gi"
```

- [ ] **Step 2: Validate**

Run:
```bash
sed 's|<ECR_WORKER_IMAGE>|placeholder:latest|' infra/k8s/yaah/worker.yaml \
  | kubectl apply --dry-run=client -f -
```
Expected: prints `deployment.apps/yaah-temporal-worker … (dry run)` with no errors.

- [ ] **Step 3: Commit**

```bash
git add infra/k8s/yaah/worker.yaml
git commit -m "feat: k8s Temporal worker Deployment for yaah"
```

---

## Task 10: K8s — LiteLLM gateway

**Files:**
- Create: `infra/k8s/yaah/litellm.yaml`

The LiteLLM config (`infra/litellm/config.yaml`) is loaded into a ConfigMap by
`deploy.yml` (`--from-file`), so this manifest only declares the Deployment +
Service that mount it. This keeps the config single-sourced (no YAML duplication).

- [ ] **Step 1: Create the manifest**

Create `infra/k8s/yaah/litellm.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: yaah-litellm
spec:
  selector:
    app: yaah-litellm
  ports:
    - protocol: TCP
      port: 4000
      targetPort: 4000
  type: ClusterIP
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yaah-litellm
  labels:
    app: yaah-litellm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: yaah-litellm
  template:
    metadata:
      labels:
        app: yaah-litellm
    spec:
      containers:
        - name: litellm
          image: ghcr.io/berriai/litellm:main-v1.55.8
          args: ["--config", "/app/config.yaml", "--port", "4000"]
          ports:
            - containerPort: 4000
          env:
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: anthropic-api-key
            - name: LITELLM_MASTER_KEY
              valueFrom:
                secretKeyRef:
                  name: yaah-secrets
                  key: litellm-master-key
          volumeMounts:
            - name: config
              mountPath: /app/config.yaml
              subPath: config.yaml
          readinessProbe:
            httpGet:
              path: /health/liveliness
              port: 4000
            initialDelaySeconds: 10
            periodSeconds: 15
      volumes:
        - name: config
          configMap:
            name: yaah-litellm-config
```

- [ ] **Step 2: Validate**

Run:
```bash
kubectl apply --dry-run=client -f infra/k8s/yaah/litellm.yaml
```
Expected: `service/yaah-litellm` and `deployment.apps/yaah-litellm` print `… (dry run)` with no errors. (Client-side dry-run does not resolve the ConfigMap reference, so no ConfigMap is needed here.)

- [ ] **Step 3: Commit**

```bash
git add infra/k8s/yaah/litellm.yaml
git commit -m "feat: k8s LiteLLM gateway Deployment + Service for yaah"
```

---

## Task 11: GitHub Actions — test gate

**Files:**
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/test.yml`:

```yaml
name: Test

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Set up Python
        run: uv python install 3.12
      - name: Sync deps
        run: uv sync --frozen
      - name: Run tests
        run: uv run pytest

  ui:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
          cache-dependency-path: ui/package-lock.json
      - name: Install
        working-directory: ui
        run: npm ci
      - name: Type-check
        working-directory: ui
        run: npm run lint
      - name: Unit tests
        working-directory: ui
        run: npm test
```

- [ ] **Step 2: Lint the workflow YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add Test workflow (pytest + UI) as the deploy gate"
```

---

## Task 12: GitHub Actions — backend build + deploy

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy Backend

on:
  workflow_run:
    workflows: [Test]
    types: [completed]
    branches: [main]
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: us-east-1
  ECR_API_REPOSITORY: yaah-api
  ECR_WORKER_REPOSITORY: yaah-worker

jobs:
  build:
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    outputs:
      api_image: ${{ steps.api-image.outputs.image }}
      worker_image: ${{ steps.worker-image.outputs.image }}
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Set up QEMU (arm64 cross-build)
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push API image (arm64)
        uses: docker/build-push-action@v5
        with:
          context: .
          file: infra/api/Dockerfile
          platforms: linux/arm64
          push: true
          tags: |
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_API_REPOSITORY }}:${{ github.sha }}
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_API_REPOSITORY }}:latest
          cache-from: type=registry,ref=${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_API_REPOSITORY }}:buildcache
          cache-to: type=registry,ref=${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_API_REPOSITORY }}:buildcache,mode=min

      - name: Export API image ref
        id: api-image
        run: echo "image=${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_API_REPOSITORY }}:${{ github.sha }}" >> "$GITHUB_OUTPUT"

      - name: Build and push worker image (arm64)
        uses: docker/build-push-action@v5
        with:
          context: .
          file: infra/worker/Dockerfile
          platforms: linux/arm64
          push: true
          tags: |
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_WORKER_REPOSITORY }}:${{ github.sha }}
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_WORKER_REPOSITORY }}:latest
          cache-from: type=registry,ref=${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_WORKER_REPOSITORY }}:buildcache
          cache-to: type=registry,ref=${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_WORKER_REPOSITORY }}:buildcache,mode=min

      - name: Export worker image ref
        id: worker-image
        run: echo "image=${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_WORKER_REPOSITORY }}:${{ github.sha }}" >> "$GITHUB_OUTPUT"

  deploy:
    needs: build
    runs-on: ubuntu-latest
    concurrency:
      group: yaah-deploy
      cancel-in-progress: false
    env:
      API_IMAGE: ${{ needs.build.outputs.api_image }}
      WORKER_IMAGE: ${{ needs.build.outputs.worker_image }}
    steps:
      - uses: actions/checkout@v4

      - name: Write kubeconfig
        run: |
          mkdir -p ~/.kube
          echo "${{ secrets.KUBE_CONFIG }}" | base64 -d > ~/.kube/config
          chmod 600 ~/.kube/config

      - name: Verify cluster connectivity
        run: kubectl get nodes -o name

      - name: Sync yaah-db-secret
        run: |
          DB_PW='${{ secrets.YAAH_DB_PASSWORD }}'
          kubectl create secret generic yaah-db-secret \
            --from-literal=postgres-password="${DB_PW}" \
            --from-literal=database-url="postgresql+psycopg://yaah:${DB_PW}@yaah-db:5432/yaah" \
            --dry-run=client -o yaml | kubectl apply -f -

      - name: Sync yaah-secrets
        run: |
          kubectl create secret generic yaah-secrets \
            --from-literal=secret-key='${{ secrets.YAAH_SECRET_KEY }}' \
            --from-literal=anthropic-api-key='${{ secrets.ANTHROPIC_API_KEY }}' \
            --from-literal=litellm-master-key='${{ secrets.LITELLM_MASTER_KEY }}' \
            --from-literal=github-app-id='${{ secrets.YAAH_GITHUB_APP_ID }}' \
            --from-literal=github-private-key='${{ secrets.YAAH_GITHUB_PRIVATE_KEY }}' \
            --from-literal=github-installation-id='${{ secrets.YAAH_GITHUB_INSTALLATION_ID }}' \
            --from-literal=github-repo='${{ secrets.YAAH_GITHUB_REPO }}' \
            --dry-run=client -o yaml | kubectl apply -f -

      - name: Sync LiteLLM config ConfigMap
        run: |
          kubectl create configmap yaah-litellm-config \
            --from-file=config.yaml=infra/litellm/config.yaml \
            --dry-run=client -o yaml | kubectl apply -f -

      - name: Apply databases first and wait
        run: |
          kubectl apply -f infra/k8s/yaah/postgres.yaml
          kubectl apply -f infra/k8s/yaah/temporal.yaml
          kubectl rollout status statefulset/yaah-db --timeout=180s
          kubectl rollout status statefulset/yaah-temporal-db --timeout=180s
          kubectl rollout status deployment/yaah-temporal --timeout=300s

      - name: Stamp images and apply the rest
        run: |
          sed -i "s|<ECR_API_IMAGE>|$API_IMAGE|g" infra/k8s/yaah/api/deployment.yaml
          sed -i "s|<ECR_WORKER_IMAGE>|$WORKER_IMAGE|g" infra/k8s/yaah/worker.yaml
          kubectl apply -f infra/k8s/yaah/litellm.yaml
          kubectl apply -f infra/k8s/yaah/api/
          kubectl apply -f infra/k8s/yaah/worker.yaml

      - name: Wait for rollouts
        run: |
          kubectl rollout status deployment/yaah-api --timeout=300s
          kubectl rollout status deployment/yaah-temporal-worker --timeout=300s
          kubectl rollout status deployment/yaah-litellm --timeout=180s

      - name: Smoke test the API
        run: |
          for i in $(seq 1 10); do
            if curl -fsS https://api.yaah.jwnwilson.co.uk/health; then
              echo "health ok"; exit 0
            fi
            echo "attempt $i failed, retrying in 10s"; sleep 10
          done
          echo "API health check never succeeded"; exit 1
```

- [ ] **Step 2: Lint the workflow YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add backend build + k8s deploy workflow"
```

---

## Task 13: GitHub Actions — UI deploy

**Files:**
- Create: `.github/workflows/deploy-ui.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/deploy-ui.yml`:

```yaml
name: Deploy UI

on:
  workflow_run:
    workflows: [Test]
    types: [completed]
    branches: [main]
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: us-east-1

jobs:
  deploy:
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
          cache-dependency-path: ui/package-lock.json

      - name: Install dependencies
        working-directory: ui
        run: npm ci

      - name: Build
        working-directory: ui
        env:
          VITE_API_BASE_URL: https://api.yaah.jwnwilson.co.uk
        run: npm run build

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Sync to S3
        run: aws s3 sync ui/dist/ s3://${{ secrets.UI_BUCKET }} --delete

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.UI_CF_DISTRIBUTION_ID }} \
            --paths "/*"
```

- [ ] **Step 2: Lint the workflow YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-ui.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-ui.yml
git commit -m "ci: add UI build + S3/CloudFront deploy workflow"
```

---

## Task 14: Deployment runbook + CLAUDE.md note

**Files:**
- Create: `docs/deployment.md`
- Modify: `CLAUDE.md` (Dev commands area)

- [ ] **Step 1: Write the runbook**

Create `docs/deployment.md`:

```markdown
# yaah Deployment Runbook

Production deploy: UI on S3+CloudFront, backend on the shared K8s cluster
(`default` namespace, every object prefixed `yaah-`). See the design spec at
`docs/specs/2026-06-13-yaah-deployment-design.md`.

## One-time bootstrap

1. **Terraform state bucket** (out-of-band):
   ```bash
   aws s3 mb s3://yaah-terraform-state --region us-east-1
   aws s3api put-bucket-versioning --bucket yaah-terraform-state \
     --versioning-configuration Status=Enabled
   ```
2. **Apply Terraform:**
   ```bash
   cd infra/terraform
   terraform init
   terraform apply -var github_repo=<owner/name> -var cluster_ip=<ingress public IP>
   ```
   If the account already has a GitHub OIDC provider, import it first:
   `terraform import module.iam.aws_iam_openid_connect_provider.github <arn>`.
3. **Record outputs** and set them as GitHub repo secrets:
   `terraform output` -> `AWS_ROLE_ARN`, `UI_BUCKET`, `UI_CF_DISTRIBUTION_ID`.
4. **Set the remaining GitHub secrets** (see the plan's secrets table):
   `KUBE_CONFIG` (base64), `YAAH_DB_PASSWORD`, `YAAH_SECRET_KEY`,
   `ANTHROPIC_API_KEY`, `LITELLM_MASTER_KEY`, and the `YAAH_GITHUB_*` set.
5. **Confirm the cluster prerequisites** (already present from llm_api):
   `kubectl get clusterissuer` (issuer name matches the ingress annotation),
   `kubectl -n default get secret ecr-credentials` (refresher is populating it).

## Routine deploys

Push to `main`. `Test` runs; on success `Deploy Backend` and `Deploy UI` fire
automatically. Manual re-deploy: run either workflow via `workflow_dispatch`.

## Rollback

- Backend: re-run `Deploy Backend` against an earlier commit, or
  `kubectl rollout undo deployment/yaah-api` (and `.../yaah-temporal-worker`).
- UI: re-run `Deploy UI` from an earlier commit (S3 sync + invalidation).

## Known follow-ups (out of scope here)

Auth0 wiring (API ships in `dev` auth mode = single shared owner), Temporal Web
UI exposure, managed Postgres (RDS), staging environment.
```

- [ ] **Step 2: Add a pointer in CLAUDE.md**

In `CLAUDE.md`, inside the `## Dev commands` fenced code block, add this line
after the existing `litellm` line (still inside the code fence):

```bash
# Deploy: push to main -> GitHub Actions (see docs/deployment.md). Manual: gh workflow run "Deploy Backend"
```

- [ ] **Step 3: Verify the docs are present and parse**

Run:
```bash
test -f docs/specs/2026-06-13-yaah-deployment-design.md && echo "spec present"
test -f docs/deployment.md && echo "runbook present"
grep -q "docs/deployment.md" CLAUDE.md && echo "pointer added"
```
Expected: `spec present`, `runbook present`, `pointer added`.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment.md CLAUDE.md
git commit -m "docs: add yaah deployment runbook and CLAUDE.md pointer"
```

---

## Final verification (after all tasks)

- [ ] `cd ui && npx vitest run && npm run lint` — UI green.
- [ ] `cd infra/terraform && terraform init -backend=false && terraform validate` — `Success!`.
- [ ] `for f in $(find infra/k8s/yaah -name '*.yaml'); do sed -e 's|<ECR_API_IMAGE>|p:latest|' -e 's|<ECR_WORKER_IMAGE>|p:latest|' "$f" | kubectl apply --dry-run=client -f - ; done` — all objects valid.
- [ ] `for f in .github/workflows/*.yml; do python3 -c "import yaml;yaml.safe_load(open('$f'))"; done` — all workflows parse.
- [ ] `docker build -f infra/api/Dockerfile -t yaah-api:local .` — image builds.
- [ ] Spec coverage walk: each component in `docs/specs/2026-06-13-yaah-deployment-design.md` maps to a task below.

---

## Spec coverage map

| Spec component | Task(s) |
| --- | --- |
| API Dockerfile | 2 |
| Terraform ECR | 3 |
| Terraform ACM / S3+CloudFront / DNS | 4 |
| Terraform IAM (OIDC) + outputs | 5 |
| K8s Postgres | 6 |
| K8s Temporal | 7 |
| K8s API (Deployment/Service/Ingress/HPA) | 8 |
| K8s API NetworkPolicy (DB ingress) | 6 |
| K8s worker | 9 |
| K8s LiteLLM | 10 |
| GitHub Actions test gate | 11 |
| GitHub Actions backend deploy (build/push/secrets/apply/smoke) | 12 |
| GitHub Actions UI deploy | 13 |
| UI API base-URL app change | 1 |
| Secrets & config (in-cluster from GH secrets) | 12 |
| Runbook / bootstrap / ops | 14 |

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

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

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

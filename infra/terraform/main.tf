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

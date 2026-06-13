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

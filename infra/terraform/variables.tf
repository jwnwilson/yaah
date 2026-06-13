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

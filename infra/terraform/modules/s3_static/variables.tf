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

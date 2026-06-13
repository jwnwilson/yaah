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

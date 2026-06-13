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

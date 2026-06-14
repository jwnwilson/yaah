output "repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  value = aws_ecr_repository.this.arn
}

output "ecr_push_policy_arn" {
  value = aws_iam_policy.ecr_push.arn
}

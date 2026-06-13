output "ui_fqdn" {
  value = aws_route53_record.ui.fqdn
}

output "api_fqdn" {
  value = aws_route53_record.api.fqdn
}

data "aws_route53_zone" "zone" {
  name         = var.zone_name
  private_zone = false
}

resource "aws_route53_record" "ui" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = var.ui_domain
  type    = "CNAME"
  ttl     = 300
  records = [var.ui_cf_domain]
}

resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = var.api_domain
  type    = "A"
  ttl     = 300
  records = [var.cluster_ip]
}

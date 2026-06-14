# Remote state in S3. Create the bucket once, out-of-band, before `terraform init`:
#   aws s3 mb s3://yaah-terraform-state --region us-east-1
#   aws s3api put-bucket-versioning --bucket yaah-terraform-state \
#     --versioning-configuration Status=Enabled
terraform {
  backend "s3" {
    bucket = "yaah-terraform-state"
    key    = "yaah/terraform.tfstate"
    region = "us-east-1"
  }
}

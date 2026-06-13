# GitHub Actions OIDC — lets the workflow assume this role without long-lived keys.
# If the OIDC provider already exists in the account (e.g. created by another
# project), import it instead of recreating: `terraform import module.iam.aws_iam_openid_connect_provider.github <arn>`.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repo}:ref:refs/heads/main",
        "repo:${var.github_repo}:pull_request",
      ]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "yaah-github-actions"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "ecr" {
  count      = length(var.ecr_push_policy_arns)
  role       = aws_iam_role.github_actions.name
  policy_arn = var.ecr_push_policy_arns[count.index]
}

data "aws_iam_policy_document" "ui_deploy" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.ui_bucket_arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.ui_bucket_arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [var.ui_distribution_arn]
  }
}

resource "aws_iam_policy" "ui_deploy" {
  name   = "yaah-ui-deploy"
  policy = data.aws_iam_policy_document.ui_deploy.json
}

resource "aws_iam_role_policy_attachment" "ui_deploy" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.ui_deploy.arn
}

# Read/write the Terraform remote state so CI can run `plan`.
data "aws_iam_policy_document" "tf_state" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.tf_state_bucket}"]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::${var.tf_state_bucket}/yaah/terraform.tfstate"]
  }
}

resource "aws_iam_policy" "tf_state" {
  name   = "yaah-terraform-state"
  policy = data.aws_iam_policy_document.tf_state.json
}

resource "aws_iam_role_policy_attachment" "tf_state" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.tf_state.arn
}

locals {
  default_tags = {
    Deployment = var.prefix
  }
}

terraform {
  required_providers {
    aws  = ">= 2.31.0"
    null = "~> 2.1"
  }
}

module "orca" {
  source = ""
}
variable "prefix" {
  type    = string
  default = "orca"
}

variable "dr_version" {
  default     = "0.1.1"
  description = "Version of DR lambda code to deploy."
}

variable "restore_object_role_arn" {
  type        = string
  description = "Arn for restoration role"
}

variable "subnet_ids" {}

variable "vpc_postgres_ingress_all_egress_id" {
  description = "The security group of postgres egress ingress"
}

variable "database_host" {}

variable "database_port" {
  default = "5432"
}

variable "postgres_user_pw" {}

variable "database_name" {
  default = "orca"
}

variable "database_app_user" {}

variable "database_app_user_pw" {}

variable "ddl_dir" {
  default = "ddl/"
}

variable "drop_database" {
  //TODO Maybe this needs to be a boolean false?
  default = "False"
}

variable "platform" {
  default = "AWS"
}



variable "restore_expire_days" {
  default = 5
}

variable "restore_request_retries" {
  default = 3
}

variable "restore_retry_sleep_secs" {
  default = 0
}

variable "restore_retrieval_type" {
  default = "Standard"
}


variable "copy_retries" {
  default = 3
}

variable "copy_retry_sleep_secs" {
  default = 0
}

variable "glacier_bucket" {}



variable "vpc_id" {
  type = string
}

variable "lambda_timeout" {
  type = number
  default = 300
}
variable "restore_complete_filter_prefix" {
  default = "orca"
}

variable "tags" {}
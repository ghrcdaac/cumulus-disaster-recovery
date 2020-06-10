
locals {
  default_tags = {
    Deployment = var.prefix
  }
  request_source_hash    = filemd5("${path.module}/tasks/request_files/request-${var.dr_version}.zip")
  extract_filepaths_hash = filemd5("${path.module}/tasks/extract_filepaths_for_granule/extract-${var.dr_version}.zip")
}

module "lambda_security_group" {
  source = "../security_groups"
  tags = var.tags
  vpc_id = var.vpc_id
  
}


resource "aws_lambda_function" "db_deploy" {
  filename      = "${path.module}/tasks/db_deploy/dbdeploy-${var.dr_version}.zip"
  function_name = "${var.prefix}_db_deploy"
  role          = var.restore_object_role_arn
  handler       = "db_deploy.handler"
  runtime       = "python3.7"
  timeout       = var.lambda_timeout
  description   = "Deploys the Disaster Recovery database"

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [module.lambda_security_group.vpc_postgres_ingress_all_egress_id]
  }

  environment {
    variables = {
      DATABASE_PORT = var.database_port
      DATABASE_NAME = var.database_name
      DATABASE_USER = var.database_app_user
      DDL_DIR       = var.ddl_dir
      DROP_DATABASE = var.drop_database
      PLATFORM      = var.platform
    }
  }
}


resource "aws_lambda_function" "extract_filepaths_for_granule_lambda" {
  filename         = "${path.module}/tasks/extract_filepaths_for_granule/extract-${var.dr_version}.zip"
  source_code_hash = local.extract_filepaths_hash
  function_name    = "${var.prefix}_extract_filepaths_for_granule"
  role             = var.restore_object_role_arn
  handler          = "extract_filepaths_for_granule.handler"
  runtime          = "python3.7"
  timeout          = var.lambda_timeout
  description      = "Extracts bucket info and granules file keys from the CMA"

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [module.lambda_security_group.vpc_postgres_ingress_all_egress_id]
  }
}


resource "aws_lambda_function" "request_files_lambda" {
  filename         = "${path.module}/tasks/request_files/request-${var.dr_version}.zip"
  function_name    = "${var.prefix}_request_files"
  source_code_hash = local.request_source_hash
  role             = var.restore_object_role_arn
  handler          = "request_files.handler"
  runtime          = "python3.7"
  timeout          = var.lambda_timeout
  description      = "Submits a restore request for a file"

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [module.lambda_security_group.vpc_postgres_ingress_all_egress_id]
  }

  environment {
    variables = {
      DATABASE_PORT            = var.database_port
      DATABASE_NAME            = var.database_name
      DATABASE_USER            = var.database_app_user
      RESTORE_EXPIRE_DAYS      = var.restore_expire_days
      RESTORE_REQUEST_RETRIES  = var.restore_request_retries
      RESTORE_RETRY_SLEEP_SECS = var.restore_retry_sleep_secs
      RESTORE_RETRIEVAL_TYPE   = var.restore_retrieval_type
    }
  }
}


resource "aws_lambda_function" "copy_files_to_archive" {
  filename      = "${path.module}/tasks/copy_files_to_archive/copy-${var.dr_version}.zip"
  function_name = "${var.prefix}_copy_files_to_archive"
  role          = var.restore_object_role_arn
  handler       = "copy_files_to_archive.handler"
  runtime       = "python3.7"
  timeout       = var.lambda_timeout
  description   = "Copies a restored file to the archive"

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [module.lambda_security_group.vpc_postgres_ingress_all_egress_id]
  }

  environment {
    variables = {
      COPY_RETRIES          = var.copy_retries
      COPY_RETRY_SLEEP_SECS = var.copy_retry_sleep_secs
      DATABASE_PORT         = var.database_port
      DATABASE_NAME         = var.database_name
      DATABASE_USER         = var.database_app_user
    }
  }
}

resource "aws_lambda_function" "request_status" {
  filename      = "${path.module}/tasks/request_status/status-${var.dr_version}.zip"
  function_name = "${var.prefix}_request_status"
  role          = var.restore_object_role_arn
  handler       = "request_status.handler"
  runtime       = "python3.7"
  timeout       = var.lambda_timeout
  description   = "Queries the Disaster Recovery database for status"

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [module.lambda_security_group.vpc_postgres_ingress_all_egress_id]
  }

  environment {
    variables = {
      DATABASE_PORT = var.database_port
      DATABASE_NAME = var.database_name
      DATABASE_USER = var.database_app_user
    }
  }
}

resource "aws_lambda_permission" "allow_s3_trigger" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.copy_files_to_archive.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::${var.glacier_bucket}"
}


resource "aws_s3_bucket_notification" "copy_lambda_trigger" {
  depends_on = [aws_lambda_permission.allow_s3_trigger]
  bucket = var.glacier_bucket

  lambda_function {
    lambda_function_arn = aws_lambda_function.copy_files_to_archive.arn
    events              = ["s3:ObjectRestore:Completed"]
    filter_prefix       = var.restore_complete_filter_prefix
  }
}

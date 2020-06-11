## Adding Copy To Glacier Lambda
Include {prefix}-glacier in buckets which should be created in cumulus deployment. GHRC adds the following to cumulus-tf/terraform.tfvars.example within our buckets dictionary
```
glacier = {
    name = "${TF_VAR_glacier_bucket}"
    type = "private"
  }
```
Add the relative path to the copy to lambda source code to cumulus-tf/lambdas.tf with your other locals
```
orca_copy_to_glacier_lambda_path  = "../operational-recovery-cloud-archive/copy_to_glacier_lambda/dist/copy_to_glacier_lambda.zip"
```
Add the source code hash to cumulus-tf/lambdas.tf with your other locals
```
orca_copy_to_glacier_lambda_hash  = filemd5(local.orca_copy_to_glacier_lambda_path)
```
Add the copy to glacier terraform module to cumulus-tf/lambdas.tf
```
resource "aws_lambda_function" "copy_to_glacier" {
  function_name    = "${var.prefix}-copy_to_glacier"
  filename         = "${local.orca_copy_to_glacier_lambda_path}"
  source_code_hash = "${local.orca_copy_to_glacier_lambda_hash}"
  handler          = "handler.handler"
  role             = module.cumulus.lambda_processing_role_arn
  runtime          = "python3.7"
  memory_size      = 2240
  timeout          = 600 # 10 minutes

  tags = local.default_tags
  environment {
    variables = {
      system_bucket               = var.system_bucket
      stackName                   = var.prefix
      CUMULUS_MESSAGE_ADAPTER_DIR = "/opt/"
    }
  }

  vpc_config {
    subnet_ids         = list(module.ngap.ngap_subnets_ids[0])
    security_group_ids = [aws_security_group.no_ingress_all_egress.id]
  }
}
```
Add the copy to glacier step into your cumulus workflow. GHRC adds this step into our ingest_granule_workflow.tf file after our PostToCMR step.
```
      "Next":"CopyToGlacier"
      },
      "CopyToGlacier":{
         "Parameters":{
            "cma":{
               "event.$":"$",
               "task_config":{
                  "bucket":"{$.meta.buckets.internal.name}",
                  "buckets":"{$.meta.buckets}",
                  "distribution_endpoint":"{$.meta.distribution_endpoint}",
                  "files_config":"{$.meta.collection.files}",
                  "fileStagingDir":"{$.meta.collection.url_path}",
                  "granuleIdExtraction":"{$.meta.collection.granuleIdExtraction}",
                  "collection":"{$.meta.collection}",
                  "cumulus_message":{
                     "input":"{[$.payload.granules[*].files[*].filename]}",
                     "outputs":[
                        {
                           "source":"{$}",
                           "destination":"{$.payload}"
                        }
                     ]
                  }
               }
            }
         },
         "Type":"Task",
         "Resource":"${aws_lambda_function.copy_to_glacier.arn}",
         "Catch":[
            {
               "ErrorEquals":[
                  "States.ALL"
               ],
               "ResultPath":"$.exception",
               "Next":"WorkflowFailed"
            }
         ],
         "Retry":[
            {
               "ErrorEquals":[
                  "States.ALL"
               ],
               "IntervalSeconds":2,
               "MaxAttempts":3
            }
         ],
         "Next":"WorkflowSucceeded"
      },
```

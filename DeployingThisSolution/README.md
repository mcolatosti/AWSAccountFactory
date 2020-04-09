# account-bootstrapper AWS Deployment Considerations and Requirements
This information directory contains policies and roles used by bootstrapper from the servicing account (master).
This information is to record our current or best practices when deploying the solution, but content in this directory IS NOT ACTUALLY REFERENCED BY ANY PROJECT CODE.

## The following IAM roles and policies have been deployed to the master account to support this solution

`IAM Role: accountfactory`

This role is a lauch constraint used by the Account Bootstrapper "Account Factory" service catalog product.  It has been granted superuser rights and the ability to assume other roles.
This is a highly privileged role and not to be used by any other services or users other than the service catalog.

- The role is permitted the built-in `AdministratorAccess` role
- The role is permitted the following additional inline policy role: `AllowRoleAssuming`
    {
        "Version": "2012-10-17",
        "Statement": {
            "Effect": "Allow",
            "Action": "sts:AssumeRole",
            "Resource": "*"
        }
    }
- The role has the following trusted entity assigned: `The identity provider(s) servicecatalog.amazonaws.com`

`IAM Role: SAML_MASTER_AccountFactory`

This role is used to grant access to the Account Factory from ADFS federated login based on an equivalent AD domain group.
Membership in this AD group permits the ability to launch the Account Factory, edit your own launched products, view but NOT modify other launched products and to access all Account Product cloudwatch detailed events.
This is a SAML trusted entity type role with the following trust relationship: `arn:aws:iam::yourmasteracct#:saml-provider/your_idp_provider_FQDN`

- The role is allowed the following inline policy role: `AllowLimitedAccessToCloudwatchLogs`
```
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:Describe*",
                    "logs:Get*"
                ],
                "Resource": [
                    "arn:aws:logs:*:yourmasteracct#:log-group:aws/lambda/SC-yourmasteracct#-pp-*",
                    "arn:aws:logs:*:*:log-group:*:*:*"
                ]
            }
        ]
    }
```
- The role is granted the following inline policy role: `AWSServiceCatalogEndUserAccountLevel`
```
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "cloudformation:CreateStack",
                    "cloudformation:DeleteStack",
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:DescribeStacks",
                    "cloudformation:SetStackPolicy",
                    "cloudformation:ValidateTemplate",
                    "cloudformation:UpdateStack",
                    "cloudformation:CreateChangeSet",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:ExecuteChangeSet",
                    "cloudformation:ListChangeSets",
                    "cloudformation:DeleteChangeSet",
                    "cloudformation:TagResource",
                    "cloudformation:CreateStackSet",
                    "cloudformation:CreateStackInstances",
                    "cloudformation:UpdateStackSet",
                    "cloudformation:UpdateStackInstances",
                    "cloudformation:DeleteStackSet",
                    "cloudformation:DeleteStackInstances",
                    "cloudformation:DescribeStackSet",
                    "cloudformation:DescribeStackInstance",
                    "cloudformation:DescribeStackSetOperation",
                    "cloudformation:ListStackInstances",
                    "cloudformation:ListStackResources",
                    "cloudformation:ListStackSetOperations",
                    "cloudformation:ListStackSetOperationResults"
                ],
                "Resource": [
                    "arn:aws:cloudformation:*:*:stack/SC-*",
                    "arn:aws:cloudformation:*:*:stack/StackSet-SC-*",
                    "arn:aws:cloudformation:*:*:changeSet/SC-*",
                    "arn:aws:cloudformation:*:*:stackset/SC-*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "cloudformation:GetTemplateSummary",
                    "servicecatalog:DescribeProduct",
                    "servicecatalog:DescribeProductView",
                    "servicecatalog:DescribeProvisioningParameters",
                    "servicecatalog:ListLaunchPaths",
                    "servicecatalog:ProvisionProduct",
                    "servicecatalog:SearchProducts",
                    "ssm:DescribeDocument",
                    "ssm:GetAutomationExecution",
                    "config:DescribeConfigurationRecorders",
                    "config:DescribeConfigurationRecorderStatus"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "servicecatalog:DescribeProvisionedProduct",
                    "servicecatalog:DescribeRecord",
                    "servicecatalog:ListRecordHistory",
                    "servicecatalog:ListStackInstancesForProvisionedProduct",
                    "servicecatalog:ScanProvisionedProducts",
                    "servicecatalog:TerminateProvisionedProduct",
                    "servicecatalog:UpdateProvisionedProduct",
                    "servicecatalog:SearchProvisionedProducts",
                    "servicecatalog:CreateProvisionedProductPlan",
                    "servicecatalog:DescribeProvisionedProductPlan",
                    "servicecatalog:ExecuteProvisionedProductPlan",
                    "servicecatalog:DeleteProvisionedProductPlan",
                    "servicecatalog:ListProvisionedProductPlans",
                    "servicecatalog:ListServiceActionsForProvisioningArtifact",
                    "servicecatalog:ExecuteProvisionedProductServiceAction",
                    "servicecatalog:DescribeServiceActionExecutionParameters"
                ],
                "Resource": "*",
                "Condition": {
                    "StringEquals": {
                        "servicecatalog:userLevel": "self"
                    }
                }
            },
            {
                "Sid": "ViewOnlyOtherAccountDeployments",
                "Effect": "Allow",
                "Action": [
                    "servicecatalog:Describe*",
                    "servicecatalog:List*",
                    "servicecatalog:Scan*",
                    "servicecatalog:Search*"
                ],
                "Resource": "*",
                "Condition": {
                    "StringEquals": {
                        "servicecatalog:accountLevel": "self"
                    }
                }
            }
        ]
    }
```
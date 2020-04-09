# account-bootstrapper
The AWS account-bootstrapper project is a special service required to perform the initial setup of any new AWS accounts to be provisioned within an AWS Organization.  Additionally, it is the responsibility of this project to provision the backend infrastructure needed to support Terraform to complete the provisioning of all security, networking and application deployment requirements as well as ongoing maintenance for the new AWS account.
The account creation process is a special-case Infrastructure as Code (IaC) scenario that needs to be performed only once per account and requires the "bootstrapping" of some minimal infrastructure to support Terraformn automation.
This task is performed outside of Terraform in the master account where these goals can be accomplished in a simpler, stateless manner and can leverage the existing AWS Service Catalog as the user interface.
- Special Note: The account bootstrapper project is NOT a Terraform-based IaC project, and therefore has different deployment requirements and procedures!

The Account Bootstrapper project is intended to only perform the account provisioning and minimal security tasks needed to allow Terraform projects to run and continue management and setup.

## Features Currently present:
- Creation of an AWS account within an existing AWS Organization.
- Provisioning of special terraform_writer and terraform_reader roles.
- Deletion of "default" VPC in all regions.  This behavior can be overridden in account setup via a parameter if required.
- Allows for the use of an accountbaseline yaml file to specified and to launch a cloudformation stack in the new account to provision any initial state structures that are desired outside of python lambda code.   NOT RECOMMENDED.
- Code to permit the appropriate iac account EC2 build and deploy roles to assume the new account terraform_reader and writer roles for use with CI/CD terraform build and deploy agent(s).
- Create the special environment Terraform AWS provisioner file used by the TFS Azure Devops pipeline and terraform to lock environment down from developer manipulation.
- Creation of master account Terraform automation objects (if a transit hub account) like: S3 IaC Hub bucket, EC2 build and deploy roles.

## Features to be coded:
- Review definition of terraform_reader and writer roles and code to permit the required trust settings from the master ec2 build and deploy instance roles associated with the account. Currently they are both configured to ALLOW ALL!
- Destroy account cloudformation stack on a successful deploy, perhaps?  Jury still out on whether to persist the account "service" entity after creation, keeping it around might be a good self-healing option.
- AWS Organization OU creation and joining.
- AWS Organization OU policy attachment.
- Configure and the use of special KMS encrpytion keys for application catalog and terraform configuration/state data to prevent maniuplation by AWS administrators.
- Spin up at least one build and deploy TFS agent server if a HUB account, into the special IaC account.
- Ability to drive changes to TFS Application/Infrastructure code pipelines when creating and account.  For instance the accountbootstrapper servicecatalog or a new dedicated application deployment one, could allow the user to select what "apps and infrastructure to deploy to thew new account" and that would result in MS Devops pipelines being altered to accomodate, variables be defined etc.  (Very advanced feature, but would be very nice!) (Post version 1 feature) 

## Special Project Information & Requirements
- A special master organization account AWS S3 iac bucket must exist for the storage of this project's configuration files.
- The AccountCreationLambda.py python script, the "templates" directory, and the bootstrapper.ini configuration file must be packaged as a zip file with a file name of "AccountCreationLambda.zip" and stored in the special master bucket. As the name suggests it is a lambda function launched in the master account and provides all the account provisioning code and logic.  The templates directory is to store file and policy templates that are large and not ideal to store in lambda code body.
- The accountbuilder-iac.json file defines the "Account Creation" AWS service catalog product to be published in the master account, ultimately this provides the user interface to spin up accounts.
- The accountbaseline.yaml file is stored in the special IaC bucket and permits the customization of the solution to perform future account initialization tasks via this special cloudformation stack definition that runs in the newly created account.  There is no imediate need for this entity but has been implemented for future proofing.

### SOME MINOR FIND AND REPLACE operations are required in this project to make deployment unique and to support your AWS Organizational environment.
 - Text substitution required in the AccountCreationLambda.py file: 
    1. Replace yourcompanynameORcustomprefix     with a custom unique prefix to generate accountbootstrapper project S3 buckets.
 - Text substitution required in the account-builder-iac.json file: 
    1. Replace yourspecialIACAWSaccount#         with the account number of your account used to house special IaC objects like S3 terraform buckets.
    2. Replace "AllowedPattern": ".+\\@contoso\\.com"  in the email parameter constraint as desired to limit account registration to emails in your corporate domain and control.

- Ensure you refer to the [Deploying This Solution](DeployingThisSolution/README.md) for additional information concerning deploying this AWS Service Catalog solution in an AWS account.


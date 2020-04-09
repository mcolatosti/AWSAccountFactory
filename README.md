# AWSAccount Factory (aka. account-bootstrapper)
The AWS Account Factory Project (aka the account-bootstrapper) is a python-based AWS ServiceCatalog application definition used to provide the ability for users to spin up AWS Accounts in an existing AWS Organization.  The solution mimics some of the functionality and strategies used by Amazon tools like Control Tower or Landing Zones, but is designed to be highly tailored to a client environment and more importantly. provide just the bare minimum of services needed to support all other networking, security and application service provisioning within the new account via Terraform.  This enables an organzation to completely deploy and continually change all components deployed into the account via Terraform instead of inheriting a large amount of infrasatructure and security configuration that would then need to be managed outside of a Terraform CI/CD pipeline.  A number of Terraform specific infrastructure is automatically deployed (in a very secure manner) as part of the account provisioning process.  This includes:
- Secure Terraform state S3 buckets or bucket paths for each account provisioned.
- Dedicated terraform read and writer roles secured per account to a cross-account trust.
- Dedicated EC2 terraform IAM roles to permit CI/CD agents to assume, in order to read or deploy into the specific accounts via terraform tools. Secured to cross account role trusts.  
   - It is recommended to have an AWS ORganization policy that prevents account from modifying these provisione terramform roles from being edited even by root user of the accounts.  This policy is trivial to implement but not part of deployment at this time.
- The provisioning/creation of a special terraform provider file used by terraform to deploy into created accounts including all account details and roles to assume.  The recommendation is that these provider files are injected into CI/CD pipeline build/deploys so that developers cannot attempt to change which environment deploys occur to, or what state buckets to use, etc.  All operations which if permitted to occur can be disastrous to the operational or security of an environment. 

The AWS AccountFactory (account-bootstrapper) project is a special service required to perform the initial setup of any new AWS accounts to be provisioned within an AWS Organization.  Additionally, it is the responsibility of this project to provision the backend infrastructure needed to support Terraform to complete the provisioning of all security, networking and application deployment requirements as well as ongoing maintenance for the new AWS account.
The account creation process is a special-case Infrastructure as Code (IaC) scenario that needs to be performed only once per account and requires the "bootstrapping" of some minimal infrastructure to support Terraformn automation.
This task is performed outside of Terraform in the master account where these goals can be accomplished in a simpler, stateless manner and can leverage the existing AWS Service Catalog as the user interface.
- Special Note: The account bootstrapper project is NOT a Terraform-based IaC project, and therefore has different deployment requirements and procedures!

The Account Bootstrapper project is intended to only perform the account provisioning and minimal security tasks needed to allow Terraform projects to run and continue management and setup of the account.

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
- Ability to drive changes to MS Devops Application/Infrastructure code pipelines when creating and account.  For instance the accountbootstrapper servicecatalog or a new dedicated application deployment one, could allow the user to select what "apps and infrastructure to deploy to thew new account" and that would result in MS Devops pipelines being altered to accomodate, variables be defined etc.  (Very advanced feature, but would be very nice!) (Post version 1 feature) 

## Special Project Information & Requirements
- A special master organization account AWS S3 iac bucket must exist for the storage of this project's configuration files.
- The AccountCreationLambda.py python script, the "templates" directory, and the bootstrapper.ini configuration file must be packaged as a zip file with a file name of "AccountCreationLambda.zip" and stored in the special master bucket. As the name suggests it is a lambda function launched in the master account and provides all the account provisioning code and logic.  The templates directory is to store file and policy templates that are large and not ideal to store in lambda code body.
- The accountbuilder-iac.json file defines the "Account Creation" AWS service catalog product to be published in the master account, ultimately this provides the user interface to spin up accounts.
- The accountbaseline.yaml file is stored in the special IaC bucket and permits the customization of the solution to perform future account initialization tasks via this special cloudformation stack definition that runs in the newly created account.  There is no imediate need for this entity but has been implemented for future proofing.

### SOME MINOR FIND AND REPLACE operations are required in this project to make deployment unique and to support your AWS Organizational environment.
 - Text substitution required in the AccountCreationLambda.py file: 
    1. Replace yourcompanynameORcustomprefix     with a custom unique prefix to generate accountbootstrapper project S3 buckets.
 - Text substitution required in the accountbuilder-iac.json file: 
    1. Replace yourspecialIACAWSaccount#         with the account number of your account used to house special IaC objects like S3 terraform buckets.
    2. Replace "AllowedPattern": ".+\\@contoso\\.com"  in the email parameter constraint as desired to limit account registration to emails in your corporate domain and control.

- Ensure you refer to the [Deploying This Solution](DeployingThisSolution/README.md) for additional information concerning deploying this AWS Service Catalog solution in an AWS account.


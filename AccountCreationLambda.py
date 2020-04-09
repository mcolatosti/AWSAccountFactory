 ######################################################################################
 #
 # Custom AWS Org Account creation bootstrapping solution for Terraform use.
 #
 # This python package is expected to be launched via an AWS Service Catalog
 # published account creation application in the Organization Master account.
 # 
 # Some of the functions have been borrowed from AWS published, licensed free to 
 # use and modify source code that has no reuse or redistributing limitations.
 #
 # Text substitution required in this file: 
 #   Replace yourcompanynameORcustomprefix     with a custom unique prefix to 
 #               generate accountbootstrapper project S3 buckets.
 # Text substitution required in account-builder-iac.json file: 
 #   Replace yourspecialIACAWSaccount#         with the account number of your account
 #               used to house special IaC objects like S3 terraform buckets.
 #
 ######################################################################################

#!/usr/bin/env python

from __future__ import print_function

import argparse
import ast
import boto3
import botocore
import configparser
import json
import logging
import os
import time
import sys
import urllib

from botocore.vendored import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def assume_role(account_id, account_role):
    # Function to return the temporary AWS credentials object for the specified role to assume
    # Function is typically used for gaining access across accounts
    # Parameters:
    #   account_id:  The AWS account ID housing the role to assume.
    #   account_role: The account role NAME to assume.  Note: Provide the name and NOT the ARN.
    
    sts_client = boto3.client('sts')
    role_arn = 'arn:aws:iam::' + account_id + ':role/' + account_role
    assuming_role = True
    while assuming_role is True:
        try:
            assuming_role = False
            assumedRoleObject = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="NewAccountRole"
            )
        except botocore.exceptions.ClientError as e:
            assuming_role = True
            print(e)
            print("Retrying...")
            time.sleep(60)

    # From the response that contains the assumed role, return the temporary
    # credentials that can be used to make subsequent API calls
    return assumedRoleObject['Credentials']

def attach_policy(rolename,policyarn,credentials):
    # Function to attach a policy to a given role
    # Parameters:
    #   credentials: An AWS credentials object with the privileges attach the given policy to the role.
    #   account_idpolicyarn:  The policy to attach to the role, specified using the policies AWS ARN value.
    #   rolename: The role NAME to attach the policy to.  Note: Provide the role's name and NOT the ARN value.

    iam_client = boto3.client('iam',aws_access_key_id=credentials['AccessKeyId'],
                                  aws_secret_access_key=credentials['SecretAccessKey'],
                                  aws_session_token=credentials['SessionToken'])
    attempt_counter = 1   #Try 3 times, every 30 secs for a maximum of 90 sec. 
    response="Failure"
    while attempt_counter <= 3:
        try:
            response = iam_client.attach_role_policy(RoleName=rolename,PolicyArn=policyarn)
            print("Success policy {} to role {} on attempt#{}".format(policyarn,rolename,attempt_counter))
            print(response)
            
        except botocore.exceptions.ClientError as e:    
            print("Error Occured in attempt #{}, attaching policy to role : {}".format(attempt_counter,e))
            time.sleep(30)
        else:
            attempt_counter = 999
        attempt_counter += 1
    return response

def bucket_policy(requesttype,account_id,accountrole,bucketname,sid,bucketpolicy):
    # No longer used but provides a means to apply or add to an S3 bucket policy.
    # Design no longer requires this function, but code could be useful in the future.
    credentials = assume_role(account_id, accountrole)
    s3_client = boto3.client('s3',aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials['SessionToken'])
    if (requesttype == "init"):
        # Function call is used for setting the intial bucket policy on bucket creation.
        # Can be used to wipe all policies and reset to a known state.
        # Note SID parameter is unused, and bucket policy must include all AWS S3 policy elements
        print("--- Applying Initial IaC Bucket Policy ---")
        attempt_counter = 1   #Try 20 times, every 30 secs for a maximum of 10 min. 
        while attempt_counter <= 20:
            try:
                time.sleep(30)
                s3response = s3_client.put_bucket_policy(
                    Bucket=bucketname,
                    Policy=bucketpolicy
                )
            except botocore.exceptions.ClientError as e:
                print("Error applying policy to Terraform IaC bucket on attempt#{}. Error : {}".format(attempt_counter,e))
            else:
                print("Successfully applied policy to Terraform IaC bucket on attempt#{}".format(attempt_counter))
                return ("success")
                attempt_counter = 999
            attempt_counter += 1            
        return ("error: {}".format(e))
    elif (requesttype == "add"):
        # Function call is used for adding additional bucket policy statement blocks to an existing policy
        # for this call bucketpolicy variable is equal to JUST the json statement block element to add in an existing statement list
        # SID Parameter is not used, this should be provided as part of the bucketpolicy json data!  Without it, delete call will not be possible!
        print("--- Adding to IaC Bucket Policy ---")
        s3policy = s3_client.get_bucket_policy(Bucket=bucketname)
        print(" existing policy")
        print(s3policy['Policy'])
        s3policy = ast.literal_eval(s3policy['Policy'])
        s3policy['Statement'].append(json.loads(bucketpolicy))
        s3policy = json.dumps(s3policy)
        print("New Policy: {}".format(s3policy))
        print("--- Applying additional IaC Bucket Policy ---")
        attempt_counter = 1   #Try 20 times, every 30 secs for a maximum of 10 min. 
        while attempt_counter <= 20:
            try:
                s3response = s3_client.put_bucket_policy(
                    Bucket=bucketname,
                    Policy=s3policy
                )
            except botocore.exceptions.ClientError as e:
                print("Error applying policy to Terraform IaC bucket on attempt#{}. Error : {}".format(attempt_counter,e))
                time.sleep(30)
            else:
                print("Successfully added policy to Terraform IaC bucket on attempt#{}".format(attempt_counter))
                return ("success")
                attempt_counter = 999
            attempt_counter += 1            
        return ("error: {}".format(e))

def get_client(service):
    # Function call to standardize boto3 client calls in other areas of code.
    client = boto3.client(service)
    return client

def create_account(event,accountname,accountemail,accountrole,access_to_billing,scp,root_id):
    # Function to create a new account in an existing AWS Orgranization.
    # Parameters:
    #   event:        Account creation event type, typically create or destroy.  Only create has been currently coded for.
    #   accountname:  AWS Account name to give the new account.
    #   accountemail: Email account to register the AWS account, this must be a unique account and cannot be reused.
    #   accountrole:  The name of the role for AWS to provision in the new account that can be used by the master account to gain administrative access.
    #   access_to_billing: A boolean that sets whether it may be possible for a user to view billing information if access granted elsewhere.
    #   scp:          Org Service Control Policy to attach - this functionality has not been coded for yet.
    #   root_id:      Org Account organization tree level - this functionality has not been completely coded for yet.
       
    account_id = 'None'
    client = get_client('organizations')
    
    try:
        print("Trying to create the account with {}".format(accountemail))
        create_account_response = client.create_account(Email=accountemail, AccountName=accountname,
                                                        RoleName=accountrole,
                                                        IamUserAccessToBilling=access_to_billing)
        time.sleep(40)
        account_status = client.describe_create_account_status(CreateAccountRequestId=create_account_response['CreateAccountStatus']['Id'])
        print("Account Creation status: {}".format(account_status['CreateAccountStatus']['State']))
        if(account_status['CreateAccountStatus']['State'] == 'FAILED'):
            print("Account Creation Failed. Reason : {}".format(account_status['CreateAccountStatus']['FailureReason']))
            delete_respond_cloudformation(event, "FAILED", account_status['CreateAccountStatus']['FailureReason'])

    except botocore.exceptions.ClientError as e:
        print("In the except module. Error : {}".format(e))
        delete_respond_cloudformation(event, "FAILED", "Account Creation Failed. Deleting Lambda Function." +e+ ".")
        
    time.sleep(10)
    create_account_status_response = client.describe_create_account_status(CreateAccountRequestId=create_account_response.get('CreateAccountStatus').get('Id'))
    account_id = create_account_status_response.get('CreateAccountStatus').get('AccountId')
    while(account_id is None ):
        create_account_status_response = client.describe_create_account_status(CreateAccountRequestId=create_account_response.get('CreateAccountStatus').get('Id'))
        account_id = create_account_status_response.get('CreateAccountStatus').get('AccountId')
    #move_response = client.move_account(AccountId=account_id,SourceParentId=root_id,DestinationParentId=organization_unit_id)
    return(create_account_response,account_id)

def create_newrole(newrole,top_level_account,credentials,newrolepolicy,newtrustpolicy):
    # Function to create a new role with speficied policy in the account associted with the passed credentials
    #  Can be used to create roles in any account.
    # Parameters:
    #    newrole:           The name of the IAM role to create.
    #    top_level_account: No longer really used (to be removed from function code and calls), but needs to be specified, historically was passed root account.
    #    credentials:       AWS credentials object for the account to create the role in.
    #    newrolepolicy:     A string representation of the complete AWS policy to apply to the new IAM role.
    #    newtrustpolicy:    A string representation of the AWS trust policy to assign to the new IAM role.

    iam_client = boto3.client('iam',aws_access_key_id=credentials['AccessKeyId'],
                                  aws_secret_access_key=credentials['SecretAccessKey'],
                                  aws_session_token=credentials['SessionToken'])
    print(newrolepolicy)
    print(newtrustpolicy)
    
    attempt_counter = 1   #Try 20 times, every 30 secs for a maximum of 10 min. 
    while attempt_counter <= 20:
        try:
            create_role_response = iam_client.create_role(RoleName=newrole,AssumeRolePolicyDocument=newtrustpolicy,Description=newrole,MaxSessionDuration=3600)
            print("Success creating new role on attempt#{}".format(attempt_counter))
            print(create_role_response['Role']['Arn'])
            
        except botocore.exceptions.ClientError as e:    
            print("Error Occured in attempt #{}, creating a role : {}".format(attempt_counter,e))
            time.sleep(30)
        else:
            attempt_counter = 999
        attempt_counter += 1

    attempt_counter = 1   #Try 20 times, every 30 secs for a maximum of 10 min. 
    while attempt_counter <= 20:
        try:
            update_role_response = iam_client.put_role_policy(RoleName=newrole,PolicyName=newrole,PolicyDocument=newrolepolicy)
        except botocore.exceptions.ClientError as e:
            print("Error on attempt# {}, attaching policy to the role : {}".format(attempt_counter,e))
        else:
            print("Success on attempt# {}, attaching policy to the role".format(attempt_counter))
            attempt_counter = 999
        attempt_counter += 1

    print("{},{},{}".format(newrole,top_level_account,credentials))
    return create_role_response['Role']['Arn']

def delete_default_vpc(credentials,currentregion):
    # Function to delete the existing default VPC in a given region within an account.
    #   This needs to be called iteratively for each region if its desired to destroy all defualt VPCs and associated security objects.
    #   Function taken from AWS code sample verbatim, function code is free to distribute with any distribution limitations.
    # Parameters:
    #   credentials:    AWS credential object for the account to destroy default VPCs
    #   currentregion:  The official AWS region name containing the defualt VPC to destroy.
 
    ec2_client = boto3.client('ec2',
                            aws_access_key_id=credentials['AccessKeyId'],
                            aws_secret_access_key=credentials['SecretAccessKey'],
                            aws_session_token=credentials['SessionToken'],
                            region_name=currentregion)

    vpc_response = ec2_client.describe_vpcs()
    for i in range(0,len(vpc_response['Vpcs'])):
        if((vpc_response['Vpcs'][i]['InstanceTenancy']) == 'default'):
            default_vpcid = vpc_response['Vpcs'][0]['VpcId']

    subnet_response = ec2_client.describe_subnets()
    subnet_delete_response = []
    default_subnets = []
    for i in range(0,len(subnet_response['Subnets'])):
        if(subnet_response['Subnets'][i]['VpcId'] == default_vpcid):
            default_subnets.append(subnet_response['Subnets'][i]['SubnetId'])
    for i in range(0,len(default_subnets)):
        subnet_delete_response.append(ec2_client.delete_subnet(SubnetId=default_subnets[i],DryRun=False))
    
    igw_response = ec2_client.describe_internet_gateways()
    for i in range(0,len(igw_response['InternetGateways'])):
        for j in range(0,len(igw_response['InternetGateways'][i]['Attachments'])):
            if(igw_response['InternetGateways'][i]['Attachments'][j]['VpcId'] == default_vpcid):
                default_igw = igw_response['InternetGateways'][i]['InternetGatewayId']

    try:
        detach_default_igw_response = ec2_client.detach_internet_gateway(InternetGatewayId=default_igw,VpcId=default_vpcid,DryRun=False)
        delete_internet_gateway_response = ec2_client.delete_internet_gateway(InternetGatewayId=default_igw)
        time.sleep(10)
        delete_vpc_response = ec2_client.delete_vpc(VpcId=default_vpcid,DryRun=False)
        print("Deleted Default VPC in {}".format(currentregion))

    except botocore.exceptions.ClientError as e:
        print(e)

    return delete_vpc_response    

def get_ou_name_id(root_id,organization_unit_name):
    # Function checks for the existence of an AWS organization OU group name, creating it if non-existent.
    # Parameters:
    #   root_id:                The AWS root organization Identifier of the master account.
    #   organization_unit_name: The name of the org unit to create or retrieve if already in existence.

    ou_client = get_client('organizations')
    list_of_OU_ids = []
    list_of_OU_names = []
    ou_name_to_id = {}

    list_of_OUs_response = ou_client.list_organizational_units_for_parent(ParentId=root_id)
    
    for i in list_of_OUs_response['OrganizationalUnits']:
        list_of_OU_ids.append(i['Id'])
        list_of_OU_names.append(i['Name'])
        
    if(organization_unit_name not in list_of_OU_names):
        print("The provided Organization Unit Name doesnt exist. Creating an OU named: {}".format(organization_unit_name))
        try:
            ou_creation_response = ou_client.create_organizational_unit(ParentId=root_id,Name=organization_unit_name)
            for k,v in ou_creation_response.items():
                for k1,v1 in v.items():
                    if(k1 == 'Name'):
                        organization_unit_name = v1
                    if(k1 == 'Id'):
                        organization_unit_id = v1
        except botocore.exceptions.ClientError as e:
            print("Error in creating the OU: {}".format(e))
            respond_cloudformation(event, "FAILED", { "Message": "Could not list out AWS Organization OUs. Account creation Aborted."})

    else:
        for i in range(len(list_of_OU_names)):
            ou_name_to_id[list_of_OU_names[i]] = list_of_OU_ids[i]
        organization_unit_id = ou_name_to_id[organization_unit_name]
    
    return(organization_unit_name,organization_unit_id)

def get_template(sourcebucket,baselinetemplate):
    # Function to retrieve the policy of an existing S3 bucket.
    #   Function is no longer used by project but code left in for potential future usage.

    s3 = boto3.resource('s3')
    try:
        obj = s3.Object(sourcebucket,baselinetemplate)
        return obj.get()['Body'].read().decode('utf-8') 
    except botocore.exceptions.ClientError as e:
        print("Error accessing the source bucket. Error : {}".format(e))
        return e

def selfinvoke(event,status):
    # Function to handle Service Catalog based lambda initialization.
    lambda_client = boto3.client('lambda')
    function_name = os.environ['AWS_LAMBDA_FUNCTION_NAME']
    event['RequestType'] = status
    print('invoking itself ' + function_name)
    response = lambda_client.invoke(FunctionName=function_name, InvocationType='Event',Payload=json.dumps(event))

def respond_cloudformation(event, status, data=None):
    # Function to handle Service Catalog based cloudformation events.
    responseBody = {
        'Status': status,
        'Reason': 'See the details in CloudWatch Log Stream',
        'PhysicalResourceId': event['ServiceToken'],
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': data
    }

    print('Response = ' + json.dumps(responseBody))
    print(event)
    requests.put(event['ResponseURL'], data=json.dumps(responseBody))

def delete_respond_cloudformation(event, status, message):
    # Function to handle Service Catalog based cloudformation events.
    responseBody = {
        'Status': status,
        'Reason': message,
        'PhysicalResourceId': event['ServiceToken'],
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId']
    }

    requests.put(event['ResponseURL'], data=json.dumps(responseBody))
    lambda_client = get_client('lambda')
    function_name = os.environ['AWS_LAMBDA_FUNCTION_NAME']
    print('Deleting resources and rolling back the stack.')
    lambda_client.delete_function(FunctionName=function_name)
    #requests.put(event['ResponseURL'], data=json.dumps(responseBody))
    
def role_inlinepolicy(requestype,credentials,awsrolename,policyname,awsrolepolicy):
    # Function to create a new, or replace an existing inline IAM role policy.
    # Parameters:
    #   requestype:     Type of action being requested, currently only "Add" supported.
    #   credentials:    AWS credentials object for the account housing the existing role to be modified.
    #   awsrolename:    The AWS role name to be modified, this is the name and NOT ARN value.
    #   policyname:     The inline policy name to create or overwrite.
    #   awsrolepolicy:  A string representation of a complete AWS IAM Role policy to attach inline.
    iam_client = boto3.client('iam',aws_access_key_id=credentials['AccessKeyId'],
                                    aws_secret_access_key=credentials['SecretAccessKey'],
                                    aws_session_token=credentials['SessionToken'])
    if (requestype == "add"):
        print("--- Adding to IAM policy ---")
        attempt_counter = 1   #Try 20 times, every 30 secs for a maximum of 10 min. 
        while attempt_counter <= 20:
            try:
                update_role_response = iam_client.put_role_policy(RoleName=awsrolename,PolicyName=policyname,PolicyDocument=awsrolepolicy)
            except botocore.exceptions.ClientError as e:
                print("Error on attempt# {}, attaching policy to the role : {}".format(attempt_counter,e))
            else:
                print("Success on attempt# {}, attaching policy to the role".format(attempt_counter))
                attempt_counter = 999
            attempt_counter += 1
        return update_role_response
    
def create_awsprovider_file(accountrole,region,iac_account_id,rolearn,parenthub,accountname,deploytype):
    # Function call is used for creating the special Terraform AWS provider file for a particular environment.
    # Parameters:
    #  accountrole      = AWS credentials needed to assume access to IaC Bucket account.
    #  region           = The default AWS provider region, passed from the AWS confgi service user specified parameter.
    #  iac_account_id   = The AWS iac special account id.
    #  account_id       = The AWS environment account being created.
    #  rolearn          = The terraform ARN role to pass into the provider file (and grant access).
    #  parenthub        = The hub environment name this account is attached to, or the hubname if the account is the hub.
    #  accountname      = The AWS account name, which equates to the environment name being created.
    #  deploytype       = Are you creating the build role or deploy role aws provider file?

    providercontent = open('templates/awsprovider.template', 'r').read()
    providercontent = providercontent.format(
        iac_account_id=iac_account_id,
        accountname=accountname,
        region=region,
        rolearn=rolearn,
        deploytype=deploytype
    )

    credentials = assume_role(iac_account_id, accountrole)
    s3_client = boto3.resource('s3',aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials['SessionToken'])
    try:
        response = s3_client.Object('yourcompanynameORcustomprefix-iac-'+parenthub, 'providers/'+accountname+'/tf_awsprovider-'+accountname+'_{dtype}.tf'.format(dtype=deploytype)).put(Body=providercontent)
    except botocore.exceptions.ClientError as e:
        print("Error creating AWS Provider file.  Error: {}".format(e))
        return False
    return True

def create_instanceprofilerole(newrole,top_level_account,credentials,newrolepolicy,newtrustpolicy):
    # Function to create an EC2 instance Profile Launch role.  
    #   Unlike the AWS GUI a role created in code DOES NOT automatically result in the creation of the "hidden" EC2 launch role with the same name.
    #   This function creates an EC2 profile launch role for any roles created in code that need to be assumed by an EC2 instance.
    #   TO avoid confusion create this launch policy role with the same name, and policies as a visible entry.
    # Parameters:
    #   newrole:            role name to create.  Suggest creating the EC2 Profile role the exact same name as the IAM role (like the AWS console does!)
    #   top_level_account:  To be removed, does not serve a required function any longer, any string should be fine.
    #   credentials:        AWS credentials object for the account to create the EC2 profile instance role.
    #   newrolepolicy:      The IAM policy to assign to the profile role.  This is a string presentation of the JSON policy code!
    #   newtrustpolicy:     The IAM trust policy to assign to the profile role.  This is a string presentation of the JSON policy code!
    iam_client = boto3.client('iam',aws_access_key_id=credentials['AccessKeyId'],
                                  aws_secret_access_key=credentials['SecretAccessKey'],
                                  aws_session_token=credentials['SessionToken'])
    # Create an AWS EC2 Instance Profile Launch Role
    try:
        response = iam_client.create_instance_profile(InstanceProfileName=newrole)
    except botocore.exceptions.ClientError as e:
        print("Error creating the specified profile launch role. Error : {}".format(e))
    
    # Call function to create a matching AWS IAM Role
    try:
        newrole_arn = create_newrole(newrole,top_level_account,credentials,newrolepolicy,newtrustpolicy)
    except botocore.exceptions.ClientError as e:
        print("Error creating the specified role. Error : {}".format(e))
        newrole_arn = "arn:aws:iam::"+iac_account_id+":role/"+newrole

    #Attach role to instance profile role
    try:
        response = iam_client.add_role_to_instance_profile(InstanceProfileName=newrole,RoleName=newrole)
    except botocore.exceptions.ClientError as e:
        print("Error associating role to instance profile role. Error : {}".format(e))
        newrole_arn = None
    return (response)

def main(event,context):
    # Main function branch of Bootstrapper account creation code.
    # Only the "Create" Service Catalog/Cloudformation event is handled in code at this time.
    # Parameters are read from two sources, 
    #   in the first block these variables are read from environment variables set from cloudformation Service Catalog product.
    #   in the second block the variables are read from a bootstrapper.ini file included as part of the bootstrapper Service Catalog solution.
    
    print(event)
    client = get_client('organizations')
    accountname = os.environ['accountname']
    accountemail = os.environ['accountemail']
    parenthub = os.environ['parenthub']
    ishub = os.environ['ishub']
    accountrole = 'OrganizationAccountAccessRole'
    iac_account_id = os.environ['iac_account_id']
    stackname = os.environ['stackname']
    stackregion = os.environ['stackregion']
    sourcebucket = os.environ['sourcebucket']
    removedefaultvpc = os.environ['removedefaultvpc']

    # Read account bootstrapper configuration from required "bootstrapper.ini" file.
    config = configparser.ConfigParser()
    config.read('bootstrapper.ini')
    access_to_billing = config.get('General', 'access_to_billing', fallback='ALLOW')
    baselinetemplate = config.get('General', 'baselinetemplate', fallback='')
    testaccountid = config.get('General', 'testaccountid')
    testmode = config.getboolean('General', 'testmode', fallback='False')

    print("access_to_billing: {}".format(access_to_billing))
    print("baselinetemplate: {}".format(baselinetemplate))
    print("testaccountid: {}".format(testaccountid))
    print("testmode: {}".format(testmode))

    scp = None

    # This should be converted to some AWS call to retrieve dynamically!
    RegiontoAZMap = {
        "ap-northeast-1": ["ap-northeast-1a","ap-northeast-1c"],
        "ap-northeast-2": [ "ap-northeast-2a","ap-northeast-2c"],
        "ap-northeast-3": [ "ap-northeast-3a" ],
        "ap-south-1": [ "ap-south-1a","ap-south-1b"],
        "ap-southeast-1": [ "ap-southeast-1a","ap-southeast-1b","ap-southeast-1c"],
        "ap-southeast-2": [ "ap-southeast-2a","ap-southeast-2b","ap-southeast-2c"],
        "ca-central-1": ["ca-central-1a","ca-central-1b"],
        "eu-central-1": ["eu-central-1a","eu-central-1b","eu-central-1c"],
        "eu-west-1": [ "eu-west-1a","eu-west-1b","eu-west-1c"],
        "eu-west-2": [ "eu-west-2a","eu-west-2b","eu-west-2c"],
        "eu-west-3": [ "eu-west-3a","eu-west-3b","eu-west-3c"],
        "sa-east-1": [ "sa-east-1a","sa-east-1c"],
        "us-east-1": [ "us-east-1a","us-east-1b","us-east-1c","us-east-1d","us-east-1e","us-east-1f"],
        "us-east-2": [ "us-east-2a","us-east-2b","us-east-2c"],
        "us-west-1": [ "us-west-1b","us-west-1c"],
        "us-west-2": [ "us-west-2a","us-west-2b","us-west-2c"]
    }
    # Standard EC2 AWS trust policy
    AWSEC2trustpolicy = json.dumps({
                                    "Version": "2012-10-17",
                                      "Statement": [{
                                        "Effect": "Allow",
                                        "Principal": {
                                            "Service": "ec2.amazonaws.com"
                                        },
                                        "Action": "sts:AssumeRole"
                                      }]
                                    } 
                                )

    if (event['RequestType'] == 'Create'):
        selfinvoke(event,'Wait')
        top_level_account = event['ServiceToken'].split(':')[4]
        org_client = get_client('organizations')
        
        preferred_az_list = RegiontoAZMap[stackregion]
        
        try:
            list_roots_response = org_client.list_roots()
            #print(list_roots_response)
            root_id = list_roots_response['Roots'][0]['Id']
        except:
            root_id = "Error"
    
        if root_id  is not "Error":
            ### List the available AWS Oranization OU's 
            #if(organization_unit_name is not None):
                #(organization_unit_name,organization_unit_id) = get_ou_name_id(root_id,organization_unit_name)
            
            # Create AWS account (if not in testmode, be careful not to release a production version of the account builder with testmode left on!)
            if not testmode:
                print ("Creating new account: " + accountname + " (" + accountemail + ")")
                print ("AWS Account creation variables:")
                print ("event: {}".format(event))
                print ("accountname: {}".format(accountname))
                print ("accountemail: {}".format(accountemail))
                print ("accountrole: {}".format(accountrole))
                print ("access_to_billing: {}".format(access_to_billing))
                print ("scp: {}".format(scp))
                print ("root_id: {}".format(root_id))

                (create_account_response,account_id) = create_account(event,accountname,accountemail,accountrole,access_to_billing,scp,root_id)
                print("Created acount:{}\n".format(account_id))
            else:
                account_id = testaccountid
            
            #attach_policy_response = org_client.attach_policy(PolicyId=scp_id,TargetId=account_id)
            credentials = assume_role(account_id, accountrole)

            #--------------------------------------------------------------------------------------------
            # Create HUB Account TFS Agent Queue EC2 Roles in Master ORG if account privisioned is a HUB.
            #--------------------------------------------------------------------------------------------
            # Roles below need to be created in the special IaC Terraform management account.
            
            # Retrieve assume credentials for special IaC AWS Org Account
            credentials = assume_role(iac_account_id, accountrole)
            
            if ishub=='true':
                print("--- Account has been designated a Transit HUB! ---")
                # Create new S3 bucket in IaC AWS Org Account
                print("--- Creating IaC HUB bucket ---")
                try:
                    s3_client = boto3.client('s3',aws_access_key_id=credentials['AccessKeyId'],
                                  aws_secret_access_key=credentials['SecretAccessKey'],
                                  aws_session_token=credentials['SessionToken'])
                    s3response = s3_client.create_bucket(
                        Bucket = 'yourcompanynameORcustomprefix-iac-'+accountname,
                        ACL = 'private',
                        CreateBucketConfiguration = {
                            'LocationConstraint': stackregion
                        }
                        #ObjectLockEnabledForBucket=True|False
                    )
                except botocore.exceptions.ClientError as e:
                    print("Error creating the special Terraform IaC bucket!!!!. Error : {}".format(e))
                                
                # Create new ec2_iacbuild_{hubenv} iac account EC2 role used by code pipeline build agents.
                print("--- Creating IaC HUB EC2 build role ---")
                newrole = "ec2_iacbuild_"+parenthub
                newrolepolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":{{\"Sid\":\"AllowHUBTerraformRoleAssume\",\"Effect\":\"Allow\",\"Action\":\"sts:AssumeRole\",\"Resource\":[\"arn:aws:iam::{}:role/terraform_reader\",\"arn:aws:iam::{}:role/s3_iac_{}\"]}}}}".format(account_id,account_id,accountname)
                
                try:
                    newrole_arn = create_instanceprofilerole(newrole,top_level_account,credentials,newrolepolicy,AWSEC2trustpolicy)
                except botocore.exceptions.ClientError as e:
                    print("Error creating the specified role. Error : {}".format(e))
                    newrole_arn = "arn:aws:iam::"+iac_account_id+":role/"+newrole
                print(newrole_arn)
                
                # Create new EC2 ec2_iacdeploy_{hubenv} iac account role.
                print("--- Creating IaC HUB EC2 Deploy Role ---")
                newrole = "ec2_iacdeploy_"+parenthub
                newrolepolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":{{\"Sid\":\"AllowHUBTerraformRoleAssume\",\"Effect\":\"Allow\",\"Action\":\"sts:AssumeRole\",\"Resource\":[\"arn:aws:iam::{}:role/terraform_writer\",\"arn:aws:iam::{}:role/s3_iac_{}\"]}}}}".format(account_id,account_id,accountname)
                
                try:
                    newrole_arn = create_instanceprofilerole(newrole,top_level_account,credentials,newrolepolicy,AWSEC2trustpolicy)
                except botocore.exceptions.ClientError as e:
                    print("Error creating the specified role. Error : {}".format(e))
                    newrole_arn = "arn:aws:iam::"+iac_account_id+":role/"+newrole
                print(newrole_arn)
                
                # Create new s3_iac_{hubenv} iac account role
                print("--- Creating IaC S3 Terraform bucket access role ---")
                newrole = "s3_iac_"+accountname
                newrolepolicy = json.dumps (
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "ALLOWIACBUCKETREAD"+accountname,
                                "Effect": "Allow",
                                "Action": [
                                    "s3:List*"
                                ],
                                "Resource": "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub
                            },
                            {
                                "Sid": "ALLOWIACACCESSREAD"+accountname,
                                "Effect": "Allow",
                                "Action": [
                                    "s3:Get*",
                                    "s3:List*"
                                ],
                                "Resource": "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub+"/providers/"+accountname+"/*"
                            },
                            {
                                "Sid": "ALLOWIACACCESSWRITE"+accountname,
                                "Effect": "Allow",
                                "Action": [
                                    "s3:DeleteObject",
                                    "s3:Get*",
                                    "s3:List*",
                                    "s3:PutObject"
                                ],
                                "Resource": [
                                    "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub+"/release_artifacts/"+accountname+"/*",
                                    "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub+"/terraformstate/"+accountname+"/*"
                                ]
                            }
                        ]
                    }
                )

                newtrustpolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":[{{\"Effect\":\"Allow\",\"Principal\":{{\"AWS\":[\"arn:aws:iam::{}:role/ec2_iacbuild_{}\",\"arn:aws:iam::{}:role/ec2_iacdeploy_{}\"]}},\"Action\":\"sts:AssumeRole\"}}]}}".format(iac_account_id,accountname,iac_account_id,accountname)
                
                try:
                    newrole_arn = create_newrole(newrole,top_level_account,credentials,newrolepolicy,newtrustpolicy)
                except botocore.exceptions.ClientError as e:
                    print("Error creating the specified role. Error : {}".format(e))
                    newrole_arn = "arn:aws:iam::"+iac_account_id+":role/"+newrole
                print(newrole_arn)
                
            else:
                # Account being created is a Spoke Account
                # Create new s3_iac_{hubenv} iac account role
                print("--- Creating IaC S3 Terraform bucket access role ---")
                newrole = "s3_iac_"+accountname
                newrolepolicy = json.dumps (
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "ALLOWIACBUCKETREAD"+accountname,
                                "Effect": "Allow",
                                "Action": [
                                    "s3:List*"
                                ],
                                "Resource": "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub
                            },
                            {
                                "Sid": "ALLOWIACACCESSREAD"+accountname,
                                "Effect": "Allow",
                                "Action": [
                                    "s3:Get*",
                                    "s3:List*"
                                ],
                                "Resource": "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub+"/providers/"+accountname+"/*"
                            },
                            {
                                "Sid": "ALLOWIACACCESSWRITE"+accountname,
                                "Effect": "Allow",
                                "Action": [
                                    "s3:DeleteObject",
                                    "s3:Get*",
                                    "s3:List*",
                                    "s3:PutObject"
                                ],
                                "Resource": [
                                    "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub+"/release_artifacts/"+accountname+"/*",
                                    "arn:aws:s3:::yourcompanynameORcustomprefix-iac-"+parenthub+"/terraformstate/"+accountname+"/*"
                                ]
                            }
                        ]
                    }
                )

                newtrustpolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":[{{\"Effect\":\"Allow\",\"Principal\":{{\"AWS\":[\"arn:aws:iam::{}:role/ec2_iacbuild_{}\",\"arn:aws:iam::{}:role/ec2_iacdeploy_{}\"]}},\"Action\":\"sts:AssumeRole\"}}]}}".format(iac_account_id,parenthub,iac_account_id,parenthub)
                
                try:
                    newrole_arn = create_newrole(newrole,top_level_account,credentials,newrolepolicy,newtrustpolicy)
                except botocore.exceptions.ClientError as e:
                    print("Error creating the specified role. Error : {}".format(e))
                    newrole_arn = "arn:aws:iam::"+iac_account_id+":role/"+newrole
                print(newrole_arn)
                
            #######
            # Perform the following tasks for all account types
            #######
            
            # Add the new account terraform roles yet to be created to the IaC account's special HUB EC2 devops agent roles 
            # terraform_reader
            newrolepolicy = json.dumps(
                {
                    "Version":"2012-10-17",
                    "Statement": 
                    {
                        "Sid":"ALLOWTERRAFORMREADERASSUME"+accountname,
                        "Effect":"Allow",
                        "Action":"sts:AssumeRole",
                        "Resource":"arn:aws:iam::"+account_id+":role/terraform_reader"
                    }
                }
            )
            try:
                newrole_arn = role_inlinepolicy("add",credentials,"ec2_iacbuild_"+parenthub,"ec2_iacbuild_"+accountname,newrolepolicy)
            except botocore.exceptions.ClientError as e:
                print("Error adding policy to specified EC2 Iam role. Error : {}".format(e))
                newrole_arn = "arn:aws:iam::"+iac_account_id+":role/ec2_iacbuild_"+parenthub
            print(newrole_arn)

            # terraform_writer
            newrolepolicy = json.dumps(
                {
                    "Version":"2012-10-17",
                    "Statement": 
                    {
                        "Sid":"ALLOWTERRAFORMWRITERASSUME"+accountname,
                        "Effect":"Allow",
                        "Action":"sts:AssumeRole",
                        "Resource":"arn:aws:iam::"+account_id+":role/terraform_writer"
                    }
                }
            )
            try:
                newrole_arn = role_inlinepolicy("add",credentials,"ec2_iacdeploy_"+parenthub,"ec2_iacdeploy_"+accountname,newrolepolicy)
            except botocore.exceptions.ClientError as e:
                print("Error adding policy to specified EC2 Iam role. Error : {}".format(e))
                newrole_arn = "arn:aws:iam::"+iac_account_id+":role/ec2_iacdeploy_"+parenthub
            print(newrole_arn)
                
            # Create special AWS provider files in IaC Environment Terraform Bucket
            print ("Creating Special Terraform AWS Build Provider file...")
            response = create_awsprovider_file(accountrole,stackregion,iac_account_id,"arn:aws:iam::{}:role/terraform_reader".format(account_id),parenthub,accountname,"build")
            print (response)
            print ("Creating Special Terraform AWS Deploy Provider file...")
            response = create_awsprovider_file(accountrole,stackregion,iac_account_id,"arn:aws:iam::{}:role/terraform_writer".format(account_id),parenthub,accountname,"release")
            print (response)
            
            # Assume credentials that can be used in new account.
            credentials = assume_role(account_id, accountrole)
            
            # Create new account local Terraform Reader role.
            time.sleep(20)
            print("--- Creating New Account Special Terraform Reader Role ---")
            newrole = "terraform_reader"
            newrolepolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":[{{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\"],\"Resource\":\"arn:aws:s3:::yourcompanynameORcustomprefix-iac-{}/*/{}/*\"}}]}}".format(parenthub,accountname)
            newtrustpolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":[{{\"Effect\":\"Allow\",\"Principal\":{{\"AWS\":\"arn:aws:iam::{}:role/ec2_iacbuild_{}\"}},\"Action\":\"sts:AssumeRole\"}}]}}".format(iac_account_id,parenthub)

            newrole_arn = create_newrole(newrole,top_level_account,credentials,newrolepolicy,newtrustpolicy)
            print(newrole_arn)
            # Attach readonly built in admin policy to terraform reader role
            response = attach_policy("terraform_reader","arn:aws:iam::aws:policy/ReadOnlyAccess",credentials)

            # Create new account local Terraform Writer role.
            print("--- Creating New Account Special Terraform Writer Role ---")
            newrole = "terraform_writer"
            newrolepolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":[{{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\"],\"Resource\":\"arn:aws:s3:::yourcompanynameORcustomprefix-iac-{}/*/{}/*\"}}]}}".format(parenthub,accountname)
            newtrustpolicy = "{{\"Version\":\"2012-10-17\",\"Statement\":[{{\"Effect\":\"Allow\",\"Principal\":{{\"AWS\":\"arn:aws:iam::{}:role/ec2_iacdeploy_{}\"}},\"Action\":\"sts:AssumeRole\"}}]}}".format(iac_account_id,parenthub)
            
            newrole_arn = create_newrole(newrole,top_level_account,credentials,newrolepolicy,newtrustpolicy)
            print(newrole_arn)

            # Attach readonly built in admin policy to terraform writer role
            response = attach_policy("terraform_writer","arn:aws:iam::aws:policy/AdministratorAccess",credentials)


            # Switch to assume credentials that can be used in the new account.
            credentials = assume_role(account_id, accountrole)
            iam_client = boto3.client('iam',aws_access_key_id=credentials['AccessKeyId'],
                                  aws_secret_access_key=credentials['SecretAccessKey'],
                                  aws_session_token=credentials['SessionToken'])
            
            # Delete default account VPCs.
            ec2_client = get_client('ec2')
            if(removedefaultvpc!='false'):
                regions = []
                regions_response = ec2_client.describe_regions()
                for i in range(0,len(regions_response['Regions'])):
                    regions.append(regions_response['Regions'][i]['RegionName']) 
                for r in regions:
                    try:
                        #print('In the VPC deletion block - {}'.format(r))
                        delete_vpc_response = delete_default_vpc(credentials,r)
                    except botocore.exceptions.ClientError as e:
                        print("An error occured while deleting Default VPC in {}. Error: {}".format(r,e))
                        i+=1

            # Create or move account to appropriate AWS organizations OU.
            
            # Get the root account ID.
            print ("--- Configure account's Org OU membership --")
            org_client = boto3.client('organizations')
            root_id = org_client.list_roots().get('Roots')[0].get('Id')
            print(root_id)

            # Create/Attach an organizational policy
            if ishub=='true':
                organization_unit_name = accountname                
                try:
                    (organization_unit_name,organization_unit_id) = get_ou_name_id(root_id,organization_unit_name)
                    move_response = org_client.move_account(AccountId=account_id,SourceParentId=root_id,DestinationParentId=organization_unit_id)
                    
                except Exception as ex:
                    template = "An exception of type {0} occurred. Arguments:\n{1!r} "
                    message = template.format(type(ex).__name__, ex.args)
                    print(message)


            if scp is not None:
                attach_policy_response = client.attach_policy(PolicyId=scp, TargetId=account_id)
                print("Attach policy response "+str(attach_policy_response))
                
            respond_cloudformation(event, "SUCCESS", { "Message": "Account Created!", 
                                                       "LoginURL" : "https://"+account_id+".signin.aws.amazon.com/console?region="+stackregion+"#", 
                                                       "AccountID" : account_id, 
                                                       "Role" : newrole, 
                                                       "Stackregion": stackregion })
        else:
            print("Cannot access the AWS Organization ROOT. Contact the master account Administrator for more details.")
            #sys.exit(1)
            delete_respond_cloudformation(event, "FAILED", "Cannot access the AWS Organization ROOT. Contact the master account Administrator for more details.Deleting Lambda Function.")

    if(event['RequestType'] == 'Update'):
        print("Template in Update Status")
        respond_cloudformation(event, "SUCCESS", { "Message": "Resource update successful!" })
        #respond_cloudformation(event, "SUCCESS", { "Message": "Account Created!","Login URL : "https://" +account_id+".signin.aws.amazon.com/console", "AccountID" : account_id, "Username" : adminusername, "Role" : newrole })

    elif(event['RequestType'] == 'Delete'):
        try:
            delete_respond_cloudformation(event, "SUCCESS", "Delete Request Initiated. Deleting Lambda Function.")
        except:
            print("Couldnt initiate delete response.")


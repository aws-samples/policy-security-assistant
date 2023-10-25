# How to Build a Security Assistant with Generative AI Using Amazon Bedrock and AWS

[Leer en español](./README.es.md)

[Amazon Bedrock](https://aws.amazon.com/bedrock/) is a fully managed service offering a selection of high-performance foundational models (FM) from leading AI companies, such as AI21 Labs, Anthropic, Cohere, Meta, Stability AI, and Amazon, through a single API, along with a comprehensive set of capabilities needed to create generative AI applications, simplifying development while maintaining privacy and security. Using Amazon Bedrock, it's possible to build a web self-service portal that checks whether an [AWS Identity and Access Management (IAM)](https://aws.amazon.com/iam/) policy adheres to the principle of least privilege, aiming to streamline the permission approval process within an organization without compromising security.

Organizations are constantly evolving, developing new projects and applications. Essential for these applications to function is having the necessary permissions and access to carry out various actions on AWS services and resources. These actions are specified through [IAM policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html), expressed in JSON format.

Typically, project teams request permissions for their applications, and the organization's security team then validates, approves, or rejects these requests. Issues arise when project teams request access that doesn't align with the principle of least privilege. This challenge is magnified when security teams lack detailed insight into the applications and must enforce best practices. Due to the need for permission approvals, interactions between development and application areas can become bottlenecks, delaying the delivery of new projects and features to the organization.

![security-flow](./images/security_flow.png)

Application teams often interact multiple times with the security department, aiming to gain the accesses their applications require.

Ensuring that permission requests adhere to the principle of least privilege from the start accelerates the approval process, reduces bottlenecks, and diminishes user frustration.

## Web Self-Service Portal

The following application is a Web self-service portal, allowing users to check if the IAM policy adheres to the best practices of the principle of least privilege. In this instance, Amazon Bedrock will analyze the inputted policy, validate its syntax, and assess its compliance based on specificity of actions, resource restrictions, effects, and conditions. It will then highlight potential areas for policy improvement and provide a compliance score on a scale of 1 to 10. On this scale, 1 represents low adherence to the principle of least privilege, while 10 indicates high adherence.

![website](./images/website.png)

## Architecture
The following architecture diagram describes how the self-service portal operates.

![architecture_diagram](./images/architecture_diagram.png)

The self-service portal comprises a distribution of [Amazon CloudFront (1)](https://aws.amazon.com/cloudfront/), which distributes a web form stored in an [Amazon S3](https://aws.amazon.com/s3/) bucket.

Users enter the IAM policy into the web form, which communicates with the [Amazon API Gateway](https://aws.amazon.com/api-gateway/) (3) service using the [AWS SDK for Javascript](https://aws.amazon.com/sdk-for-javascript/).

Amazon API Gateway invokes the AWS Lambda function, which sends the policy to Amazon Bedrock, asking it to evaluate its syntax and adherence to the principle of least privilege, and provide a score between 1 to 10 based on its level of compliance.

## Implementation Guide

The solution is implemented in three parts,

1. Enable Amazon Bedrock on the AWS console.
2. Creation of Lambda Layer.
3. Deployment of the architecture via CloudFormation.

### 1. Enable Amazon Bedrock

Open the Amazon Bedrock console. In the left menu, select “Model access”, click the "Edit" button and enable the Anthropic > Claude model, then save the changes.

Remember, as of the date this article was published, Amazon Bedrock is available in the following AWS regions: US West (Oregon), Asia Pacific (Tokyo), Asia Pacific (Singapore), US East (N. Virginia).

### 2. Creation of Lambda Layer

For interaction between Lambda and Bedrock, we will need version 1.28.57 or higher of the [AWS Software Development Kit for Python (Boto3)](https://aws.amazon.com/sdk-for-python/). For this, we must create a Lambda layer in an environment with Python version 3.7 or higher. If we don't have such an environment, we can use the [AWS CloudShell](https://aws.amazon.com/cloudshell/) console.

To access Amazon CloudShell, log into the AWS Console. In the navigation bar, select the CloudShell service icon or type CloudShell in the search bar. A console will open in the browser, where you can run the following command.

```
curl -sSL https://raw.githubusercontent.com/aws-samples/policy-security-assistant/master/create-layer.sh | sh
```

This script will set up a Python 3 environment with version 1.28.61 of boto3, package the environment into the boto3-layer.zip file, and publish it as a Lambda Layer via the AWS CLI. The Layer ARN and Python version will be displayed at the end of the script and will be used during the CloudFormation template deployment.

The script's output will look something like this. It's essential to note this information for the next step.

Python Version: 3.10
Layer ARN: "arn:aws:lambda:us-east-1:111222333444:layer:security-assistant:1"

### 3. Deployment of the CloudFormation Template

- [Source Code in AWS Samples GitHub](https://github.com/aws-samples/policy-security-assistant/)
- [Cloudformation Template](https://github.com/aws-samples/policy-security-assistant/blob/main/security-assistant.yaml)


We will deploy the architecture using [Amazon CloudFormation](https://aws.amazon.com/cloudformation/). To do this, download the following [template](https://github.com/aws-samples/policy-security-assistant/blob/main/security-assistant.yaml), access the AWS Console and in the AWS CloudFormation service, select “Create Stack (with new resources)”. Then, click on “Upload a template file” and choose the already downloaded [security-assistant.yaml](https://github.com/aws-samples/policy-security-assistant/blob/main/security-assistant.yaml) template.

In the next section, we will name our stack according to our preference and fill in the LambdaLayerArn and PythonRuntimeVersion fields with the information obtained in the previous step.

![cloudformation](./images/cloudformation.png)

The CloudFormation stack will create the resources defined in the architecture. Once the stack creation is completed, in the Output section, we will find the API Gateway website URL and the S3 Bucket name. By opening the website link, we can access the security assistant.

![cloudformation_output](./images/cloudformation_output.png)

## Conclusion

Using Amazon Bedrock, it's possible to construct a self-service portal to assess if an Amazon IAM policy adheres to the principle of least privilege. This will speed up interactions between the security and application development areas.

Additionally, it's possible to modify this solution to integrate it into your organization's permission request workflow, for example, to automatically reject requests that don't meet a minimum compliance score. This will reduce the security team's backlog, leaving human interaction only for requests that comply with best practices.

## Note
This solution is a demonstration: The automated policy analysis should be considered a suggestion. Before implementing any policy in your organization, make sure to validate it with a security specialist

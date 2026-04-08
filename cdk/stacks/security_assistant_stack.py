"""CDK Stack for Policy Security Assistant v2.

Author: Hernan Fernandez Retamal
"""

import os
import secrets

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_wafv2 as wafv2,
    aws_logs as logs,
    aws_cloudwatch as cw,
)
from constructs import Construct

# Secret header value to verify requests come through CloudFront
ORIGIN_VERIFY_HEADER = "x-origin-verify"
ORIGIN_VERIFY_SECRET = secrets.token_hex(32)


class SecurityAssistantStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── DynamoDB Audit Table ──
        audit_table = dynamodb.Table(
            self, "AuditTable",
            partition_key=dynamodb.Attribute(name="request_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),
        )

        # ── Analyze Policy Lambda ──
        analyze_fn = lambda_.Function(
            self, "AnalyzePolicyFn",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "..", "backend", "lambda", "analyze_policy")
            ),
            timeout=Duration.seconds(60),
            memory_size=512,
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "AUDIT_TABLE_NAME": audit_table.table_name,
                "MODEL_ID": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                "BEDROCK_REGION": "us-east-1",
                "ORIGIN_VERIFY_HEADER": ORIGIN_VERIFY_HEADER,
                "ORIGIN_VERIFY_SECRET": ORIGIN_VERIFY_SECRET,
            },
            log_group=logs.LogGroup(
                self, "AnalyzePolicyLogGroup",
                retention=logs.RetentionDays.TWO_WEEKS,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        audit_table.grant_write_data(analyze_fn)
        analyze_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0",
                f"arn:aws:bedrock:*:{Stack.of(self).account}:inference-profile/us.anthropic.*",
            ],
        ))
        analyze_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["access-analyzer:ValidatePolicy"], resources=["*"],
        ))

        # ── Generate Policy Lambda ──
        generate_fn = lambda_.Function(
            self, "GeneratePolicyFn",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "..", "backend", "lambda", "generate_policy")
            ),
            timeout=Duration.seconds(60),
            memory_size=512,
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "AUDIT_TABLE_NAME": audit_table.table_name,
                "MODEL_ID": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                "BEDROCK_REGION": "us-east-1",
                "ORIGIN_VERIFY_HEADER": ORIGIN_VERIFY_HEADER,
                "ORIGIN_VERIFY_SECRET": ORIGIN_VERIFY_SECRET,
            },
            log_group=logs.LogGroup(
                self, "GeneratePolicyLogGroup",
                retention=logs.RetentionDays.TWO_WEEKS,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        audit_table.grant_write_data(generate_fn)
        generate_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0",
                f"arn:aws:bedrock:*:{Stack.of(self).account}:inference-profile/us.anthropic.*",
            ],
        ))
        generate_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["access-analyzer:ValidatePolicy"], resources=["*"],
        ))

        # ── API Gateway ──
        api_log_group = logs.LogGroup(
            self, "ApiLogGroup",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        api = apigw.RestApi(
            self, "PolicySecurityAssistantApi",
            rest_api_name="PolicySecurityAssistantApi",
            description="Policy Security Assistant v2 API",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                tracing_enabled=True,
                access_log_destination=apigw.LogGroupLogDestination(api_log_group),
                access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                    caller=True, http_method=True, ip=True, protocol=True,
                    request_time=True, resource_path=True, response_length=True,
                    status=True, user=True,
                ),
            ),
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )

        # Usage plan for throttling (no API key required — origin header protects access)
        usage_plan = api.add_usage_plan(
            "UsagePlan",
            name="SecurityAssistantUsagePlan",
            throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=20),
            quota=apigw.QuotaSettings(limit=1000, period=apigw.Period.DAY),
        )
        usage_plan.add_api_stage(stage=api.deployment_stage)

        # /api/security-assistant
        api_resource = api.root.add_resource("api")
        security_resource = api_resource.add_resource("security-assistant")
        security_resource.add_method("POST", apigw.LambdaIntegration(analyze_fn), api_key_required=False)
        security_resource.add_cors_preflight(
            allow_origins=["*"], allow_methods=["POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

        # /api/generate-policy
        generate_resource = api_resource.add_resource("generate-policy")
        generate_resource.add_method("POST", apigw.LambdaIntegration(generate_fn), api_key_required=False)
        generate_resource.add_cors_preflight(
            allow_origins=["*"], allow_methods=["POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

        # ── S3 Buckets ──
        logging_bucket = s3.Bucket(
            self, "LoggingBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
        )

        website_bucket = s3.Bucket(
            self, "WebsiteBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            server_access_logs_bucket=logging_bucket,
            server_access_logs_prefix="website-logs/",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ── CloudFront WAF ──
        cloudfront_waf = self._create_waf_web_acl("CloudFrontWAF", "CLOUDFRONT")

        # ── CloudFront Distribution (two origins: S3 + API Gateway) ──
        # API origin with secret header verification
        api_origin = origins.HttpOrigin(
            f"{api.rest_api_id}.execute-api.{Stack.of(self).region}.amazonaws.com",
            origin_path="/prod",
            custom_headers={ORIGIN_VERIFY_HEADER: ORIGIN_VERIFY_SECRET},
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
        )

        distribution = cloudfront.Distribution(
            self, "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(website_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                ),
            },
            default_root_object="index.html",
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            web_acl_id=cloudfront_waf.attr_arn,
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403, response_page_path="/index.html",
                    response_http_status=200, ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404, response_page_path="/index.html",
                    response_http_status=200, ttl=Duration.seconds(0),
                ),
            ],
        )

        # ── Deploy Frontend to S3 ──
        frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
        s3deploy.BucketDeployment(
            self, "DeployFrontend",
            sources=[s3deploy.Source.asset(frontend_path)],
            destination_bucket=website_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # ── API WAF ──
        api_waf = self._create_waf_web_acl("ApiWAF", "REGIONAL")
        wafv2.CfnWebACLAssociation(
            self, "ApiWafAssociation",
            resource_arn=api.deployment_stage.stage_arn,
            web_acl_arn=api_waf.attr_arn,
        )

        # ── Observability ──
        lambda_errors = analyze_fn.metric_errors(period=Duration.minutes(5))
        lambda_duration = analyze_fn.metric_duration(period=Duration.minutes(5))
        lambda_invocations = analyze_fn.metric_invocations(period=Duration.minutes(5))
        gen_errors = generate_fn.metric_errors(period=Duration.minutes(5))
        gen_duration = generate_fn.metric_duration(period=Duration.minutes(5))
        gen_invocations = generate_fn.metric_invocations(period=Duration.minutes(5))

        cw.Alarm(self, "LambdaErrorAlarm", metric=lambda_errors, threshold=5,
                 evaluation_periods=1, alarm_description="Lambda errors exceeded 5 in 5 min",
                 comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD)
        cw.Alarm(self, "LambdaDurationAlarm", metric=lambda_duration, threshold=30000,
                 evaluation_periods=2, alarm_description="Lambda duration exceeded 30s",
                 comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD)

        api_5xx = api.metric_server_error(period=Duration.minutes(5))
        api_4xx = api.metric_client_error(period=Duration.minutes(5))
        cw.Alarm(self, "Api5xxAlarm", metric=api_5xx, threshold=5,
                 evaluation_periods=1, alarm_description="API 5xx errors exceeded 5 in 5 min")

        dashboard = cw.Dashboard(self, "SecurityAssistantDashboard", dashboard_name="SecurityAssistant-v2")
        dashboard.add_widgets(
            cw.GraphWidget(title="Analyze — Invocations", left=[lambda_invocations]),
            cw.GraphWidget(title="Analyze — Errors", left=[lambda_errors]),
            cw.GraphWidget(title="Analyze — Duration (ms)", left=[lambda_duration]),
            cw.GraphWidget(title="Generate — Invocations", left=[gen_invocations]),
            cw.GraphWidget(title="Generate — Errors", left=[gen_errors]),
            cw.GraphWidget(title="Generate — Duration (ms)", left=[gen_duration]),
            cw.GraphWidget(title="API 4xx / 5xx", left=[api_4xx, api_5xx]),
        )

        # ── Outputs ──
        CfnOutput(self, "WebsiteURL", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "ApiURL", value=api.url)
        CfnOutput(self, "DashboardURL",
                  value=f"https://console.aws.amazon.com/cloudwatch/home#dashboards:name=SecurityAssistant-v2")

    # ── Helper: WAF WebACL ──
    def _create_waf_web_acl(self, id: str, scope: str) -> wafv2.CfnWebACL:
        managed_rules = [
            ("AWSManagedRulesAmazonIpReputationList", 0),
            ("AWSManagedRulesCommonRuleSet", 1),
            ("AWSManagedRulesKnownBadInputsRuleSet", 2),
        ]
        rules = []
        for name, priority in managed_rules:
            rules.append(wafv2.CfnWebACL.RuleProperty(
                name=name, priority=priority,
                override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS", name=name,
                    )
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    sampled_requests_enabled=True, cloud_watch_metrics_enabled=True,
                    metric_name=f"{name}Metric",
                ),
            ))
        return wafv2.CfnWebACL(
            self, id, scope=scope,
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True, cloud_watch_metrics_enabled=True,
                metric_name=f"{id}Metric",
            ),
            rules=rules,
        )

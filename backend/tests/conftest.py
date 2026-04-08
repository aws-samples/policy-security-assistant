"""Shared fixtures for Lambda handler tests."""

import json
import os
import pytest
import boto3
from moto import mock_dynamodb
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.setenv("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB audit table."""
    with mock_dynamodb():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="AuditTable",
            KeySchema=[
                {"AttributeName": "request_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "request_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield client


SAMPLE_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": "ec2:*",
        "Resource": "*",
    }]
})

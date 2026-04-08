"""Shared test helpers for Lambda handler tests."""

import json
import io
import os
import importlib
import sys
from unittest.mock import MagicMock


def make_event(body: dict) -> dict:
    return {"body": json.dumps(body)}


def make_bedrock_mock(text: str) -> MagicMock:
    """Create a Bedrock mock that returns fresh BytesIO on each call."""
    mock = MagicMock()

    def invoke_side_effect(**kwargs):
        body_bytes = json.dumps({"content": [{"text": text}]}).encode()
        return {"body": io.BytesIO(body_bytes)}

    mock.invoke_model.side_effect = invoke_side_effect
    return mock


def load_lambda(module_path, bedrock_text="ok", aa_findings=None):
    """Load a Lambda module and replace its clients with mocks.

    Instead of fighting with importlib.reload, we load the module once
    and directly replace the module-level client variables.
    """
    if aa_findings is None:
        aa_findings = []

    # Ensure env vars are set
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AUDIT_TABLE_NAME"] = "AuditTable"
    os.environ["BEDROCK_REGION"] = "us-east-1"
    os.environ["MODEL_ID"] = "test-model"

    # Patch boto3 before first import
    import boto3
    orig_client = boto3.client
    orig_resource = boto3.resource

    mock_bedrock = make_bedrock_mock(bedrock_text)
    mock_aa = MagicMock()
    mock_aa.validate_policy.return_value = {"findings": aa_findings, "nextToken": None}
    mock_table = MagicMock()
    mock_dynamo = MagicMock()
    mock_dynamo.Table.return_value = mock_table

    boto3.client = lambda svc, **kw: mock_bedrock if svc == "bedrock-runtime" else (mock_aa if svc == "accessanalyzer" else MagicMock())
    boto3.resource = lambda svc, **kw: mock_dynamo if svc == "dynamodb" else MagicMock()

    # Force fresh import — clear both the wrapper and the underlying module
    for key in list(sys.modules.keys()):
        if module_path in key or "index" == key:
            del sys.modules[key]

    mod = importlib.import_module(module_path)

    # Restore boto3
    boto3.client = orig_client
    boto3.resource = orig_resource

    return mod, mock_bedrock, mock_aa, mock_table

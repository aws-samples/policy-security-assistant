"""Tests for the generate_policy Lambda handler."""

import json
from tests.helpers import make_event, load_lambda

MODULE = "lambda_pkg.generate_policy.index"

SAFE_RESPONSE = json.dumps({
    "safe": True,
    "policy": {"Version": "2012-10-17", "Statement": [
        {"Sid": "ReadOrders", "Effect": "Allow", "Action": ["dynamodb:GetItem"],
         "Resource": "arn:aws:dynamodb:us-east-1:123456789012:table/orders"}
    ]},
    "explanation": "Allows reading from the orders table.",
})

UNSAFE_RESPONSE = json.dumps({
    "safe": False,
    "message": "Your request is too broad.",
})

FENCED_RESPONSE = f"```json\n{SAFE_RESPONSE}\n```"


def test_safe_policy():
    mod, _, _, _ = load_lambda(MODULE, bedrock_text=SAFE_RESPONSE)
    result = mod.lambda_handler(make_event({"description": "Read from DynamoDB", "lang": "en"}), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["safe"] is True
    assert body["policy"]["Version"] == "2012-10-17"
    assert "aa_findings" in body


def test_unsafe_response():
    mod, _, _, _ = load_lambda(MODULE, bedrock_text=UNSAFE_RESPONSE)
    result = mod.lambda_handler(make_event({"description": "full admin access", "lang": "en"}), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["safe"] is False
    assert "message" in body


def test_strips_code_fences():
    mod, _, _, _ = load_lambda(MODULE, bedrock_text=FENCED_RESPONSE)
    result = mod.lambda_handler(make_event({"description": "Read from DynamoDB", "lang": "en"}), None)

    body = json.loads(result["body"])
    assert body["safe"] is True
    assert "policy" in body


def test_rejects_empty_description():
    mod, _, _, _ = load_lambda(MODULE)
    result = mod.lambda_handler(make_event({"description": "", "lang": "en"}), None)
    assert result["statusCode"] == 400


def test_cors_headers():
    mod, _, _, _ = load_lambda(MODULE)
    result = mod.lambda_handler(make_event({"description": "", "lang": "en"}), None)
    assert result["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "X-Api-Key" in result["headers"]["Access-Control-Allow-Headers"]


def test_multiturn_passes_history():
    mod, mock_bedrock, _, _ = load_lambda(MODULE, bedrock_text=SAFE_RESPONSE)
    event = make_event({
        "description": "also restrict to us-east-1", "lang": "en",
        "messages": [
            {"role": "user", "content": "Read from DynamoDB orders table"},
            {"role": "assistant", "content": SAFE_RESPONSE},
        ],
    })
    result = mod.lambda_handler(event, None)

    assert result["statusCode"] == 200
    assert mock_bedrock.invoke_model.call_count == 1

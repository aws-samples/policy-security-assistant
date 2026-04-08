"""Tests for the analyze_policy Lambda handler."""

import json
from tests.helpers import make_event, load_lambda
from tests.conftest import SAMPLE_POLICY

MODULE = "lambda_pkg.analyze_policy.index"


def test_returns_200_with_analysis():
    aa_finding = {
        "findingType": "SECURITY_WARNING", "issueCode": "WILDCARD_ACTION",
        "findingDetails": "Wildcard action detected",
        "learnMoreLink": "https://docs.aws.amazon.com", "locations": [],
    }
    mod, _, _, _ = load_lambda(MODULE, bedrock_text="## Analysis\n**3/10**", aa_findings=[aa_finding])
    result = mod.lambda_handler(make_event({"policy": SAMPLE_POLICY, "lang": "en"}), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert "message" in body
    assert len(body["aa_findings"]) == 1
    assert body["aa_findings"][0]["type"] == "SECURITY_WARNING"


def test_rejects_empty_policy():
    mod, _, _, _ = load_lambda(MODULE)
    result = mod.lambda_handler(make_event({"policy": "", "lang": "en"}), None)
    assert result["statusCode"] == 400


def test_rejects_invalid_json():
    mod, _, _, _ = load_lambda(MODULE)
    result = mod.lambda_handler(make_event({"policy": "not json {{{", "lang": "en"}), None)
    assert result["statusCode"] == 400
    assert "Invalid JSON" in json.loads(result["body"])["error"]


def test_cors_headers():
    mod, _, _, _ = load_lambda(MODULE)
    result = mod.lambda_handler(make_event({"policy": "", "lang": "en"}), None)
    assert result["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "X-Api-Key" in result["headers"]["Access-Control-Allow-Headers"]


def test_followup_requires_message():
    mod, _, _, _ = load_lambda(MODULE)
    event = make_event({
        "policy": SAMPLE_POLICY, "message": "", "lang": "en",
        "messages": [{"role": "user", "content": "analyze this"}],
    })
    result = mod.lambda_handler(event, None)
    assert result["statusCode"] == 400


def test_followup_sends_history():
    mod, mock_bedrock, _, _ = load_lambda(MODULE, bedrock_text="Fixed version")
    event = make_event({
        "policy": SAMPLE_POLICY, "message": "fix issue #1", "lang": "en",
        "messages": [
            {"role": "user", "content": "Analyze this policy"},
            {"role": "assistant", "content": "## Analysis\n**3/10**"},
        ],
    })
    result = mod.lambda_handler(event, None)
    assert result["statusCode"] == 200
    # Verify bedrock was called (side_effect tracks calls)
    assert mock_bedrock.invoke_model.call_count == 1


def test_default_language():
    mod, mock_bedrock, _, _ = load_lambda(MODULE, bedrock_text="Analysis result")
    result = mod.lambda_handler(make_event({"policy": SAMPLE_POLICY}), None)
    assert result["statusCode"] == 200
    assert mock_bedrock.invoke_model.call_count == 1

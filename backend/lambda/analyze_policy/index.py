"""Policy Security Assistant — Lambda handler.

Analyzes IAM policies for least-privilege compliance using
Amazon Bedrock Claude Sonnet 4.5 (Messages API).
Supports multi-turn conversation for iterative remediation.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("BEDROCK_REGION", os.environ["AWS_REGION"]))
aa_client = boto3.client("accessanalyzer")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["AUDIT_TABLE_NAME"])

MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
MAX_TOKENS = 2048
MAX_HISTORY_MESSAGES = 20

ORIGIN_HEADER = os.environ.get("ORIGIN_VERIFY_HEADER", "")
ORIGIN_SECRET = os.environ.get("ORIGIN_VERIFY_SECRET", "")


def _verify_origin(event):
    """Verify the request came through CloudFront via the secret header."""
    if not ORIGIN_SECRET:
        return True  # skip verification if not configured (local dev)
    headers = event.get("headers", {}) or {}
    return headers.get(ORIGIN_HEADER) == ORIGIN_SECRET

SYSTEM_PROMPT = """You are an AWS IAM security expert. Your job is to analyze IAM policies
for compliance with the principle of least privilege, and help users fix them interactively.

This is a multi-turn conversation. The user may:
- Submit a policy for initial analysis
- Ask you to fix specific issues from the analysis
- Ask you to modify the policy (add conditions, restrict resources, etc.)
- Ask follow-up questions about the analysis

For the INITIAL analysis of a policy, respond using this structure:

## Syntax Validation
State whether the JSON is valid or not. If invalid, stop here.

## Compliance Score
**X/10** — one-line summary.

## Issues Found
Numbered list with bold titles and sub-bullets.

## Recommended Improvements
Numbered list with code snippets.

## Summary
One or two sentences.

For FOLLOW-UP messages (fixing issues, modifying the policy, answering questions):
- Respond naturally and concisely
- When providing an updated policy, include the COMPLETE policy JSON in a code block
- Re-score the updated policy if you made changes
- Reference the specific changes you made

Analysis criteria:
- Specificity of actions (wildcards vs explicit actions)
- Resource restrictions (wildcards vs specific ARNs)
- Use of conditions to narrow scope
- Effect statements (Allow vs Deny patterns)

Be concise, actionable, and specific. Always follow section order regardless of language."""

LANG_MAP = {"es": "Spanish", "pt": "Portuguese", "en": "English"}


def lambda_handler(event, context):
    request_id = str(uuid.uuid4())
    start_time = time.time()

    if not _verify_origin(event):
        return _response(403, {"error": "Forbidden"})

    try:
        body = json.loads(event.get("body", "{}"))
        policy_text = body.get("policy", "")
        user_text = body.get("message", "")  # follow-up message
        lang = body.get("lang", "en")
        history = body.get("messages", [])  # previous conversation turns

        # First turn requires a policy
        if not history and (not policy_text or not policy_text.strip()):
            return _response(400, {"error": "Policy text is required."})

        # Follow-up turns require a message
        if history and not user_text.strip():
            return _response(400, {"error": "Message is required."})

        language = LANG_MAP.get(lang, "English")

        # Run Access Analyzer on initial policy submission only
        aa_findings = []
        if not history and policy_text:
            try:
                json.loads(policy_text)
                aa_findings = _validate_with_access_analyzer(policy_text)
            except json.JSONDecodeError:
                return _response(400, {"error": "Invalid JSON in policy."})

        # Build messages array
        messages = []
        for msg in history[-MAX_HISTORY_MESSAGES:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Build the new user message
        if not history:
            # First turn: full analysis prompt
            user_message = (
                f"Analyze the following IAM policy for least-privilege compliance. "
                f"Respond in {language}.\n\n```json\n{policy_text}\n```"
            )
        else:
            # Follow-up: direct message
            user_message = user_text

        messages.append({"role": "user", "content": user_message})

        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": MAX_TOKENS,
                "temperature": 0.1,
                "system": SYSTEM_PROMPT,
                "messages": messages,
            }),
        )

        result = json.loads(response["body"].read())
        analysis = result["content"][0]["text"]
        duration_ms = int((time.time() - start_time) * 1000)

        _write_audit(request_id, policy_text or user_text, lang, analysis, duration_ms)

        logger.info("Policy analyzed", extra={"request_id": request_id, "lang": lang, "duration_ms": duration_ms})

        return _response(200, {
            "message": analysis,
            "request_id": request_id,
            "aa_findings": aa_findings,
        })

    except KeyError as e:
        logger.error("Missing key: %s", str(e))
        return _response(400, {"error": f"Missing key: {str(e)}"})
    except Exception:
        logger.exception("Unexpected error")
        return _response(500, {"error": "An internal error occurred."})


def _validate_with_access_analyzer(policy_text):
    """Run IAM Access Analyzer ValidatePolicy and return structured findings."""
    try:
        findings = []
        next_token = None
        while True:
            kwargs = {
                "policyType": "IDENTITY_POLICY",
                "policyDocument": policy_text,
            }
            if next_token:
                kwargs["nextToken"] = next_token
            response = aa_client.validate_policy(**kwargs)
            for f in response.get("findings", []):
                finding = {
                    "type": f.get("findingType", ""),
                    "issueCode": f.get("issueCode", ""),
                    "details": f.get("findingDetails", ""),
                    "learnMoreLink": f.get("learnMoreLink", ""),
                }
                locations = f.get("locations", [])
                if locations:
                    path_parts = []
                    for part in locations[0].get("path", []):
                        if "value" in part:
                            path_parts.append(part["value"])
                        elif "index" in part:
                            path_parts.append(f"[{part['index']}]")
                    finding["path"] = ".".join(path_parts).replace(".[", "[")
                findings.append(finding)
            next_token = response.get("nextToken")
            if not next_token:
                break
        return findings
    except Exception:
        logger.exception("Access Analyzer validation failed")
        return []


def _write_audit(request_id, policy, lang, analysis, duration_ms):
    try:
        table.put_item(
            Item={
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "policy": policy[:10000],
                "language": lang,
                "analysis": analysis[:10000],
                "duration_ms": duration_ms,
            }
        )
    except Exception:
        logger.exception("Failed to write audit record")


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
        },
        "body": json.dumps(body),
    }

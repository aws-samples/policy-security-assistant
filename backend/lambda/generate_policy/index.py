"""Policy Security Assistant — Policy Generator Lambda handler.

Generates IAM policies from natural language descriptions using
Amazon Bedrock Claude Sonnet 4.5 (Messages API).
Supports multi-turn conversation for iterative refinement.
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
MAX_HISTORY_MESSAGES = 20  # cap conversation length

ORIGIN_HEADER = os.environ.get("ORIGIN_VERIFY_HEADER", "")
ORIGIN_SECRET = os.environ.get("ORIGIN_VERIFY_SECRET", "")


def _verify_origin(event):
    if not ORIGIN_SECRET:
        return True
    headers = event.get("headers", {}) or {}
    return headers.get(ORIGIN_HEADER) == ORIGIN_SECRET

SYSTEM_PROMPT = """You are an AWS IAM security expert that generates IAM policies from natural language descriptions.
This is a multi-turn conversation. The user may refine their request across multiple messages.

Guidelines:
1. Generate policies that follow the principle of least privilege.
2. NEVER use wildcard (*) for actions. Always specify explicit actions.
3. For resources, accept reasonable scoping such as:
   - Tag-based conditions (e.g., ec2:ResourceTag/Team = DevOps)
   - Region restrictions via conditions
   - Resource-type patterns (e.g., arn:aws:ec2:us-east-1:123456789012:instance/*)
     BUT only when combined with at least one condition (tag, region, time, IP, MFA).
   - Specific ARNs when provided.
   Resource-type wildcards WITHOUT any conditions are not acceptable for write/modify actions.
4. Separate read-only actions (Describe*, List*, Get*) into their own statement.
   These actions often require Resource "*" which is correct and expected.
   Write/modify/delete actions MUST have scoped resources.
5. Only reject a request (safe=false) if it is genuinely too broad with no way to scope it.
6. Include conditions where the user mentions them (region, time, IP, MFA, tags).
   When the user specifies a region by name, map it to the correct AWS region code.
7. Use the account ID placeholder 123456789012 when an account ID is needed.
8. Add brief inline comments (using Sid) explaining each statement's purpose.

When the user refines a previous request (e.g., "add a region condition", "also allow S3 read"),
update the previously generated policy accordingly and return the complete updated policy.

Your response MUST be a valid JSON object with this structure:
- If the request is specific enough to generate a safe policy:
  {"safe": true, "policy": <the IAM policy JSON object>, "explanation": "<markdown explanation>"}
- If the request is genuinely too broad or you need clarification:
  {"safe": false, "message": "<markdown explanation with suggestions>"}

The "explanation" and "message" fields MUST use markdown formatting.
Always respond with valid JSON only. No markdown wrapping, no code blocks around the JSON."""

LANG_MAP = {"es": "Spanish", "pt": "Portuguese", "en": "English"}


def lambda_handler(event, context):
    request_id = str(uuid.uuid4())
    start_time = time.time()

    if not _verify_origin(event):
        return _response(403, {"error": "Forbidden"})

    try:
        body = json.loads(event.get("body", "{}"))
        description = body.get("description", "")
        lang = body.get("lang", "en")
        history = body.get("messages", [])  # previous conversation turns

        if not description or not description.strip():
            return _response(400, {"error": "Description is required."})

        language = LANG_MAP.get(lang, "English")

        # Build messages array from history + new message
        messages = []
        for msg in history[-MAX_HISTORY_MESSAGES:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Add the new user message
        user_message = (
            f"Generate or update the IAM policy for the following requirement. "
            f"Respond in {language}.\n\nRequirement: {description}"
        ) if not messages else description  # first turn gets the full prompt, follow-ups are direct

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
        raw_text = result["content"][0]["text"]

        # Strip markdown code fences if Bedrock wrapped the JSON
        clean_text = raw_text.strip()
        if clean_text.startswith("```"):
            first_newline = clean_text.index("\n")
            clean_text = clean_text[first_newline + 1:]
            if clean_text.rstrip().endswith("```"):
                clean_text = clean_text.rstrip()[:-3].rstrip()

        try:
            parsed = json.loads(clean_text)
        except json.JSONDecodeError:
            parsed = {"safe": False, "message": raw_text}

        duration_ms = int((time.time() - start_time) * 1000)

        # Run Access Analyzer on generated policy
        aa_findings = []
        if parsed.get("safe") and parsed.get("policy"):
            policy_json = json.dumps(parsed["policy"]) if isinstance(parsed["policy"], dict) else parsed["policy"]
            aa_findings = _validate_with_access_analyzer(policy_json)

        _write_audit(request_id, description, lang, raw_text, duration_ms, parsed.get("safe", False))

        logger.info("Policy generated", extra={
            "request_id": request_id, "lang": lang,
            "duration_ms": duration_ms, "safe": parsed.get("safe"),
        })

        return _response(200, {**parsed, "request_id": request_id, "raw_assistant": raw_text, "aa_findings": aa_findings})

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


def _write_audit(request_id, description, lang, response_text, duration_ms, safe):
    try:
        table.put_item(
            Item={
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "generate",
                "description": description[:10000],
                "language": lang,
                "response": response_text[:10000],
                "duration_ms": duration_ms,
                "safe": safe,
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

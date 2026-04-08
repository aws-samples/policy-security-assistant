#!/usr/bin/env python3
"""CDK app entry point for Policy Security Assistant v2."""

import aws_cdk as cdk

from stacks.security_assistant_stack import SecurityAssistantStack

app = cdk.App()
SecurityAssistantStack(app, "SecurityAssistantV2")
app.synth()

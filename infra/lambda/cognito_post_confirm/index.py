"""Cognito PostConfirmation trigger.

Fires after a user confirms their email during self-signup. Reads the
``custom:signup_role`` attribute they selected on the signup form and adds
them to the matching Cognito group.

Self-signup is restricted to ``donor`` and ``patient`` roles. Admin and
coordinator accounts are admin-created via the AWS console / CLI.

Result event shape (we return it unchanged):
    https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-post-confirmation.html
"""

from __future__ import annotations

import os

import boto3

ALLOWED_SELF_SIGNUP_ROLES = {"donor", "patient"}


def lambda_handler(event, context):
    trigger = event.get("triggerSource", "")
    if trigger != "PostConfirmation_ConfirmSignUp":
        # Other triggers like ForgotPassword should pass through untouched
        return event

    attributes = event.get("request", {}).get("userAttributes", {}) or {}
    role = (attributes.get("custom:signup_role") or "").strip().lower()

    if role not in ALLOWED_SELF_SIGNUP_ROLES:
        print(f"signup_role missing or not allowed: {role!r}; no group assignment")
        return event

    user_pool_id = event.get("userPoolId") or os.environ.get("USER_POOL_ID", "")
    username = event.get("userName") or attributes.get("sub", "")
    if not user_pool_id or not username:
        print(f"missing pool or user: pool={user_pool_id!r}, user={username!r}")
        return event

    client = boto3.client("cognito-idp", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    try:
        client.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=username,
            GroupName=role,
        )
        print(f"added {username} to {role} group")
    except Exception as exc:
        # Don't block signup — coordinator can fix manually
        print(f"failed to add {username} to {role}: {exc}")

    return event

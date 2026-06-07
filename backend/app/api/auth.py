"""E14 — Cognito auth endpoints.

  GET /auth/me        — return the current user's identity (JWT-protected)
  GET /auth/config    — public — returns Cognito client config so the
                        frontend knows where the hosted UI lives
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from app.integrations.cognito_auth import (
    AuthenticatedUser,
    require_authenticated_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", summary="E14: who am I (JWT-protected)")
def me(user: AuthenticatedUser = Depends(require_authenticated_user)) -> dict:
    return {
        "sub": user.sub,
        "email": user.email,
        "is_anonymous": user.is_anonymous,
    }


@router.get("/config", summary="Public: Cognito client config for the frontend")
def cognito_config() -> dict:
    pool_id = os.environ.get("COGNITO_USER_POOL_ID", "")
    region = os.environ.get("AWS_REGION", "us-east-1")
    return {
        "enabled": bool(pool_id),
        "user_pool_id": pool_id,
        "client_id": os.environ.get("COGNITO_CLIENT_ID", ""),
        "region": region,
        "hosted_ui_domain": os.environ.get("COGNITO_HOSTED_UI_DOMAIN", ""),
        "login_url": (
            f"https://{os.environ.get('COGNITO_HOSTED_UI_DOMAIN', '')}/login"
            f"?client_id={os.environ.get('COGNITO_CLIENT_ID', '')}"
            f"&response_type=code&scope=openid+email+profile"
            f"&redirect_uri={os.environ.get('COGNITO_REDIRECT_URI', 'https://bridge-os.click/login/callback')}"
        ) if pool_id else "",
    }

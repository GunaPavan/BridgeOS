"""E14 — Cognito JWT validation.

Verifies the ID token a Cognito user gets back from the hosted UI flow.
Used as a FastAPI dependency on routes that should require login.

Algorithm:
  1. Fetch the User Pool's JWKS (public keys) once and cache it
  2. Decode the JWT header → find the `kid` (key id)
  3. Look up the public key with that `kid`
  4. Verify the signature, expiry, audience, and issuer

When `COGNITO_USER_POOL_ID` isn't set (local dev), the dependency
short-circuits and returns a fake "anonymous" user so tests + dev work
without Cognito. Production paths gate on the env var.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)

# Cache: (jwks_dict, fetched_at)
_jwks_cache: tuple[dict, float] | None = None
_JWKS_TTL_SECONDS = 3600


@dataclass(frozen=True)
class AuthenticatedUser:
    """Subset of Cognito claims we care about."""

    sub: str  # Cognito user id (UUID)
    email: str
    groups: tuple[str, ...] = ()  # cognito:groups membership
    linked_id: str = ""           # custom:linked_id — donor.id or patient.id
    is_anonymous: bool = False

    def has_role(self, *roles: str) -> bool:
        return any(r in self.groups for r in roles)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.groups

    @property
    def is_coordinator(self) -> bool:
        return self.is_admin or "coordinator" in self.groups


def _enabled() -> bool:
    return bool(os.environ.get("COGNITO_USER_POOL_ID"))


def _user_pool_id() -> str:
    return os.environ.get("COGNITO_USER_POOL_ID", "")


def _client_id() -> str:
    return os.environ.get("COGNITO_CLIENT_ID", "")


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1")


def _jwks_url() -> str:
    pool = _user_pool_id()
    region = _region()
    return f"https://cognito-idp.{region}.amazonaws.com/{pool}/.well-known/jwks.json"


def _issuer() -> str:
    pool = _user_pool_id()
    region = _region()
    return f"https://cognito-idp.{region}.amazonaws.com/{pool}"


def _get_jwks() -> dict:
    """Fetch + cache the User Pool's JWKS."""
    global _jwks_cache
    now = time.time()
    if _jwks_cache and now - _jwks_cache[1] < _JWKS_TTL_SECONDS:
        return _jwks_cache[0]
    import urllib.request

    with urllib.request.urlopen(_jwks_url(), timeout=8) as resp:
        import json
        keys = json.loads(resp.read())
    _jwks_cache = (keys, now)
    return keys


def verify_jwt(token: str) -> AuthenticatedUser:
    """Verify a Cognito ID/access token. Raises HTTPException on failure."""
    try:
        from jose import jwt, JWTError  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("python-jose not installed; cannot verify JWT")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT validation library missing",
        )

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Bad JWT header: {exc}")

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="JWT missing kid")

    jwks = _get_jwks()
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        # Force a JWKS refresh once in case of key rotation
        global _jwks_cache
        _jwks_cache = None
        jwks = _get_jwks()
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        raise HTTPException(status_code=401, detail="No matching JWKS key")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[unverified_header.get("alg", "RS256")],
            audience=_client_id() or None,
            issuer=_issuer(),
            options={"verify_aud": bool(_client_id())},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"JWT invalid: {exc}")

    groups_claim = claims.get("cognito:groups", []) or []
    return AuthenticatedUser(
        sub=claims.get("sub", ""),
        email=claims.get("email", ""),
        groups=tuple(groups_claim) if isinstance(groups_claim, list) else (groups_claim,),
        linked_id=claims.get("custom:linked_id", "") or "",
        is_anonymous=False,
    )


def require_authenticated_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> AuthenticatedUser:
    """FastAPI dependency: require a valid Cognito JWT.

    In local dev (no COGNITO_USER_POOL_ID), returns an anonymous user so
    routes work without Cognito.
    """
    if not _enabled():
        # Local dev: pretend the user is an admin so all routes work
        return AuthenticatedUser(
            sub="local-dev", email="dev@local",
            groups=("admin",), is_anonymous=True,
        )

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_jwt(credentials.credentials)


# ---------------------------------------------------------------------------
# Role-based dependencies — use these on route declarations
# ---------------------------------------------------------------------------


def require_role(*allowed_roles: str):
    """Build a FastAPI dependency that requires the user to be in one of
    ``allowed_roles``.

    Usage:
        @router.post("/...")
        def my_endpoint(user = Depends(require_role("admin", "coordinator"))):
            ...
    """

    def _dep(
        user: AuthenticatedUser = Depends(require_authenticated_user),
    ) -> AuthenticatedUser:
        if not user.has_role(*allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"requires one of: {', '.join(allowed_roles)}; "
                    f"you have: {', '.join(user.groups) or '(none)'}"
                ),
            )
        return user

    return _dep


def require_admin(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    """Shortcut for admin-only routes."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )
    return user


def require_coordinator(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    """Coordinator or admin — covers most operational endpoints."""
    if not user.is_coordinator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="coordinator role required",
        )
    return user


def require_donor_with_link(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    """Donor accessing their own data. Requires a linked donor_id."""
    if not user.has_role("donor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="donor role required",
        )
    if not user.linked_id and not user.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="donor account not linked to a donor record",
        )
    return user


def require_patient_with_link(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    """Caregiver / patient accessing their own data. Requires a linked patient_id."""
    if not user.has_role("patient"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="patient role required",
        )
    if not user.linked_id and not user.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="patient account not linked to a patient record",
        )
    return user

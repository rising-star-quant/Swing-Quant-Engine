from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
import jwt

from schemas import JWTTokenPayload, UserRole


class SecurityViolationError(PermissionError):
    """Raised when authentication, token signature, or tenant isolation fails."""


_ARGON2_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


class MultiTenantSecurityService:
    """
    Provides cryptographic password hashing via Argon2id (argon2-cffi),
    stateless HS256 JWT generation/verification via PyJWT, and strict
    Multi-Tenant Role-Based Access Control (RBAC) enforcement.
    """

    def __init__(self, jwt_secret_key: str, token_ttl_minutes: int = 60) -> None:
        if len(jwt_secret_key) < 32:
            raise ValueError("jwt_secret_key must be at least 32 characters long.")
        self._secret_key = jwt_secret_key
        self._token_ttl_seconds = token_ttl_minutes * 60

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Hashes a plaintext password using Argon2id."""
        if len(plain_password) < 12:
            raise ValueError("Password must be at least 12 characters long.")
        return _ARGON2_HASHER.hash(plain_password)

    @staticmethod
    def verify_password(plain_password: str, stored_hash: str) -> bool:
        """Verifies a plaintext password against an Argon2id hash in constant time."""
        try:
            return bool(_ARGON2_HASHER.verify(stored_hash, plain_password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def issue_jwt(self, user_id: UUID, role: UserRole) -> str:
        """Issues a signed HS256 JWT containing user_id (sub) and role claims."""
        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
        payload_model = JWTTokenPayload(
            sub=user_id,
            role=role,
            iat=now_ts,
            exp=now_ts + self._token_ttl_seconds,
        )
        claims: Dict[str, Any] = {
            "sub": str(payload_model.sub),
            "role": payload_model.role.value,
            "iat": payload_model.iat,
            "exp": payload_model.exp,
        }
        return jwt.encode(claims, self._secret_key, algorithm="HS256")

    def verify_jwt(self, token: str) -> JWTTokenPayload:
        """Verifies an HS256 JWT signature and expiration timestamp."""
        try:
            decoded: Dict[str, Any] = jwt.decode(
                token,
                self._secret_key,
                algorithms=["HS256"],
                options={"require": ["sub", "role", "iat", "exp"]},
            )
            return JWTTokenPayload.model_validate(decoded)
        except jwt.ExpiredSignatureError as exc:
            raise SecurityViolationError("JWT token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise SecurityViolationError(f"Invalid JWT token: {exc}") from exc

    @staticmethod
    def assert_tenant_portfolio_access(
        token_payload: JWTTokenPayload,
        target_portfolio_owner_id: UUID,
        require_write: bool = False,
    ) -> None:
        """
        Enforces strict Multi-Tenant Isolation:
        - A user can NEVER access or mutate a portfolio owned by another user_id.
        - VIEWER role is strictly blocked from write/mutation operations.
        """
        if token_payload.sub != target_portfolio_owner_id:
            raise SecurityViolationError(
                f"CROSS-TENANT ACCESS DENIED: Authenticated user ({token_payload.sub}) "
                f"cannot access portfolio owned by ({target_portfolio_owner_id})."
            )
        if require_write and token_payload.role == UserRole.VIEWER:
            raise SecurityViolationError(
                "RBAC VIOLATION: VIEWER role is prohibited from mutating portfolio state."
            )

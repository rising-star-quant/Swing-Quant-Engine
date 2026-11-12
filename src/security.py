from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Sequence
from uuid import UUID

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt
from pydantic import ValidationError

try:
    from src.config import SystemSettings, get_settings
    from src.schemas import JWTTokenPayload, UserIdentitySchema, UserRole
except ImportError:
    from config import SystemSettings, get_settings  # type: ignore[no-redef]
    from schemas import JWTTokenPayload, UserIdentitySchema, UserRole  # type: ignore[no-redef]


# =============================================================================
# 1. CUSTOM DOMAIN SECURITY EXCEPTIONS
# =============================================================================


class SecurityError(Exception):
    """Base exception for all authentication and authorization failures."""


class AuthenticationError(SecurityError):
    """Raised on invalid credentials, expired/malformed JWT tokens, or inactive user accounts."""


class AuthorizationError(SecurityError):
    """Raised on RBAC permission violations or cross-tenant isolation breaches."""


class SecurityViolationError(SecurityError, PermissionError):
    """Raised when authentication, token signature, or tenant isolation fails."""


# =============================================================================
# 2. PASSWORD HASHING & VERIFICATION (ARGON2ID)
# =============================================================================


class PasswordManager:
    """
    Encapsulates memory-hard Argon2id password hashing and constant-time verification
    configured with OWASP-recommended parameters.
    """

    def __init__(
        self,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
        hash_len: int = 32,
        salt_len: int = 16,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=Type.ID,
        )

    def hash_password(self, plain_password: str) -> str:
        """
        Validates password policy and returns an Argon2id encoded hash string.
        """
        if not isinstance(plain_password, str) or not plain_password or len(plain_password) < 10:
            raise ValueError("Password must be a non-empty string of at least 10 characters.")
        return self._hasher.hash(plain_password)

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        """
        Safely verifies a plaintext password against an Argon2id hash in constant time.
        Never leaks underlying cryptographic exceptions.
        """
        if not plain_password or not password_hash:
            return False
        try:
            return bool(self._hasher.verify(password_hash, plain_password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        """
        Checks whether an existing Argon2id password hash requires rehashing
        due to updated security parameters.
        """
        if not password_hash:
            return True
        try:
            return bool(self._hasher.check_needs_rehash(password_hash))
        except (InvalidHashError, VerificationError):
            return True


# =============================================================================
# 3. STATELESS JWT TOKEN MANAGEMENT (PYJWT)
# =============================================================================


class JWTManager:
    """
    Stateless JWT token issuer and verifier enforcing cryptographic key strength,
    account activity status, and strict claim validation.
    """

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()
        secret_key = self.settings.jwt_secret_key

        if len(secret_key) < 32:
            raise SecurityError("JWT secret key must be at least 32 characters long.")

        if self.settings.environment == "production" and "CHANGE_ME" in secret_key.upper():
            raise SecurityError(
                "CRITICAL SECURITY VIOLATION: Insecure placeholder JWT secret key ('CHANGE_ME') "
                "is strictly prohibited in production environment."
            )

    def create_access_token(
        self,
        user: UserIdentitySchema,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Creates and signs a stateless JWT access token for an active tenant user.
        """
        if not user.is_active:
            raise AuthenticationError("Inactive user account")

        now_utc = datetime.now(timezone.utc)
        iat = int(now_utc.timestamp())

        if expires_delta is not None:
            exp = int((now_utc + expires_delta).timestamp())
        else:
            exp = int(
                (now_utc + timedelta(minutes=self.settings.jwt_access_token_expire_minutes)).timestamp()
            )

        payload = JWTTokenPayload(
            sub=user.user_id,
            role=user.role,
            exp=exp,
            iat=iat,
        )

        claims: Dict[str, Any] = {
            "sub": str(payload.sub),
            "role": payload.role.value,
            "exp": payload.exp,
            "iat": payload.iat,
        }

        return jwt.encode(
            claims,
            self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
        )

    def decode_and_verify_token(self, token: str) -> JWTTokenPayload:
        """
        Decodes and cryptographically verifies a JWT access token, returning
        a validated JWTTokenPayload contract.
        """
        if not token or not isinstance(token, str):
            raise AuthenticationError("Missing or non-string JWT token.")

        try:
            decoded: Dict[str, Any] = jwt.decode(
                token,
                self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_algorithm],
                options={"require": ["sub", "role", "exp", "iat"]},
            )
            return JWTTokenPayload.model_validate(decoded)
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("JWT access token has expired.") from exc
        except (jwt.InvalidTokenError, ValidationError, ValueError) as exc:
            raise AuthenticationError(f"Invalid JWT access token: {exc}") from exc


# =============================================================================
# 4. MULTI-TENANT RBAC & TENANT ISOLATION GUARD
# =============================================================================


class TenantSecurityGuard:
    """
    Defense-in-depth Multi-Tenant Role-Based Access Control (RBAC) and
    tenant boundary enforcement aligned with Phase 2 PostgreSQL RLS policies.
    """

    @staticmethod
    def require_role(
        token_payload: JWTTokenPayload,
        allowed_roles: Sequence[UserRole],
    ) -> None:
        """
        Enforces that the authenticated user's role is within the permitted role set.
        """
        if token_payload.role not in allowed_roles:
            allowed_str = ", ".join(r.value for r in allowed_roles)
            raise AuthorizationError(
                f"RBAC permission denied: role '{token_payload.role.value}' is not in allowed roles [{allowed_str}]."
            )

    @staticmethod
    def require_admin_worker(token_payload: JWTTokenPayload) -> None:
        """
        Enforces UserRole.ADMIN for triggering headless market scans or mutating
        the global index_registry.
        """
        if token_payload.role != UserRole.ADMIN:
            raise AuthorizationError(
                f"RBAC permission denied: ADMIN role required for global pipeline or index registry operations "
                f"(got '{token_payload.role.value}')."
            )

    @staticmethod
    def enforce_tenant_access(
        token_payload: JWTTokenPayload,
        resource_owner_id: UUID,
        allow_admin_override: bool = False,
    ) -> None:
        """
        Enforces strict tenant ownership isolation, preventing cross-tenant access
        unless explicit admin override is permitted and the caller holds UserRole.ADMIN.
        """
        if token_payload.sub == resource_owner_id:
            return

        if allow_admin_override and token_payload.role == UserRole.ADMIN:
            return

        raise AuthorizationError(
            f"Cross-tenant isolation breach: subject '{token_payload.sub}' is not authorized "
            f"to access resource owned by '{resource_owner_id}'."
        )

    @staticmethod
    def generate_supabase_rls_claims(token_payload: JWTTokenPayload) -> Dict[str, str]:
        """
        Generates PostgreSQL / Supabase session context claims for seamless
        Phase 2 Row-Level Security (RLS) binding.
        """
        return {
            "request.jwt.claim.sub": str(token_payload.sub),
            "request.jwt.claim.role": token_payload.role.value,
        }


# =============================================================================
# 5. UNIFIED MULTI-TENANT SECURITY SERVICE FACADE
# =============================================================================


class MultiTenantSecurityService:
    """
    High-level facade combining Argon2id password management, PyJWT signing,
    and Multi-Tenant portfolio access guards.
    """

    def __init__(self, jwt_secret_key: str, token_ttl_minutes: int = 60) -> None:
        if len(jwt_secret_key) < 32:
            raise ValueError("jwt_secret_key must be at least 32 characters long.")
        self._secret_key = jwt_secret_key
        self._token_ttl_seconds = token_ttl_minutes * 60
        self._password_manager = PasswordManager()

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Hashes a plaintext password using Argon2id."""
        return PasswordManager().hash_password(plain_password)

    @staticmethod
    def verify_password(plain_password: str, stored_hash: str) -> bool:
        """Verifies a plaintext password against an Argon2id hash in constant time."""
        return PasswordManager().verify_password(plain_password, stored_hash)

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
        except (jwt.InvalidTokenError, ValidationError, ValueError) as exc:
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

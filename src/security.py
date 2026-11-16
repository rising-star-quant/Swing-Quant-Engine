from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import hmac
import os
import threading
import time
from typing import Any, Deque, Dict, Optional, Sequence, Tuple
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


class RateLimitExceededError(SecurityError):
    """Raised when an IP exceeds the sliding-window login failure threshold (HTTP 429)."""

    def __init__(self, message: str, retry_after_seconds: int = 900) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SchedulerAuthError(SecurityError):
    """Raised when X-Sirix-Scheduler-Token fails constant-time verification (HTTP 403)."""


SESSION_COOKIE_NAME: str = "sirix_session"
SESSION_TTL_SECONDS: int = 86_400
LOGIN_MAX_ATTEMPTS: int = 5
LOGIN_WINDOW_SECONDS: int = 900


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


# =============================================================================
# 6. F01 SINGLE-ORIGIN COOKIE AUTH, RATE LIMITING & SCHEDULER GUARD
# =============================================================================


class SlidingWindowLoginRateLimiter:
    """
    Thread-safe in-memory per-IP sliding-window rate limiter enforcing a maximum
    of `max_attempts` failed login attempts per `window_seconds` (default: 5 / 15 min).
    """

    def __init__(
        self,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
        window_seconds: int = LOGIN_WINDOW_SECONDS,
        clock: Any = time.monotonic,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer.")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be a positive integer.")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._attempts: Dict[str, Deque[float]] = {}

    def _prune_locked(self, key: str, now_ts: float) -> Deque[float]:
        bucket = self._attempts.get(key)
        if bucket is None:
            bucket = deque()
            self._attempts[key] = bucket
        cutoff = now_ts - float(self.window_seconds)
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if not bucket:
            self._attempts.pop(key, None)
        return bucket

    def check_allowed(self, client_ip: str) -> None:
        """
        Verifies whether `client_ip` is below the failed-attempt ceiling.
        Raises `RateLimitExceededError` (HTTP 429) if throttled.
        """
        key = (client_ip or "unknown").strip() or "unknown"
        now_ts = float(self._clock())
        with self._lock:
            bucket = self._prune_locked(key, now_ts)
            if len(bucket) >= self.max_attempts:
                oldest = bucket[0]
                retry_after = max(1, int(self.window_seconds - (now_ts - oldest)))
                raise RateLimitExceededError(
                    "Too many failed authentication attempts. Please retry after cooldown.",
                    retry_after_seconds=retry_after,
                )

    def record_failure(self, client_ip: str) -> int:
        """
        Records a failed authentication timestamp for `client_ip` and returns the
        current failure count inside the active sliding window.
        """
        key = (client_ip or "unknown").strip() or "unknown"
        now_ts = float(self._clock())
        with self._lock:
            bucket = self._attempts.setdefault(key, deque())
            cutoff = now_ts - float(self.window_seconds)
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            bucket.append(now_ts)
            return len(bucket)

    def reset(self, client_ip: str) -> None:
        """Clears failed login history for `client_ip` after a successful login."""
        key = (client_ip or "unknown").strip() or "unknown"
        with self._lock:
            self._attempts.pop(key, None)

    def remaining_attempts(self, client_ip: str) -> int:
        """Returns remaining login attempts available for `client_ip` in the current window."""
        key = (client_ip or "unknown").strip() or "unknown"
        now_ts = float(self._clock())
        with self._lock:
            bucket = self._prune_locked(key, now_ts)
            return max(0, self.max_attempts - len(bucket))


class SingleOriginCookieSessionManager:
    """
    Manages F01 Single-Origin cookie authentication (`sirix_session`) backed by
    Argon2id credential verification (`ADMIN_PASSWORD_HASH`) and HS256 JWT tokens
    with 24-hour expiration (`HttpOnly; Secure; SameSite=Strict`).
    """

    DEFAULT_ADMIN_SUBJECT = UUID("00000000-0000-4000-8000-000000000001")

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        admin_username: Optional[str] = None,
        admin_password_hash: Optional[str] = None,
        jwt_secret_key: Optional[str] = None,
        session_ttl_seconds: int = SESSION_TTL_SECONDS,
    ) -> None:
        self.settings: SystemSettings = settings or get_settings()
        self.password_manager = PasswordManager()
        self.session_ttl_seconds = session_ttl_seconds
        self.cookie_name = SESSION_COOKIE_NAME

        self.admin_username = (
            admin_username
            if admin_username is not None
            else os.environ.get("ADMIN_USERNAME", "admin")
        ).strip() or "admin"

        env_hash = (
            admin_password_hash
            if admin_password_hash is not None
            else os.environ.get("ADMIN_PASSWORD_HASH", "")
        ).strip()

        if not env_hash and self.settings.environment != "production":
            dev_plain = os.environ.get("SIRIX_DEV_ADMIN_PASSWORD", "sirix-sandbox-admin")
            env_hash = self.password_manager.hash_password(dev_plain)
        self._admin_password_hash: str = env_hash

        resolved_secret = (
            jwt_secret_key
            or os.environ.get("JWT_SECRET_KEY", "").strip()
            or self.settings.jwt_secret_key
        )
        if len(resolved_secret) < 32:
            raise SecurityError("JWT secret key must be at least 32 characters long.")
        if self.settings.environment == "production" and "CHANGE_ME" in resolved_secret.upper():
            raise SecurityError(
                "CRITICAL SECURITY VIOLATION: Insecure placeholder JWT secret key is prohibited in production."
            )
        self._jwt_secret_key = resolved_secret

    def authenticate_credentials(self, username: str, password: str) -> Tuple[str, datetime]:
        """
        Verifies username + password in constant time against `ADMIN_USERNAME` and
        Argon2id `ADMIN_PASSWORD_HASH`. Returns `(jwt_token, expires_at_utc)`.
        """
        clean_user = (username or "").strip().lower()
        expected_user = self.admin_username.strip().lower()
        user_matches = hmac.compare_digest(clean_user.encode("utf-8"), expected_user.encode("utf-8"))

        if not self._admin_password_hash:
            raise AuthenticationError("Authentication credentials rejected.")

        password_matches = self.password_manager.verify_password(
            password or "",
            self._admin_password_hash,
        )

        if not (user_matches and password_matches):
            raise AuthenticationError("Invalid credentials provided.")

        return self.issue_session_token(username=self.admin_username)

    def issue_session_token(
        self,
        username: Optional[str] = None,
        role: UserRole = UserRole.ADMIN,
    ) -> Tuple[str, datetime]:
        """Issues an HS256 JWT token valid for `session_ttl_seconds` (24 hours)."""
        now_utc = datetime.now(timezone.utc)
        expires_at_utc = now_utc + timedelta(seconds=self.session_ttl_seconds)
        iat = int(now_utc.timestamp())
        exp = int(expires_at_utc.timestamp())

        payload = JWTTokenPayload(
            sub=self.DEFAULT_ADMIN_SUBJECT,
            role=role,
            exp=exp,
            iat=iat,
        )
        claims: Dict[str, Any] = {
            "sub": str(payload.sub),
            "role": payload.role.value,
            "username": (username or self.admin_username),
            "exp": payload.exp,
            "iat": payload.iat,
        }
        token = jwt.encode(claims, self._jwt_secret_key, algorithm="HS256")
        return token, expires_at_utc

    def verify_session_cookie(self, token: Optional[str]) -> Dict[str, Any]:
        """
        Cryptographically verifies the `sirix_session` cookie JWT and returns
        validated session metadata (`sub`, `username`, `role`, `expires_at_utc`).
        """
        if not token or not isinstance(token, str):
            raise AuthenticationError("Missing or empty session cookie.")

        try:
            decoded: Dict[str, Any] = jwt.decode(
                token,
                self._jwt_secret_key,
                algorithms=["HS256"],
                options={"require": ["sub", "role", "exp", "iat"]},
            )
            validated = JWTTokenPayload.model_validate(decoded)
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Session cookie has expired.") from exc
        except (jwt.InvalidTokenError, ValidationError, ValueError) as exc:
            raise AuthenticationError(f"Invalid session cookie: {exc}") from exc

        return {
            "sub": str(validated.sub),
            "role": validated.role.value,
            "username": str(decoded.get("username") or self.admin_username),
            "expires_at_utc": datetime.fromtimestamp(validated.exp, tz=timezone.utc),
        }

    def cookie_attributes(self) -> Dict[str, Any]:
        """Returns strict single-origin cookie flags (`HttpOnly; Secure; SameSite=Strict`)."""
        secure_flag = os.environ.get("SIRIX_COOKIE_SECURE", "true").strip().lower() != "false"
        return {
            "key": self.cookie_name,
            "httponly": True,
            "secure": secure_flag,
            "samesite": "strict",
            "max_age": self.session_ttl_seconds,
            "path": "/",
        }


def verify_internal_scheduler_token(
    provided_token: Optional[str],
    expected_token: Optional[str] = None,
) -> None:
    """
    Validates `X-Sirix-Scheduler-Token` in constant time against `INTERNAL_SCHEDULER_TOKEN`.
    Raises `SchedulerAuthError` (HTTP 403 Forbidden) on missing, unconfigured, or mismatched tokens.
    """
    configured = (
        expected_token
        if expected_token is not None
        else os.environ.get("INTERNAL_SCHEDULER_TOKEN", "")
    ).strip()
    supplied = (provided_token or "").strip()

    if not configured or not supplied:
        raise SchedulerAuthError("Forbidden: Missing or unconfigured internal scheduler token.")

    if not hmac.compare_digest(supplied.encode("utf-8"), configured.encode("utf-8")):
        raise SchedulerAuthError("Forbidden: Invalid internal scheduler token.")


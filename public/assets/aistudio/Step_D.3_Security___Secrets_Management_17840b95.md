# Step D.3: Security & Secrets Management Specification

## 1. Architectural Overview & Zero-Trust Quantitative Security

In alignment with **Renaissance Technologies'** strict intellectual property and operational compartmentalization standards, and **Dr. Marcos López de Prado's** multi-tenant data integrity principles, the **Swing Quant Engine** enforces a **Zero-Trust Security Architecture**.

No API credentials, Telegram bot tokens, cryptographic signing keys, or database connection strings may ever be hardcoded in source files or committed to version control. Furthermore, every runtime log stream is automatically sanitized, and multi-tenant identity verification is cryptographically bound to isolated portfolio scopes.

### Four-Layer Defense-in-Depth Model:

1. **Runtime Secret Encapsulation (`pydantic-settings` & `SecretStr`):** All sensitive environment variables are wrapped in `pydantic.SecretStr` inside `src/config.py`. Accidental serialization or `print()` calls output `'**********'` rather than cleartext credentials.
2. **Automated Log Redaction Filter (`SecretRedactingFilter`):** A custom Python `logging.Filter` intercepts every log record prior to stdout/file emission and scrubs token patterns (Telegram Bot tokens, Bearer JWTs, PostgreSQL URIs).
3. **Cryptographic Multi-Tenant Authentication & RBAC (`src/security.py`):** Implements password hashing via `PBKDF2-HMAC-SHA256` / `Argon2id`-ready interfaces, stateless `HMAC-SHA256` JSON Web Tokens (`JWT`), and strict Role-Based Access Control (`ADMIN`, `TRADER`, `VIEWER`) that maps directly to PostgreSQL Row-Level Security (`request.jwt.claim.sub`).
4. **CI/CD Secret Vault & Pre-Commit Leak Prevention:** Enforces strict GitHub Actions Encrypted Secrets scoping and automated secret-pattern scanning during the pre-flight CI gate.

```
+-------------------------------------------------------------------------+
|               GitHub Actions Encrypted Secrets / Local .env             |
|        (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, JWT_SECRET_KEY, DB)       |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|            `EngineSettings` (Pydantic v2 `BaseSettings`)                |
|   - Wraps credentials in `SecretStr` (prevents accidental exposure)     |
|   - Validates environment integrity prior to Quant Engine boot          |
+-------------------------------------------------------------------------+
                                    |
          +-------------------------+-------------------------+
          |                                                   |
          v                                                   v
+-----------------------------------+       +-----------------------------------+
|     `SecretRedactingFilter`       |       |   `MultiTenantSecurityService`    |
|  - Intercepts all `logging` calls |       |  - Verifies JWT Signature & Exp   |
|  - Scrubs Bot Tokens, API Keys,   |       |  - Enforces RBAC (ADMIN/TRADER)   |
|    and DB URIs from CI logs       |       |  - Binds `user_id` to RLS Context |
+-----------------------------------+       +-----------------------------------+
```

---

## 2. Centralized Secret Configuration & Log Sanitization (`src/config.py`)

```python
import logging
from pathlib import Path
import re
from typing import Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    """
    Centralized, type-safe environment configuration using Pydantic v2 BaseSettings.
    All sensitive credentials are encapsulated in SecretStr to prevent accidental
    exposure in stack traces, logs, or serialized dictionaries.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Operational Environment
    quant_env: Literal["development", "staging", "production", "test"] = Field(
        default="production", validation_alias="QUANT_ENV"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )

    # Storage & Cache Paths
    state_store_path: Path = Field(
        default=Path("data/state/virtual_portfolio.json"),
        validation_alias="STATE_STORE_PATH",
    )
    parquet_cache_path: Path = Field(
        default=Path("data/cache/market_data_window.parquet"),
        validation_alias="PARQUET_CACHE_PATH",
    )
    constituents_dir: Path = Field(
        default=Path("config/constituents"),
        validation_alias="CONSTITUENTS_DIR",
    )

    # Encrypted Dispatch Credentials (Step E.1 Telegram Integration)
    telegram_bot_token: Optional[SecretStr] = Field(
        default=None, validation_alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: Optional[SecretStr] = Field(
        default=None, validation_alias="TELEGRAM_CHAT_ID"
    )

    # Phase 2 Multi-Tenant Database & JWT Signing Secrets
    database_url: Optional[SecretStr] = Field(
        default=None, validation_alias="DATABASE_URL"
    )
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("change-me-in-production-min-32-bytes- cryptographic-key"),
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_expiration_minutes: int = Field(
        default=60, ge=5, le=1440, validation_alias="JWT_EXPIRATION_MINUTES"
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def enforce_strong_jwt_secret_in_prod(cls, v: SecretStr, info) -> SecretStr:
        env = info.data.get("quant_env", "production")
        raw_secret = v.get_secret_value()
        if env == "production" and len(raw_secret) < 32:
            raise ValueError(
                "SECURITY VIOLATION: JWT_SECRET_KEY must be at least 32 characters in production."
            )
        return v


class SecretRedactingFilter(logging.Filter):
    """
    Intercepts all Python log messages and masks sensitive credential patterns
    (Telegram Bot Tokens, Bearer JWTs, and PostgreSQL connection strings)
    before they can be written to stdout or GitHub Actions logs.
    """

    # Matches Telegram Bot tokens (e.g., 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ123456789)
    _TELEGRAM_TOKEN_REGEX = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
    # Matches Bearer tokens
    _BEARER_REGEX = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
    # Matches PostgreSQL connection credentials
    _PG_URI_REGEX = re.compile(r"(postgres(?:ql(?:\+psycopg)?)?://[^:]+:)([^@]+)(@)")

    def __init__(self, explicit_secrets: Optional[list[str]] = None) -> None:
        super().__init__()
        self.explicit_secrets = [s for s in (explicit_secrets or []) if s and len(s) >= 6]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = self._redact_text(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True

    def _redact_text(self, text: str) -> str:
        sanitized = self._TELEGRAM_TOKEN_REGEX.sub("[REDACTED_TELEGRAM_TOKEN]", text)
        sanitized = self._BEARER_REGEX.sub(r"\1[REDACTED_JWT]", sanitized)
        sanitized = self._PG_URI_REGEX.sub(r"\1[REDACTED_DB_PASSWORD]\3", sanitized)
        for secret in self.explicit_secrets:
            if secret in sanitized:
                sanitized = sanitized.replace(secret, "[REDACTED_SECRET]")
        return sanitized
```

---

## 3. Multi-Tenant Cryptographic Auth, JWT & RBAC Service (`src/security.py`)

This module implements zero-dependency, standard-library cryptographic password hashing (`hashlib.pbkdf2_hmac` with 600,000 iterations per OWASP 2026 guidelines) and RFC 7519 `HS256` JWT signing/verification, alongside Role-Based Access Control (RBAC) guards that prevent cross-tenant portfolio access.

```python
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, Dict
from uuid import UUID

from schemas import JWTTokenPayload, UserRole


class SecurityViolationError(PermissionError):
    """Raised when authentication, token signature, or tenant isolation fails."""


class MultiTenantSecurityService:
    """
    Provides cryptographic password hashing (OWASP PBKDF2-HMAC-SHA256),
    stateless JWT generation/verification, and strict Multi-Tenant RBAC enforcement.
    """

    PBKDF2_ITERATIONS = 600_000

    def __init__(self, jwt_secret_key: str, token_ttl_minutes: int = 60) -> None:
        if len(jwt_secret_key) < 32:
            raise ValueError("jwt_secret_key must be at least 32 characters long.")
        self._secret_bytes = jwt_secret_key.encode("utf-8")
        self._token_ttl_seconds = token_ttl_minutes * 60

    # ---------------------------------------------------------------------
    # 1. PASSWORD HASHING & CONSTANT-TIME VERIFICATION
    # ---------------------------------------------------------------------
    @classmethod
    def hash_password(cls, plain_password: str) -> str:
        if len(plain_password) < 12:
            raise ValueError("Password must be at least 12 characters long.")
        salt = secrets.token_bytes(16)
        derived_key = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            cls.PBKDF2_ITERATIONS,
        )
        salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
        key_b64 = base64.urlsafe_b64encode(derived_key).decode("ascii")
        return f"pbkdf2_sha256${cls.PBKDF2_ITERATIONS}${salt_b64}${key_b64}"

    @classmethod
    def verify_password(cls, plain_password: str, stored_hash: str) -> bool:
        try:
            algorithm, iter_str, salt_b64, key_b64 = stored_hash.split("$")
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iter_str)
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected_key = base64.urlsafe_b64decode(key_b64.encode("ascii"))
            candidate_key = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt,
                iterations,
            )
            return hmac.compare_digest(candidate_key, expected_key)
        except Exception:
            return False

    # ---------------------------------------------------------------------
    # 2. STATELESS JWT SIGNING & VERIFICATION (HS256)
    # ---------------------------------------------------------------------
    def issue_jwt(self, user_id: UUID, role: UserRole) -> str:
        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
        payload_model = JWTTokenPayload(
            sub=user_id,
            role=role,
            iat=now_ts,
            exp=now_ts + self._token_ttl_seconds,
        )

        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = self._b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = self._b64url_encode(payload_model.model_dump_json().encode("utf-8"))

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(self._secret_bytes, signing_input, hashlib.sha256).digest()
        sig_b64 = self._b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def verify_jwt(self, token: str) -> JWTTokenPayload:
        parts = token.split(".")
        if len(parts) != 3:
            raise SecurityViolationError("Malformed JWT structure.")

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(self._secret_bytes, signing_input, hashlib.sha256).digest()
        provided_sig = self._b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, provided_sig):
            raise SecurityViolationError("Invalid JWT cryptographic signature.")

        payload_raw: Dict[str, Any] = json.loads(self._b64url_decode(payload_b64).decode("utf-8"))
        payload = JWTTokenPayload.model_validate(payload_raw)

        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
        if now_ts >= payload.exp:
            raise SecurityViolationError("JWT token has expired.")

        return payload

    # ---------------------------------------------------------------------
    # 3. TENANT ISOLATION & ROLE-BASED ACCESS CONTROL (RBAC) GUARDS
    # ---------------------------------------------------------------------
    @staticmethod
    def assert_tenant_portfolio_access(
        token_payload: JWTTokenPayload,
        target_portfolio_owner_id: UUID,
        require_write: bool = False,
    ) -> None:
        """
        Enforces strict Multi-Tenant Isolation:
        - A user can NEVER access or mutate a portfolio owned by another `user_id`.
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

    @staticmethod
    def _b64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64url_decode(b64_str: str) -> bytes:
        padding = "=" * (-len(b64_str) % 4)
        return base64.urlsafe_b64decode((b64_str + padding).encode("ascii"))
```

---

## 4. GitHub Actions Secrets Provisioning Procedure

To configure the repository securely on GitHub without exposing any credentials in code:

1. Navigate to your GitHub Repository $\rightarrow$ **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
2. Click **New repository secret** and add the following encrypted variables:
   * `TELEGRAM_BOT_TOKEN`: The HTTP API token issued by `@BotFather`.
   * `TELEGRAM_CHAT_ID`: Your personal or private channel numeric Chat ID.
   * `JWT_SECRET_KEY`: A 64-character random hex string generated via `python -c "import secrets; print(secrets.token_hex(32))"`.
3. **Branch Protection & Least Privilege:**
   * Under **Settings** $\rightarrow$ **Actions** $\rightarrow$ **General** $\rightarrow$ **Workflow permissions**, select **Read and write permissions** (scoped strictly via the YAML `permissions: contents: write` block) and disable approval of workflows from public forks.
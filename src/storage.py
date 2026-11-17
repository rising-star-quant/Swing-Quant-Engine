from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading
import time
from typing import Any, Dict, Iterator, List, Literal, Optional, Sequence, Tuple
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import ValidationError

try:
    import psycopg  # type: ignore[import-not-found]
except ImportError:
    psycopg = None  # type: ignore[assignment]

try:
    from google.cloud import storage as gcs_storage  # type: ignore[import-not-found]
except ImportError:
    gcs_storage = None  # type: ignore[assignment]

try:
    from src.config import SystemSettings, get_settings, load_index_registry
    from src.schemas import (
        IndexConfigSchema,
        JWTTokenPayload,
        MultiTenantStateStoreSchema,
        VirtualPortfolioLedgerSchema,
    )
    from src.security import MultiTenantSecurityService
except ImportError:
    from config import SystemSettings, get_settings, load_index_registry  # type: ignore[no-redef]
    from schemas import (  # type: ignore[no-redef]
        IndexConfigSchema,
        JWTTokenPayload,
        MultiTenantStateStoreSchema,
        VirtualPortfolioLedgerSchema,
    )
    from security import MultiTenantSecurityService  # type: ignore[no-redef]

logger = logging.getLogger("SwingQuantEngine.Storage")

DEFAULT_ADMIN_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEFAULT_ADMIN_PORTFOLIO_ID = UUID("00000000-0000-4000-8000-000000000101")

REQUIRED_OHLCV_COLUMNS: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")


# =============================================================================
# 1. CUSTOM STORAGE & DATA INTEGRITY EXCEPTIONS
# =============================================================================


class StorageError(Exception):
    """Base exception for all persistence and serialization errors."""


class CorporateActionSplitDetectedError(StorageError):
    """
    Raised when a retroactive price discontinuity (stock split or reverse split)
    is detected at t-1 between newly ingested data and cached Parquet history,
    signaling that full 500-day history must be re-fetched cleanly.
    """


class StateCorruptionError(StorageError):
    """
    Raised when virtual_portfolio.json fails Pydantic schema validation
    or cross-tenant isolation checks.
    """


class MalformedStateError(StateCorruptionError):
    """
    Raised when persisted JSON state (GCS or local fallback) is malformed or
    fails structural validation (mapped to HTTP 503 Service Unavailable).
    """


# =============================================================================
# 2. ABSTRACT REPOSITORY INTERFACES (PHASE 2 CLOUD MIGRATION READY)
# =============================================================================


class MarketDataRepository(ABC):
    """
    Abstract repository contract for rolling-window OHLCV time-series storage.
    Decoupled for seamless transition from local Apache Parquet to cloud time-series stores.
    """

    @abstractmethod
    def save_ohlcv(self, ticker: str, df: pd.DataFrame) -> None:
        """Validates and atomically persists an OHLCV DataFrame for a ticker."""

    @abstractmethod
    def load_ohlcv(
        self,
        ticker: str,
        lookback_days: Optional[int] = None,
    ) -> Optional[pd.DataFrame]:
        """Loads cached OHLCV history for a ticker, optionally sliced to trailing lookback_days."""

    @abstractmethod
    def get_latest_cached_date(self, ticker: str) -> Optional[date]:
        """Returns the most recent Point-in-Time settlement date stored for a ticker."""

    @abstractmethod
    def purge_ticker_history(self, ticker: str) -> None:
        """Removes cached OHLCV storage for a ticker (e.g., upon split invalidation)."""


class PortfolioStateRepository(ABC):
    """
    Abstract repository contract for multi-tenant virtual portfolio state persistence.
    Decoupled for Phase 2 Supabase / PostgreSQL Row-Level Security (RLS) migration.
    """

    @abstractmethod
    def load_state(self) -> MultiTenantStateStoreSchema:
        """Loads and validates the multi-tenant portfolio state store."""

    @abstractmethod
    def save_state(self, state: MultiTenantStateStoreSchema) -> None:
        """Validates and atomically persists the multi-tenant portfolio state store."""


# =============================================================================
# 3. APACHE PARQUET ROLLING-WINDOW MARKET DATA REPOSITORY
# =============================================================================


class ParquetMarketDataRepository(MarketDataRepository):
    """
    Manages one Apache Parquet file per ticker at `{settings.parquet_data_dir}/{TICKER}.parquet`
    using the `pyarrow` engine and `snappy` compression.
    Enforces Dr. Marcos López de Prado's Point-in-Time (PiT) t-1 split detection guard
    and Jim Simons' atomic write-via-temp-file durability.
    """

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()
        self.parquet_dir: Path = self.settings.parquet_data_dir
        self.parquet_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_ticker(self, ticker: str) -> str:
        clean = ticker.strip().upper()
        if not clean or "/" in clean or "\\" in clean or ".." in clean:
            raise StorageError(f"Invalid ticker symbol identifier: '{ticker}'.")
        return clean

    def _get_file_path(self, ticker: str) -> Path:
        clean_ticker = self._sanitize_ticker(ticker)
        return self.parquet_dir / f"{clean_ticker}.parquet"

    def _validate_and_normalize_ohlcv(self, ticker: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        Enforces strict OHLCV schema invariants:
        - Normalized timezone-naive UTC DatetimeIndex, sorted ascending, unique dates.
        - Float64 columns ["Open", "High", "Low", "Close", "Volume"].
        - Non-null values, strictly positive prices, non-negative volume, and High >= Low.
        """
        if not isinstance(df, pd.DataFrame) or df.empty:
            raise StorageError(f"OHLCV DataFrame for '{ticker}' is empty or not a valid DataFrame.")

        working_df = df.copy()

        # Support case-insensitive column mapping if lowercase columns are provided
        col_Rename_map: Dict[str, str] = {}
        lower_to_canonical = {col.lower(): col for col in REQUIRED_OHLCV_COLUMNS}
        for col in working_df.columns:
            col_str = str(col).strip().lower()
            if col_str in lower_to_canonical:
                col_Rename_map[col] = lower_to_canonical[col_str]
        if col_Rename_map:
            working_df = working_df.rename(columns=col_Rename_map)

        missing_cols = [c for c in REQUIRED_OHLCV_COLUMNS if c not in working_df.columns]
        if missing_cols:
            raise StorageError(
                f"OHLCV DataFrame for '{ticker}' is missing required columns: {missing_cols}."
            )

        working_df = working_df.loc[:, list(REQUIRED_OHLCV_COLUMNS)].copy()

        # Validate and normalize DatetimeIndex
        try:
            dt_index = pd.to_datetime(working_df.index)
        except Exception as exc:
            raise StorageError(
                f"Failed to convert index to DatetimeIndex for '{ticker}': {exc}"
            ) from exc

        if not isinstance(dt_index, pd.DatetimeIndex):
            raise StorageError(f"Index for '{ticker}' must be a pandas DatetimeIndex.")

        if dt_index.tz is not None:
            dt_index = dt_index.tz_convert("UTC").tz_localize(None)

        dt_index = dt_index.normalize()
        if dt_index.isna().any():
            raise StorageError(f"DatetimeIndex for '{ticker}' contains NaT/null timestamps.")

        working_df.index = dt_index
        working_df.index.name = "Date"

        # Deduplicate keeping latest observation and sort ascending chronologically
        if working_df.index.has_duplicates:
            working_df = working_df[~working_df.index.duplicated(keep="last")]
        working_df = working_df.sort_index(ascending=True)

        # Enforce float64 dtype and non-null numerical values
        try:
            working_df = working_df.astype(np.float64)
        except (ValueError, TypeError) as exc:
            raise StorageError(
                f"OHLCV columns for '{ticker}' could not be cast to float64: {exc}"
            ) from exc

        if working_df.isna().any().any() or np.isinf(working_df.to_numpy()).any():
            raise StorageError(f"OHLCV DataFrame for '{ticker}' contains NaN or infinite values.")

        # Enforce positive price invariants and non-negative volume
        price_cols = ["Open", "High", "Low", "Close"]
        if (working_df[price_cols] <= 0.0).any().any():
            raise StorageError(
                f"OHLCV DataFrame for '{ticker}' contains non-positive price values."
            )

        if (working_df["Volume"] < 0.0).any():
            raise StorageError(
                f"OHLCV DataFrame for '{ticker}' contains negative volume values."
            )

        if (working_df["High"] < working_df["Low"]).any():
            raise StorageError(
                f"OHLCV geometry violation for '{ticker}': High < Low detected."
            )

        return working_df

    def _write_parquet_atomically(self, target_path: Path, df: pd.DataFrame) -> None:
        """
        Writes Parquet file to `{TICKER}.parquet.tmp` and executes an atomic POSIX `os.replace()`.
        """
        tmp_path = target_path.with_name(f"{target_path.name}.tmp")
        try:
            df.to_parquet(
                tmp_path,
                engine="pyarrow",
                compression="snappy",
                index=True,
            )
            os.replace(tmp_path, target_path)
        except Exception as exc:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError as cleanup_err:
                    logger.debug(f"Temporary Parquet cleanup warning for {tmp_path}: {cleanup_err}")
            raise StorageError(
                f"Atomic Parquet write failed for '{target_path}': {exc}"
            ) from exc

    def save_ohlcv(self, ticker: str, df: pd.DataFrame) -> None:
        """
        Validates, normalizes, trims to backtest_lookback_days, and atomically persists OHLCV data.
        """
        clean_ticker = self._sanitize_ticker(ticker)
        normalized_df = self._validate_and_normalize_ohlcv(clean_ticker, df)
        max_window = self.settings.backtest_lookback_days
        if len(normalized_df) > max_window:
            normalized_df = normalized_df.tail(max_window)

        file_path = self._get_file_path(clean_ticker)
        self._write_parquet_atomically(file_path, normalized_df)

    def load_ohlcv(
        self,
        ticker: str,
        lookback_days: Optional[int] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Loads cached OHLCV DataFrame from Parquet, validating schema integrity and optionally
        slicing the trailing `lookback_days` rows (e.g., 250 for screening, 500 for backtesting).
        """
        clean_ticker = self._sanitize_ticker(ticker)
        file_path = self._get_file_path(clean_ticker)
        if not file_path.exists():
            return None

        if lookback_days is not None and lookback_days <= 0:
            raise StorageError(f"lookback_days must be a positive integer, got {lookback_days}.")

        try:
            loaded_df = pd.read_parquet(file_path, engine="pyarrow")
        except Exception as exc:
            raise StorageError(
                f"Failed to read cached Parquet file for '{clean_ticker}' at {file_path}: {exc}"
            ) from exc

        validated_df = self._validate_and_normalize_ohlcv(clean_ticker, loaded_df)
        if lookback_days is not None:
            return validated_df.tail(lookback_days).copy()
        return validated_df

    def get_latest_cached_date(self, ticker: str) -> Optional[date]:
        """Returns the most recent cached trading date for `ticker`, or None if uncached."""
        df = self.load_ohlcv(ticker)
        if df is None or df.empty:
            return None
        latest_ts: pd.Timestamp = df.index[-1]
        return latest_ts.date()

    def purge_ticker_history(self, ticker: str) -> None:
        """Deletes the cached Parquet file for `ticker` if it exists."""
        file_path = self._get_file_path(ticker)
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as exc:
            raise StorageError(
                f"Failed to purge Parquet cache for '{ticker}' at {file_path}: {exc}"
            ) from exc

    def upsert_ohlcv(
        self,
        ticker: str,
        incoming_df: pd.DataFrame,
        max_window_days: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Smart Rolling-Window Upsert with Point-in-Time `t-1` Corporate Action Split Guard:
        1. Validates and normalizes `incoming_df`.
        2. Loads existing cached Parquet DataFrame if present.
        3. Compares `existing_close` vs `incoming_close` on the most recent overlapping date (`t-1`).
           If relative divergence exceeds `settings.split_detection_tolerance`, raises
           `CorporateActionSplitDetectedError`.
        4. Merges existing and incoming histories (keeping `incoming_df` for overlapping rows),
           sorts ascending, trims to trailing `max_window_days`, and writes atomically.
        """
        clean_ticker = self._sanitize_ticker(ticker)
        window_limit = (
            max_window_days
            if max_window_days is not None
            else self.settings.backtest_lookback_days
        )
        if window_limit <= 0:
            raise StorageError(f"max_window_days must be positive, got {window_limit}.")

        clean_incoming = self._validate_and_normalize_ohlcv(clean_ticker, incoming_df)
        existing_df = self.load_ohlcv(clean_ticker)

        if existing_df is not None and not existing_df.empty:
            overlapping_dates = existing_df.index.intersection(clean_incoming.index)
            if len(overlapping_dates) > 0:
                anchor_ts: pd.Timestamp = overlapping_dates.max()
                overlap_date = anchor_ts.date()
                existing_close = float(existing_df.loc[anchor_ts, "Close"])
                incoming_close = float(clean_incoming.loc[anchor_ts, "Close"])

                if existing_close <= 0.0:
                    raise StorageError(
                        f"Corrupted non-positive cached Close price ({existing_close}) for {clean_ticker} on {overlap_date}."
                    )

                relative_diff = abs(incoming_close - existing_close) / existing_close
                if relative_diff > self.settings.split_detection_tolerance:
                    raise CorporateActionSplitDetectedError(
                        f"Split/adjustment detected for {clean_ticker} on {overlap_date}: "
                        f"cached={existing_close:.4f}, incoming={incoming_close:.4f} "
                        f"(relative_diff={relative_diff:.4%} > tolerance={self.settings.split_detection_tolerance:.2%})"
                    )

            # Merge keeping incoming_df values on overlapping timestamps
            combined_df = clean_incoming.combine_first(existing_df)
            combined_df = combined_df.loc[:, list(REQUIRED_OHLCV_COLUMNS)].astype(np.float64)
            combined_df = combined_df[~combined_df.index.duplicated(keep="last")].sort_index(
                ascending=True
            )
        else:
            combined_df = clean_incoming

        trimmed_df = combined_df.tail(window_limit).copy()
        file_path = self._get_file_path(clean_ticker)
        self._write_parquet_atomically(file_path, trimmed_df)
        return trimmed_df

    def upsert_ohlcv_with_split_guard(
        self,
        ticker: str,
        incoming_df: pd.DataFrame,
        max_window_days: Optional[int] = None,
    ) -> pd.DataFrame:
        """Alias for `upsert_ohlcv` enforcing the Point-in-Time `t-1` split guard."""
        return self.upsert_ohlcv(
            ticker=ticker,
            incoming_df=incoming_df,
            max_window_days=max_window_days,
        )


# =============================================================================
# 4. ATOMIC MULTI-TENANT JSON STATE REPOSITORY
# =============================================================================


class JsonPortfolioStateRepository(PortfolioStateRepository):
    """
    Manages atomic multi-tenant portfolio persistence at `settings.virtual_portfolio_path`.
    Guarantees schema validity, cross-tenant isolation, and zero-corruption POSIX file swaps.
    """

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        state_path: Optional[Path] = None,
        index_registry_path: Optional[Path] = None,
    ) -> None:
        self.settings: SystemSettings = settings or get_settings()
        self.state_path: Path = (
            state_path.resolve()
            if state_path is not None
            else self.settings.virtual_portfolio_path
        )
        self.index_registry_path: Path = (
            index_registry_path.resolve()
            if index_registry_path is not None
            else self.settings.index_registry_path
        )
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load_index_registry(self) -> Dict[str, IndexConfigSchema]:
        """Loads and validates the index registry configuration."""
        return load_index_registry(self.index_registry_path)

    def load_state(self) -> MultiTenantStateStoreSchema:
        """
        Loads and strictly validates `virtual_portfolio.json`.
        If the file does not exist, initializes a clean default `MultiTenantStateStoreSchema`
        populated with `load_index_registry()` and an empty `tenant_portfolios={}` dict,
        persists it atomically, and returns it.
        """
        if not self.state_path.exists():
            try:
                registry = load_index_registry(self.index_registry_path)
            except Exception as exc:
                raise StorageError(
                    f"Failed to initialize default state store due to index registry error: {exc}"
                ) from exc

            initial_state = MultiTenantStateStoreSchema(
                index_registry=registry,
                tenant_portfolios={},
            )
            self.save_state(initial_state)
            return initial_state

        try:
            raw_text = self.state_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StorageError(
                f"Failed to read portfolio state file at {self.state_path}: {exc}"
            ) from exc

        try:
            return MultiTenantStateStoreSchema.model_validate_json(raw_text)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            # Check if file is a legacy/seed single-tenant VirtualPortfolioLedgerSchema
            try:
                raw_obj = json.loads(raw_text)
                if isinstance(raw_obj, dict) and "portfolio_id" in raw_obj and "tenant_portfolios" not in raw_obj:
                    single_ledger = VirtualPortfolioLedgerSchema.model_validate(raw_obj)
                    registry = load_index_registry(self.index_registry_path)
                    migrated_state = MultiTenantStateStoreSchema(
                        index_registry=registry,
                        tenant_portfolios={single_ledger.portfolio_id: single_ledger},
                    )
                    return migrated_state
            except Exception as fallback_err:
                logger.debug(f"Legacy single-tenant migration check skipped: {fallback_err}")

            raise StateCorruptionError(
                f"Portfolio state store at {self.state_path} failed schema or tenant isolation validation: {exc}"
            ) from exc

    @staticmethod
    def _write_text_atomically(target_path: Path, json_payload: str) -> None:
        """
        Atomically persists JSON text using NamedTemporaryFile + flush + fsync + os.replace
        so downstream readers never observe partial writes.
        """
        parent_dir = target_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        tmp_file_path: Optional[Path] = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(parent_dir),
                prefix=f".{target_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_file_path = Path(tmp_file.name)
                tmp_file.write(json_payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            os.replace(tmp_file_path, target_path)
        except Exception as exc:
            if tmp_file_path is not None and tmp_file_path.exists():
                try:
                    tmp_file_path.unlink()
                except OSError as cleanup_err:
                    logger.debug(f"Temporary state file cleanup warning for {tmp_file_path}: {cleanup_err}")
            raise StorageError(
                f"Atomic state persistence failed for {target_path}: {exc}"
            ) from exc

    def _resolve_mirrored_state_dir(self) -> Optional[Path]:
        """
        Returns `{base_dir}/data/state` when operating against the canonical
        `{base_dir}/data/virtual_portfolio.json` store so production commits and
        Cloud Run API state readers remain synchronized without mutating repo files
        during isolated sandbox/test runs.
        """
        canonical_primary = (self.settings.base_dir / "data" / "virtual_portfolio.json").resolve()
        if self.state_path == canonical_primary:
            return (self.settings.base_dir / "data" / "state").resolve()
        return None

    def save_state(self, state: MultiTenantStateStoreSchema) -> None:
        """
        Re-validates `state` to enforce cross-tenant isolation and Portfolio Heat invariants,
        updates `last_updated_utc`, and writes atomically using NamedTemporaryFile + fsync + os.replace.
        """
        try:
            validated_state = MultiTenantStateStoreSchema.model_validate(state.model_dump())
        except ValidationError as exc:
            raise StateCorruptionError(
                f"Refusing to persist corrupted or cross-tenant breaching state: {exc}"
            ) from exc

        now_utc = datetime.now(timezone.utc)
        state.last_updated_utc = now_utc
        validated_state.last_updated_utc = now_utc

        json_payload = validated_state.model_dump_json(indent=2)
        self._write_text_atomically(self.state_path, json_payload)

        mirrored_dir = self._resolve_mirrored_state_dir()
        if mirrored_dir is not None:
            mirrored_state_path = mirrored_dir / "virtual_portfolio.json"
            if mirrored_state_path != self.state_path:
                self._write_text_atomically(mirrored_state_path, json_payload)

    def save_eod_heartbeat(
        self,
        state: MultiTenantStateStoreSchema,
        trading_date: date,
        eod_status: str = "HEALTHY",
    ) -> Dict[str, Any]:
        """
        Atomically persists `eod_heartbeat.json` telemetry metadata alongside the
        portfolio ledger (and mirrors to `data/state/eod_heartbeat.json` in production).
        """
        ledgers = list(state.tenant_portfolios.values())
        primary_ledger = ledgers[0] if ledgers else None
        heat_pct = (
            round(primary_ledger.current_portfolio_heat_pct * 100.0, 2)
            if primary_ledger is not None
            else 0.0
        )
        open_positions_count = (
            sum(len(ledger.open_positions) for ledger in ledgers) if ledgers else 0
        )
        total_equity = (
            round(primary_ledger.total_equity, 2) if primary_ledger is not None else 0.0
        )
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        heartbeat_payload: Dict[str, Any] = {
            "last_successful_eod_timestamp": now_iso,
            "last_updated_utc": now_iso,
            "eod_status": eod_status,
            "trading_date": trading_date.isoformat(),
            "current_portfolio_heat_pct": heat_pct,
            "portfolio_heat_pct": heat_pct,
            "open_positions_count": open_positions_count,
            "total_equity": total_equity,
        }
        serialized = json.dumps(heartbeat_payload, indent=2, ensure_ascii=False)

        primary_heartbeat_path = self.state_path.parent / "eod_heartbeat.json"
        self._write_text_atomically(primary_heartbeat_path, serialized)

        mirrored_dir = self._resolve_mirrored_state_dir()
        if mirrored_dir is not None:
            mirrored_heartbeat_path = mirrored_dir / "eod_heartbeat.json"
            if mirrored_heartbeat_path != primary_heartbeat_path:
                self._write_text_atomically(mirrored_heartbeat_path, serialized)

        return heartbeat_payload

    def upsert_tenant_portfolio(
        self,
        ledger: VirtualPortfolioLedgerSchema,
    ) -> MultiTenantStateStoreSchema:
        """
        Loads current state, validates that all `ledger.subscribed_indices` exist in
        `state.index_registry`, upserts `state.tenant_portfolios[ledger.portfolio_id] = ledger`,
        saves atomically, and returns the updated state.
        """
        try:
            validated_ledger = VirtualPortfolioLedgerSchema.model_validate(ledger.model_dump())
        except ValidationError as exc:
            raise StateCorruptionError(
                f"Invalid VirtualPortfolioLedgerSchema passed to upsert_tenant_portfolio: {exc}"
            ) from exc

        state = self.load_state()

        unknown_indices = [
            idx_id
            for idx_id in validated_ledger.subscribed_indices
            if idx_id not in state.index_registry
        ]
        if unknown_indices:
            raise StorageError(
                f"Tenant portfolio '{validated_ledger.portfolio_id}' subscribes to unregistered "
                f"indices {unknown_indices}. Available indices: {list(state.index_registry.keys())}."
            )

        updated_portfolios = dict(state.tenant_portfolios)
        updated_portfolios[validated_ledger.portfolio_id] = validated_ledger

        updated_state = MultiTenantStateStoreSchema(
            schema_version=state.schema_version,
            last_updated_utc=datetime.now(timezone.utc),
            index_registry=state.index_registry,
            tenant_portfolios=updated_portfolios,
        )
        self.save_state(updated_state)
        return updated_state

    # -------------------------------------------------------------------------
    # Backward-Compatible Methods for Orchestrator & Sandbox Runner Integration
    # -------------------------------------------------------------------------

    def load_or_initialize_state(self, as_of_date: date) -> MultiTenantStateStoreSchema:
        """
        Loads state or seeds a default primary shadow portfolio if no tenant portfolios exist.
        """
        state = self.load_state()
        if not state.tenant_portfolios:
            default_portfolio = VirtualPortfolioLedgerSchema(
                portfolio_id=DEFAULT_ADMIN_PORTFOLIO_ID,
                user_id=DEFAULT_ADMIN_USER_ID,
                portfolio_name="Primary Swing Shadow Portfolio",
                as_of_date=as_of_date,
                cash_balance=100_000.0,
                total_equity=100_000.0,
                max_portfolio_heat_pct=self.settings.default_max_portfolio_heat_pct,
                max_concurrent_positions=10,
                subscribed_indices=list(state.index_registry.keys()),
            )
            return self.upsert_tenant_portfolio(default_portfolio)
        return state

    def save_state_atomically(self, state: MultiTenantStateStoreSchema) -> None:
        """Alias for `save_state`."""
        self.save_state(state)


# =============================================================================
# 5. PHASE 2 POSTGRESQL / SUPABASE ROW-LEVEL SECURITY (RLS) ADAPTER
# =============================================================================


class PostgresMultiTenantRepository:
    """
    Phase 2 Drop-in Relational Storage Adapter for Supabase / PostgreSQL.
    Binds the authenticated user's JWT `sub` claim directly into the PostgreSQL
    transaction context (`request.jwt.claim.sub`) so Row-Level Security (RLS)
    physically prevents cross-tenant data access at the database engine level.
    """

    def __init__(
        self,
        database_url: str,
        security_service: MultiTenantSecurityService | Any,
    ) -> None:
        self.database_url = database_url
        self.security_service = security_service

    def _verify_token(self, jwt_token: str) -> JWTTokenPayload:
        if hasattr(self.security_service, "verify_jwt"):
            return self.security_service.verify_jwt(jwt_token)
        if hasattr(self.security_service, "decode_and_verify_token"):
            return self.security_service.decode_and_verify_token(jwt_token)
        raise StorageError(
            "Configured security_service must expose verify_jwt() or decode_and_verify_token()."
        )

    @contextmanager
    def tenant_scoped_transaction(self, jwt_token: str) -> Iterator[Any]:
        """
        Verifies the user's JWT cryptographic signature and opens a PostgreSQL
        transaction scoped strictly to `token_payload.sub` via RLS session variables.
        """
        if psycopg is None:
            raise StorageError(
                "psycopg (PostgreSQL driver) is not installed in the current runtime environment."
            )
        if not self.database_url or not self.database_url.strip():
            raise StorageError("database_url must be a non-empty PostgreSQL connection URI.")

        payload: JWTTokenPayload = self._verify_token(jwt_token)

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('request.jwt.claim.sub', %s, true);",
                    (str(payload.sub),),
                )
                yield cur
            conn.commit()


# =============================================================================
# 6. F01 STATELESS GCS & LOCAL-FALLBACK STATE READER (60s TTL CACHE)
# =============================================================================


class StatelessGCSStateReader:
    """
    Thread-safe Single-Source-of-Truth reader for Cloud Run API containers.
    Reads `state/virtual_portfolio.json`, `state/equity_curve.json`, and
    `state/eod_telemetry.json` from Google Cloud Storage (`GCS_BUCKET_NAME` /
    `SIRIX_GCS_BUCKET`), falling back transparently to local disk (`data/state/`
    and `data/`), with a 60-second in-memory TTL cache and instant invalidation.
    """

    DEFAULT_CACHE_TTL_SECONDS: float = 60.0

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        bucket_name: Optional[str] = None,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        gcs_client: Optional[Any] = None,
        clock: Any = time.monotonic,
    ) -> None:
        self.settings: SystemSettings = settings or get_settings()
        raw_bucket = (
            bucket_name
            if bucket_name is not None
            else (
                os.environ.get("GCS_BUCKET_NAME", "").strip()
                or os.environ.get("SIRIX_GCS_BUCKET", "").strip()
            )
        )
        self.bucket_name: Optional[str] = (
            raw_bucket.removeprefix("gs://").strip("/") if raw_bucket else None
        )
        self.cache_ttl_seconds: float = max(0.0, float(cache_ttl_seconds))
        self._gcs_client = gcs_client
        self._clock = clock
        self._lock = threading.RLock()
        self._cache: Dict[str, Tuple[float, Any, Literal["GCS", "LOCAL_FALLBACK"]]] = {}

        self.local_state_dir: Path = (self.settings.base_dir / "data" / "state").resolve()
        self.local_data_dir: Path = (self.settings.base_dir / "data").resolve()

    def active_backend(self) -> Literal["GCS", "LOCAL_FALLBACK"]:
        """Returns the primary configured state backend identifier."""
        if self.bucket_name and (self._gcs_client is not None or gcs_storage is not None):
            return "GCS"
        return "LOCAL_FALLBACK"

    def _get_gcs_client(self) -> Optional[Any]:
        if not self.bucket_name:
            return None
        if self._gcs_client is not None:
            return self._gcs_client
        if gcs_storage is None:
            return None
        try:
            self._gcs_client = gcs_storage.Client()
        except Exception as exc:
            logger.warning(f"Failed to initialize GCS client; using local fallback if available: {exc}")
            return None
        return self._gcs_client

    def invalidate_cache(self, object_name: Optional[str] = None) -> None:
        """
        Immediately clears cached state objects (all objects when `object_name` is None).
        Invoked by `POST /api/internal/trigger-eod` upon EOD completion.
        """
        with self._lock:
            if object_name is None:
                self._cache.clear()
            else:
                self._cache.pop(object_name, None)

    def _read_gcs_bytes(self, object_name: str) -> Optional[bytes]:
        client = self._get_gcs_client()
        if client is None or not self.bucket_name:
            return None
        try:
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(object_name)
            if not blob.exists():
                return None
            return bytes(blob.download_as_bytes())
        except Exception as exc:
            logger.warning(f"GCS read failed for gs://{self.bucket_name}/{object_name}: {exc}")
            return None

    def _default_local_candidates(self, object_name: str) -> List[Path]:
        clean = object_name.strip("/")
        basename = Path(clean).name
        candidates: List[Path] = [
            self.local_state_dir / basename,
            self.local_data_dir / clean,
            self.local_data_dir / basename,
        ]
        if basename == "virtual_portfolio.json":
            candidates.insert(0, self.settings.virtual_portfolio_path)
        deduped: List[Path] = []
        seen: set[Path] = set()
        for path in candidates:
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                deduped.append(resolved)
        return deduped

    def _parse_json_bytes(self, raw_bytes: bytes, source_label: str) -> Any:
        try:
            decoded_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MalformedStateError(
                f"State object '{source_label}' contains invalid UTF-8 bytes: {exc}"
            ) from exc
        try:
            return json.loads(decoded_text)
        except json.JSONDecodeError as exc:
            raise MalformedStateError(
                f"Malformed JSON in state object '{source_label}': {exc}"
            ) from exc

    def read_json(
        self,
        object_name: str,
        local_fallbacks: Optional[Sequence[Path]] = None,
        default: Optional[Any] = None,
    ) -> Tuple[Any, Literal["GCS", "LOCAL_FALLBACK"]]:
        """
        Reads and parses JSON from GCS (preferred) or local filesystem with a 60s TTL cache.
        Raises `MalformedStateError` if an existing artifact contains corrupt JSON.
        """
        now_ts = float(self._clock())
        with self._lock:
            cached = self._cache.get(object_name)
            if cached is not None:
                expires_at, cached_payload, cached_backend = cached
                if now_ts < expires_at:
                    return cached_payload, cached_backend

            raw_gcs = self._read_gcs_bytes(object_name)
            if raw_gcs is not None:
                parsed = self._parse_json_bytes(raw_gcs, f"gs://{self.bucket_name}/{object_name}")
                backend: Literal["GCS", "LOCAL_FALLBACK"] = "GCS"
                self._cache[object_name] = (now_ts + self.cache_ttl_seconds, parsed, backend)
                return parsed, backend

            candidate_paths = (
                list(local_fallbacks)
                if local_fallbacks is not None
                else self._default_local_candidates(object_name)
            )
            for candidate in candidate_paths:
                if candidate.exists() and candidate.is_file():
                    try:
                        raw_bytes = candidate.read_bytes()
                    except OSError as exc:
                        raise MalformedStateError(
                            f"Unable to read state file '{candidate}': {exc}"
                        ) from exc
                    parsed = self._parse_json_bytes(raw_bytes, str(candidate))
                    backend = "LOCAL_FALLBACK"
                    self._cache[object_name] = (now_ts + self.cache_ttl_seconds, parsed, backend)
                    return parsed, backend

            if default is not None:
                fallback_backend = self.active_backend()
                return default, fallback_backend

            raise MalformedStateError(
                f"Required state object '{object_name}' not found in GCS or local fallback directories."
            )

    def write_json_atomically(
        self,
        object_name: str,
        payload: Any,
        local_path: Optional[Path] = None,
    ) -> Literal["GCS", "LOCAL_FALLBACK"]:
        """
        Serializes `payload` and persists atomically to GCS (if configured) and/or
        local storage (`NamedTemporaryFile + fsync + os.replace`), invalidating cache.
        """
        serialized = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        target_local = (
            local_path.resolve()
            if local_path is not None
            else (self.local_state_dir / Path(object_name).name)
        )

        with self._lock:
            backend_used: Literal["GCS", "LOCAL_FALLBACK"] = "LOCAL_FALLBACK"
            client = self._get_gcs_client()
            if client is not None and self.bucket_name:
                try:
                    bucket = client.bucket(self.bucket_name)
                    clean_obj = object_name.strip("/")
                    staging_blob = bucket.blob(f"{clean_obj}.tmp")
                    staging_blob.cache_control = "no-store"
                    staging_blob.upload_from_string(serialized, content_type="application/json")
                    target_blob = bucket.blob(clean_obj)
                    target_blob.cache_control = "no-store"
                    bucket.copy_blob(staging_blob, bucket, clean_obj)
                    try:
                        staging_blob.delete()
                    except Exception as cleanup_exc:
                        logger.debug(f"GCS staging blob cleanup warning: {cleanup_exc}")
                    backend_used = "GCS"
                except Exception as exc:
                    raise StorageError(
                        f"Atomic GCS upload failed for gs://{self.bucket_name}/{object_name}: {exc}"
                    ) from exc

            JsonPortfolioStateRepository._write_text_atomically(target_local, serialized)
            self._cache.pop(object_name, None)
            return backend_used

    def read_virtual_portfolio(self) -> Tuple[MultiTenantStateStoreSchema, Literal["GCS", "LOCAL_FALLBACK"]]:
        """
        Loads and strictly validates `state/virtual_portfolio.json` into
        `MultiTenantStateStoreSchema`. If neither GCS nor local state exists yet
        (Day-1 cold start), returns a clean 100% initial cash ($100,000) portfolio.
        """
        raw_obj, backend = self.read_json("state/virtual_portfolio.json", default={})
        if not isinstance(raw_obj, dict):
            raise MalformedStateError("state/virtual_portfolio.json root must be a JSON object.")

        if not raw_obj:
            registry = load_index_registry(self.settings.index_registry_path)
            active_indices = [idx_id for idx_id, cfg in registry.items() if cfg.is_active] or list(registry.keys())
            default_ledger = VirtualPortfolioLedgerSchema(
                portfolio_id=DEFAULT_ADMIN_PORTFOLIO_ID,
                user_id=DEFAULT_ADMIN_USER_ID,
                portfolio_name="Primary Swing Shadow Portfolio",
                as_of_date=datetime.now(timezone.utc).date(),
                cash_balance=100_000.0,
                total_equity=100_000.0,
                max_portfolio_heat_pct=self.settings.default_max_portfolio_heat_pct,
                max_concurrent_positions=10,
                subscribed_indices=active_indices,
                open_positions={},
                closed_trades_audit=[],
            )
            return (
                MultiTenantStateStoreSchema(
                    index_registry=registry,
                    tenant_portfolios={DEFAULT_ADMIN_PORTFOLIO_ID: default_ledger},
                ),
                backend,
            )

        try:
            if "portfolio_id" in raw_obj and "tenant_portfolios" not in raw_obj:
                single_ledger = VirtualPortfolioLedgerSchema.model_validate(raw_obj)
                registry = load_index_registry(self.settings.index_registry_path)
                state = MultiTenantStateStoreSchema(
                    index_registry=registry,
                    tenant_portfolios={single_ledger.portfolio_id: single_ledger},
                )
                return state, backend
            return MultiTenantStateStoreSchema.model_validate(raw_obj), backend
        except (ValidationError, ValueError, TypeError) as exc:
            raise MalformedStateError(
                f"Portfolio ledger failed Pydantic v2 contract validation: {exc}"
            ) from exc

    def read_equity_curve(self) -> Tuple[List[Dict[str, Any]], Literal["GCS", "LOCAL_FALLBACK"]]:
        """
        Loads `state/equity_curve.json` (accepting either a list of points or
        `{"points": [...]}` wrapper), returning an empty list if not yet generated.
        """
        raw_obj, backend = self.read_json("state/equity_curve.json", default=[])
        if isinstance(raw_obj, dict) and isinstance(raw_obj.get("points"), list):
            return list(raw_obj["points"]), backend
        if isinstance(raw_obj, list):
            return list(raw_obj), backend
        raise MalformedStateError("state/equity_curve.json must be a JSON array or {'points': [...]}.")

    def read_eod_telemetry(self) -> Tuple[Dict[str, Any], Literal["GCS", "LOCAL_FALLBACK"]]:
        """
        Loads `state/eod_telemetry.json`, falling back to `eod_heartbeat.json`
        if `eod_telemetry.json` has not been emitted yet.
        """
        telemetry_obj, backend = self.read_json("state/eod_telemetry.json", default={})
        if isinstance(telemetry_obj, dict) and telemetry_obj:
            return telemetry_obj, backend
        if not isinstance(telemetry_obj, dict):
            raise MalformedStateError("state/eod_telemetry.json root must be a JSON object.")

        heartbeat_obj, hb_backend = self.read_json(
            "state/eod_heartbeat.json",
            local_fallbacks=[
                self.local_state_dir / "eod_heartbeat.json",
                self.local_data_dir / "eod_heartbeat.json",
            ],
            default={},
        )
        if not isinstance(heartbeat_obj, dict):
            raise MalformedStateError("eod_heartbeat.json root must be a JSON object.")
        return heartbeat_obj, hb_backend


# Backward-compatible aliases used across existing modules
BasePortfolioRepository = PortfolioStateRepository
JsonFilePortfolioRepository = JsonPortfolioStateRepository
AtomicStateRepository = JsonPortfolioStateRepository


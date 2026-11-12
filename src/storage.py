from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, Optional
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import ValidationError

try:
    from src.config import SystemSettings, get_settings, load_index_registry
    from src.schemas import (
        IndexConfigSchema,
        MultiTenantStateStoreSchema,
        VirtualPortfolioLedgerSchema,
    )
except ImportError:
    from config import SystemSettings, get_settings, load_index_registry  # type: ignore[no-redef]
    from schemas import (  # type: ignore[no-redef]
        IndexConfigSchema,
        MultiTenantStateStoreSchema,
        VirtualPortfolioLedgerSchema,
    )

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
        raise NotImplementedError

    @abstractmethod
    def load_ohlcv(
        self,
        ticker: str,
        lookback_days: Optional[int] = None,
    ) -> Optional[pd.DataFrame]:
        """Loads cached OHLCV history for a ticker, optionally sliced to trailing lookback_days."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_cached_date(self, ticker: str) -> Optional[date]:
        """Returns the most recent Point-in-Time settlement date stored for a ticker."""
        raise NotImplementedError

    @abstractmethod
    def purge_ticker_history(self, ticker: str) -> None:
        """Removes cached OHLCV storage for a ticker (e.g., upon split invalidation)."""
        raise NotImplementedError


class PortfolioStateRepository(ABC):
    """
    Abstract repository contract for multi-tenant virtual portfolio state persistence.
    Decoupled for Phase 2 Supabase / PostgreSQL Row-Level Security (RLS) migration.
    """

    @abstractmethod
    def load_state(self) -> MultiTenantStateStoreSchema:
        """Loads and validates the multi-tenant portfolio state store."""
        raise NotImplementedError

    @abstractmethod
    def save_state(self, state: MultiTenantStateStoreSchema) -> None:
        """Validates and atomically persists the multi-tenant portfolio state store."""
        raise NotImplementedError


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
                except OSError:
                    pass
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
            except Exception:
                pass

            raise StateCorruptionError(
                f"Portfolio state store at {self.state_path} failed schema or tenant isolation validation: {exc}"
            ) from exc

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
        parent_dir = self.state_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        tmp_file_path: Optional[Path] = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(parent_dir),
                prefix=f".{self.state_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_file_path = Path(tmp_file.name)
                tmp_file.write(json_payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            os.replace(tmp_file_path, self.state_path)
        except Exception as exc:
            if tmp_file_path is not None and tmp_file_path.exists():
                try:
                    tmp_file_path.unlink()
                except OSError:
                    pass
            raise StorageError(
                f"Atomic state persistence failed for {self.state_path}: {exc}"
            ) from exc

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


# Backward-compatible aliases used across existing modules
BasePortfolioRepository = PortfolioStateRepository
JsonFilePortfolioRepository = JsonPortfolioStateRepository
AtomicStateRepository = JsonPortfolioStateRepository

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
import logging
from pathlib import Path
import random
import time
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from schemas import IndexConfigSchema, MultiTenantStateStoreSchema

logger = logging.getLogger("SwingQuantEngine.DataIngestion")


# =========================================================================
# 1. ABSTRACT DATA PROVIDER INTERFACE
# =========================================================================

class BaseMarketDataProvider(ABC):
    """
    Abstract contract for market data vendors (yfinance, Polygon.io, Alpaca).
    Enforces strict Point-in-Time (PiT) upper bounds and adjusted OHLCV schemas.
    """

    @abstractmethod
    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        """
        Returns a MultiIndex DataFrame indexed by (date, ticker) with columns:
        ['open', 'high', 'low', 'close', 'volume', 'dividends', 'splits']
        All prices MUST be adjusted for splits and dividends up to end_date_inclusive.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_index_constituents(self, index_id: str) -> List[str]:
        """Returns the current constituent ticker roster for a registered index."""
        raise NotImplementedError


# =========================================================================
# 2. YFINANCE CONCRETE PROVIDER WITH CHUNKING & EXPONENTIAL BACKOFF
# =========================================================================

class YFinanceProvider(BaseMarketDataProvider):
    """
    Resilient Yahoo Finance implementation with chunked batching,
    rate-limit jitter, and exponential backoff retry logic.
    """

    def __init__(
        self,
        chunk_size: int = 100,
        max_retries: int = 3,
        base_backoff_sec: float = 2.0,
        constituent_lists_dir: Path = Path("config/constituents"),
    ) -> None:
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.constituent_lists_dir = constituent_lists_dir

    def fetch_index_constituents(self, index_id: str) -> List[str]:
        """
        Loads constituent symbols for the given index_id (e.g., 'RUT', 'MID')
        from a curated local CSV roster.
        """
        roster_file = self.constituent_lists_dir / f"{index_id}.csv"
        if not roster_file.exists():
            raise FileNotFoundError(
                f"Constituent roster file not found for index '{index_id}' at {roster_file}"
            )
        df = pd.read_csv(roster_file)
        tickers = (
            df["ticker"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .str.replace(".", "-", regex=False)
            .unique()
            .tolist()
        )
        return sorted(tickers)

    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame()

        yf_end_date = end_date_inclusive + timedelta(days=1)
        all_chunks: List[pd.DataFrame] = []

        chunks = [
            tickers[i : i + self.chunk_size]
            for i in range(0, len(tickers), self.chunk_size)
        ]

        for idx, chunk in enumerate(chunks, start=1):
            chunk_df = self._download_chunk_with_backoff(
                chunk=chunk,
                start_str=start_date.isoformat(),
                end_str=yf_end_date.isoformat(),
                chunk_index=idx,
                total_chunks=len(chunks),
            )
            if not chunk_df.empty:
                all_chunks.append(chunk_df)

            if idx < len(chunks):
                time.sleep(random.uniform(0.35, 0.85))

        if not all_chunks:
            return pd.DataFrame()

        combined = pd.concat(all_chunks, axis=0)
        combined = combined.loc[
            combined.index.get_level_values("date") <= pd.Timestamp(end_date_inclusive)
        ]
        return combined.sort_index()

    def _download_chunk_with_backoff(
        self,
        chunk: List[str],
        start_str: str,
        end_str: str,
        chunk_index: int,
        total_chunks: int,
    ) -> pd.DataFrame:
        for attempt in range(1, self.max_retries + 1):
            try:
                raw = yf.download(
                    tickers=chunk,
                    start=start_str,
                    end=end_str,
                    auto_adjust=True,
                    actions=True,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
                if raw is None or raw.empty:
                    return pd.DataFrame()
                return self._normalize_yf_dataframe(raw, chunk)

            except Exception as exc:
                wait_time = (self.base_backoff_sec ** attempt) + random.uniform(0.1, 0.9)
                logger.warning(
                    f"[Chunk {chunk_index}/{total_chunks}] Attempt {attempt}/{self.max_retries} "
                    f"failed ({exc}). Retrying in {wait_time:.2f}s..."
                )
                time.sleep(wait_time)

        logger.error(f"[Chunk {chunk_index}/{total_chunks}] Exhausted all retries. Skipping chunk.")
        return pd.DataFrame()

    @staticmethod
    def _normalize_yf_dataframe(raw: pd.DataFrame, requested_tickers: List[str]) -> pd.DataFrame:
        """Transforms yfinance wide/MultiIndex output into a standardized (date, ticker) table."""
        records: List[pd.DataFrame] = []

        if isinstance(raw.columns, pd.MultiIndex):
            available_tickers = set(raw.columns.get_level_values(0))
            for ticker in requested_tickers:
                if ticker not in available_tickers:
                    continue
                sub = raw[ticker].copy()
                sub["ticker"] = ticker
                records.append(sub)
        else:
            sub = raw.copy()
            sub["ticker"] = requested_tickers[0]
            records.append(sub)

        if not records:
            return pd.DataFrame()

        stacked = pd.concat(records, axis=0)
        stacked.index.name = "date"
        stacked = stacked.reset_index()
        stacked["date"] = pd.to_datetime(stacked["date"]).dt.tz_localize(None).dt.normalize()

        rename_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Dividends": "dividends",
            "Stock Splits": "splits",
        }
        stacked = stacked.rename(columns=rename_map)

        for action_col in ("dividends", "splits"):
            if action_col not in stacked.columns:
                stacked[action_col] = 0.0
            else:
                stacked[action_col] = stacked[action_col].fillna(0.0)

        required_cols = [
            "date",
            "ticker",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "dividends",
            "splits",
        ]
        stacked = stacked[[c for c in required_cols if c in stacked.columns]]
        stacked = stacked.dropna(subset=["open", "high", "low", "close", "volume"])

        return stacked.set_index(["date", "ticker"]).sort_index()


# Alias for backward compatibility
YFinanceDataProvider = YFinanceProvider


# =========================================================================
# 3. SMART SLIDING WINDOW MANAGER (Incremental Delta + Corporate Action Guard)
# =========================================================================

class SmartSlidingWindowOrchestrator:
    """
    Maintains a rolling W-day historical OHLCV window (default 500 trading days)
    stored in Apache Parquet. Uses daily 2-day Delta Fetches, Pre-Ingestion
    active portfolio exclusion tracking, and t-1 Overlap Corporate Action detection.
    """

    def __init__(
        self,
        provider: BaseMarketDataProvider,
        cache_path: Path = Path("data/cache/market_data_window.parquet"),
        max_window_bars: int = 500,
        min_required_bars: int = 250,
        reconciliation_tolerance: float = 1e-4,
    ) -> None:
        self.provider = provider
        self.cache_path = cache_path
        self.max_window_bars = max_window_bars
        self.min_required_bars = min_required_bars
        self.reconciliation_tolerance = reconciliation_tolerance
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def filter_candidate_universe(
        constituent_tickers: List[str],
        active_portfolio_tickers: Set[str],
    ) -> List[str]:
        """
        Pre-Ingestion Portfolio Exclusion Gate: removes tickers currently held
        in the active portfolio from the new-candidate screening roster.
        """
        held_upper = {t.upper() for t in active_portfolio_tickers}
        return [t for t in constituent_tickers if t.upper() not in held_upper]

    def sync_daily_market_window(
        self,
        state_store: MultiTenantStateStoreSchema,
        as_of_date: date,
    ) -> Tuple[pd.DataFrame, Set[str]]:
        active_indices: Dict[str, IndexConfigSchema] = {
            idx_id: cfg
            for idx_id, cfg in state_store.index_registry.items()
            if cfg.is_active
        }

        held_tickers: Set[str] = set()
        for portfolio in state_store.tenant_portfolios.values():
            held_tickers.update(portfolio.open_positions.keys())

        universe_tickers: Set[str] = set(held_tickers)
        for idx_id, cfg in active_indices.items():
            universe_tickers.add(cfg.benchmark_ticker.upper())
            constituents = self.provider.fetch_index_constituents(idx_id)
            universe_tickers.update(constituents)

        sorted_universe = sorted(universe_tickers)
        logger.info(
            f"Starting Sliding Window Sync as of {as_of_date} for {len(sorted_universe)} unique symbols "
            f"({len(held_tickers)} currently held across tenant portfolios)."
        )

        cached_df = self._load_cached_window(as_of_date)

        if cached_df.empty:
            logger.info("No local cache found. Executing Cold-Start Full History Hydration...")
            updated_df = self._hydrate_full_history(sorted_universe, as_of_date)
        else:
            updated_df = self._incremental_delta_sync(cached_df, sorted_universe, as_of_date)

        sanitized_df = self._sanitize_and_trim_window(updated_df, as_of_date)
        self._save_cached_window(sanitized_df)

        return sanitized_df, held_tickers

    def _hydrate_full_history(self, tickers: List[str], as_of_date: date) -> pd.DataFrame:
        calendar_lookback = int(self.max_window_bars * 1.52)
        start_date = as_of_date - timedelta(days=calendar_lookback)
        return self.provider.fetch_ohlcv_batch(
            tickers=tickers,
            start_date=start_date,
            end_date_inclusive=as_of_date,
        )

    def _incremental_delta_sync(
        self,
        cached_df: pd.DataFrame,
        universe_tickers: List[str],
        as_of_date: date,
    ) -> pd.DataFrame:
        cached_tickers = set(cached_df.index.get_level_values("ticker").unique())
        missing_tickers = sorted(set(universe_tickers) - cached_tickers)
        existing_tickers = sorted(set(universe_tickers) & cached_tickers)

        delta_start = as_of_date - timedelta(days=7)
        delta_df = self.provider.fetch_ohlcv_batch(
            tickers=existing_tickers,
            start_date=delta_start,
            end_date_inclusive=as_of_date,
        )

        corrupted_tickers = self._detect_corporate_actions(cached_df, delta_df)
        rehydrate_list = sorted(set(missing_tickers) | corrupted_tickers)

        if rehydrate_list:
            logger.info(
                f"Re-hydrating full {self.max_window_bars}-bar history for {len(rehydrate_list)} tickers "
                f"({len(missing_tickers)} new, {len(corrupted_tickers)} corporate action adjustments)."
            )
            rehydrated_df = self._hydrate_full_history(rehydrate_list, as_of_date)
        else:
            rehydrated_df = pd.DataFrame()

        clean_cached = cached_df.loc[
            ~cached_df.index.get_level_values("ticker").isin(rehydrate_list)
        ]
        clean_delta = (
            delta_df.loc[~delta_df.index.get_level_values("ticker").isin(rehydrate_list)]
            if not delta_df.empty
            else pd.DataFrame()
        )

        frames = [f for f in (clean_cached, clean_delta, rehydrated_df) if not f.empty]
        if not frames:
            return pd.DataFrame()

        merged = pd.concat(frames, axis=0)
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        return merged

    def _detect_corporate_actions(
        self,
        cached_df: pd.DataFrame,
        delta_df: pd.DataFrame,
    ) -> Set[str]:
        """
        Compares the overlapping t-1 adjusted close between cached_df and delta_df,
        and inspects explicit split/dividend columns.
        """
        if delta_df.empty:
            return set()

        flagged_tickers: Set[str] = set()

        action_mask = (delta_df["splits"] != 0.0) | (delta_df["dividends"] != 0.0)
        if action_mask.any():
            flagged_tickers.update(
                delta_df.loc[action_mask].index.get_level_values("ticker").unique()
            )

        common_index = cached_df.index.intersection(delta_df.index)
        if len(common_index) > 0:
            cached_closes = cached_df.loc[common_index, "close"]
            delta_closes = delta_df.loc[common_index, "close"]
            rel_diff = (delta_closes - cached_closes).abs() / cached_closes.replace(0, np.nan)
            discrepancy_mask = rel_diff > self.reconciliation_tolerance
            if discrepancy_mask.any():
                flagged_tickers.update(
                    rel_diff.loc[discrepancy_mask].index.get_level_values("ticker").unique()
                )

        return flagged_tickers

    def _sanitize_and_trim_window(self, df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.loc[df.index.get_level_values("date") <= pd.Timestamp(as_of_date)]

        valid_bar_mask = (
            (df["close"] > 0.0)
            & (df["open"] > 0.0)
            & (df["low"] > 0.0)
            & (df["high"] >= df["low"])
            & (df["high"] >= df["open"])
            & (df["high"] >= df["close"])
            & (df["low"] <= df["open"])
            & (df["low"] <= df["close"])
            & (df["volume"] >= 0)
        )
        df = df.loc[valid_bar_mask].sort_index()
        df = df.groupby(level="ticker", group_keys=False).tail(self.max_window_bars)
        return df

    def _load_cached_window(self, as_of_date: date) -> pd.DataFrame:
        if not self.cache_path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(self.cache_path)
        df = df.loc[df.index.get_level_values("date") <= pd.Timestamp(as_of_date)]
        return df.sort_index()

    def _save_cached_window(self, df: pd.DataFrame) -> None:
        if not df.empty:
            df.to_parquet(self.cache_path, engine="pyarrow", compression="snappy")

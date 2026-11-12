from __future__ import annotations

from abc import ABC, abstractmethod
import csv
from datetime import date, timedelta
from io import StringIO
import logging
import os
from pathlib import Path
import random
import tempfile
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

import httpx
import numpy as np
import pandas as pd
import yfinance as yf

try:
    from src.config import SystemSettings, get_settings
    from src.schemas import IndexConfigSchema, IndexTier, MultiTenantStateStoreSchema
    from src.storage import (
        CorporateActionSplitDetectedError,
        MarketDataRepository,
        ParquetMarketDataRepository,
        StorageError,
    )
except ImportError:
    from config import SystemSettings, get_settings  # type: ignore[no-redef]
    from schemas import IndexConfigSchema, IndexTier, MultiTenantStateStoreSchema  # type: ignore[no-redef]
    from storage import (  # type: ignore[no-redef]
        CorporateActionSplitDetectedError,
        MarketDataRepository,
        ParquetMarketDataRepository,
        StorageError,
    )

logger = logging.getLogger("SwingQuantEngine.DataIngestion")


def _configure_yfinance_tz_cache() -> None:
    """
    Safely relocates the yfinance SQLite timezone cache to an isolated temporary directory
    to prevent `[Errno 17] File exists: '/home/runner/.cache/py-yfinance'` race conditions
    on ephemeral GitHub Actions runners.
    """
    try:
        tz_cache_dir = os.path.join(tempfile.gettempdir(), "py-yfinance")
        os.makedirs(tz_cache_dir, exist_ok=True)
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(tz_cache_dir)
    except Exception as exc:
        logger.debug(f"yfinance timezone cache setup skipped: {exc}")


_configure_yfinance_tz_cache()

CANONICAL_OHLCV_COLS: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")


# =============================================================================
# 1. CUSTOM INGESTION EXCEPTIONS
# =============================================================================


class DataIngestionError(Exception):
    """Base exception for provider failures, rate-limiting exhaustion, or invalid market data feeds."""


# =============================================================================
# 2. ABSTRACT MARKET DATA PROVIDER INTERFACE
# =============================================================================


class MarketDataProvider(ABC):
    """
    Abstract contract decoupling external market data APIs (yfinance in Phase 1;
    FMP, Polygon.io, or IBKR in Phase 2) from the quantitative engine core.
    """

    @abstractmethod
    def fetch_daily_ohlcv_batch(
        self,
        tickers: Sequence[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetches daily adjusted OHLCV bars for a sequence of tickers between
        start_date and end_date (inclusive), returning a mapping of
        `ticker -> DataFrame` with columns `["Open", "High", "Low", "Close", "Volume"]`.
        """

    @abstractmethod
    def fetch_index_constituents(self, index_config: IndexConfigSchema) -> List[str]:
        """Resolves and returns the normalized constituent ticker roster for an index."""

    @abstractmethod
    def fetch_current_quotes_spread_proxy(self, tickers: Sequence[str]) -> Dict[str, float]:
        """
        Returns the relative bid-ask spread `(Ask - Bid) / Mid` per ticker,
        or `0.0` if unavailable in EOD-only fallback mode.
        """


# =============================================================================
# 3. RESILIENT YFINANCE MARKET DATA PROVIDER IMPLEMENTATION
# =============================================================================


class YFinanceMarketDataProvider(MarketDataProvider):
    """
    Production Yahoo Finance market data provider featuring:
    - Chunked batch downloading (`settings.yfinance_batch_size`) with SLA-optimized
      inter-batch jitter (`0.15s - 0.35s`).
    - Exponential backoff retry loops.
    - Point-in-Time (PiT) date boundary truncation and OHLCV bar sanity checks.
    - Dynamic live web constituent resolution (iShares `IWM` ETF holdings CSV for `RUT_2000`,
      Wikipedia HTML tables for `SP_400` and `SP_500`) with local CSV/TXT fallback on network failure.
    """

    WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    WIKIPEDIA_SP400_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    ISHARES_IWM_CSV_URL = (
        "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
        "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    )
    HTTP_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    FORBIDDEN_TICKER_TOKENS: Set[str] = {
        "-",
        "--",
        "USD",
        "MARGIN",
        "CASH",
        "FUTURES",
        "SWAP",
        "N/A",
        "NAN",
        "NONE",
    }

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalizes equity symbol for Yahoo Finance compatibility (e.g., BRK.B -> BRK-B)."""
        return symbol.strip().upper().replace(".", "-").replace("/", "-")

    @classmethod
    def _is_valid_equity_symbol(cls, raw_symbol: str) -> bool:
        """
        Validates that a raw ticker string represents a legitimate equity symbol:
        - Non-empty, no internal spaces, not digits-only
        - Not in FORBIDDEN_TICKER_TOKENS ('-', 'USD', 'MARGIN', etc.)
        - Length <= 6 characters
        - Alphanumeric (allowing hyphen for share classes)
        """
        s = raw_symbol.strip().upper()
        if not s or " " in s or len(s) > 6:
            return False
        if s in cls.FORBIDDEN_TICKER_TOKENS or s.isdigit():
            return False
        if "USD" in s or "MARGIN" in s:
            return False
        normalized = cls._normalize_symbol(s)
        if normalized.startswith("-") or normalized.endswith("-"):
            return False
        alnum_part = normalized.replace("-", "")
        return bool(alnum_part) and alnum_part.isalnum()

    @staticmethod
    def _deduplicate_preserving_order(symbols: Sequence[str]) -> List[str]:
        return list(dict.fromkeys(symbols))

    def _sanitize_ohlcv_frame(
        self,
        ticker: str,
        df: pd.DataFrame,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Enforces strict OHLCV structural and Point-in-Time invariants:
        - Columns exact: ["Open", "High", "Low", "Close", "Volume"]
        - Timezone-naive UTC date-normalized DatetimeIndex, sorted ascending, unique
        - High >= Low, High >= Open, High >= Close, Low <= Open, Low <= Close
        - Close > 0, Open > 0, Low > 0, Volume >= 0
        - Returns None if fewer than 5 valid trading bars remain.
        """
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return None

        working = df.copy()

        col_map: Dict[str, str] = {}
        lower_lookup = {c.lower(): c for c in CANONICAL_OHLCV_COLS}
        for col in working.columns:
            col_lower = str(col).strip().lower()
            if col_lower in lower_lookup:
                col_map[col] = lower_lookup[col_lower]
        if col_map:
            working = working.rename(columns=col_map)

        if any(c not in working.columns for c in CANONICAL_OHLCV_COLS):
            return None

        working = working.loc[:, list(CANONICAL_OHLCV_COLS)].copy()

        try:
            dt_idx = pd.to_datetime(working.index)
        except Exception:
            return None

        if not isinstance(dt_idx, pd.DatetimeIndex):
            return None

        if dt_idx.tz is not None:
            dt_idx = dt_idx.tz_convert("UTC").tz_localize(None)

        working.index = dt_idx.normalize()
        working.index.name = "Date"

        working = working.loc[~working.index.isna()]
        if working.index.has_duplicates:
            working = working[~working.index.duplicated(keep="last")]
        working = working.sort_index(ascending=True)

        if start_date is not None:
            working = working.loc[working.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            working = working.loc[working.index <= pd.Timestamp(end_date)]

        if working.empty:
            return None

        for col in CANONICAL_OHLCV_COLS:
            working[col] = pd.to_numeric(working[col], errors="coerce")

        working = working.replace([np.inf, -np.inf], np.nan).dropna(
            subset=list(CANONICAL_OHLCV_COLS)
        )
        if working.empty:
            return None

        working = working.astype(np.float64)

        sanity_mask = (
            (working["Close"] > 0.0)
            & (working["Open"] > 0.0)
            & (working["High"] > 0.0)
            & (working["Low"] > 0.0)
            & (working["Volume"] >= 0.0)
            & (working["High"] >= working["Low"])
            & (working["High"] >= working["Open"])
            & (working["High"] >= working["Close"])
            & (working["Low"] <= working["Open"])
            & (working["Low"] <= working["Close"])
        )
        working = working.loc[sanity_mask].copy()

        if len(working) < 5:
            logger.debug(
                f"Ticker '{ticker}' discarded by sanity check: only {len(working)} valid bars (< 5 required)."
            )
            return None

        return working

    def _extract_ticker_frames_from_yf_download(
        self,
        raw_df: pd.DataFrame,
        batch_tickers: List[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, pd.DataFrame]:
        """
        Normalizes both single-ticker and multi-ticker `yfinance.download` DataFrames
        into clean per-ticker DataFrames keyed by ticker symbol.
        """
        extracted: Dict[str, pd.DataFrame] = {}
        if raw_df is None or raw_df.empty:
            return extracted

        if isinstance(raw_df.columns, pd.MultiIndex):
            level_0_values = {str(v).upper() for v in raw_df.columns.get_level_values(0)}
            level_1_values = {str(v).upper() for v in raw_df.columns.get_level_values(1)}

            for ticker in batch_tickers:
                ticker_upper = ticker.upper()
                sub_df: Optional[pd.DataFrame] = None

                if ticker_upper in level_0_values:
                    sub_df = raw_df[ticker].copy()
                elif ticker_upper in level_1_values:
                    sub_df = raw_df.xs(ticker, axis=1, level=1).copy()

                if sub_df is not None:
                    clean_df = self._sanitize_ohlcv_frame(
                        ticker=ticker_upper,
                        df=sub_df,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    if clean_df is not None:
                        extracted[ticker_upper] = clean_df
        else:
            if len(batch_tickers) == 1:
                only_ticker = batch_tickers[0].upper()
                clean_df = self._sanitize_ohlcv_frame(
                    ticker=only_ticker,
                    df=raw_df,
                    start_date=start_date,
                    end_date=end_date,
                )
                if clean_df is not None:
                    extracted[only_ticker] = clean_df

        return extracted

    def fetch_daily_ohlcv_batch(
        self,
        tickers: Sequence[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, pd.DataFrame]:
        """
        Downloads daily adjusted OHLCV data in chunks of `settings.yfinance_batch_size` (default 50)
        with SLA-optimized inter-batch sleep jitter (`random.uniform(0.15, 0.35)` seconds) and
        exponential backoff retries (`settings.yfinance_max_retries`).
        """
        if start_date > end_date:
            raise DataIngestionError(
                f"Invalid date range: start_date ({start_date}) > end_date ({end_date})."
            )

        normalized_tickers = self._deduplicate_preserving_order(
            [self._normalize_symbol(t) for t in tickers if t and t.strip()]
        )
        if not normalized_tickers:
            return {}

        batch_size = max(1, self.settings.yfinance_batch_size)
        max_retries = max(1, self.settings.yfinance_max_retries)
        base_backoff = self.settings.yfinance_base_backoff_sec

        # yfinance `end` is exclusive; add 1 calendar day to include `end_date` EOD bar
        yf_end_exclusive = end_date + timedelta(days=1)

        batches: List[List[str]] = [
            normalized_tickers[i : i + batch_size]
            for i in range(0, len(normalized_tickers), batch_size)
        ]

        results: Dict[str, pd.DataFrame] = {}

        for batch_idx, batch in enumerate(batches):
            if batch_idx > 0:
                time.sleep(random.uniform(0.15, 0.35))

            batch_success = False
            last_error: Optional[Exception] = None

            for attempt in range(max_retries):
                try:
                    raw_df = yf.download(
                        tickers=batch,
                        start=start_date.isoformat(),
                        end=yf_end_exclusive.isoformat(),
                        interval="1d",
                        auto_adjust=True,
                        group_by="ticker",
                        threads=True,
                        progress=False,
                    )
                    batch_frames = self._extract_ticker_frames_from_yf_download(
                        raw_df=raw_df,
                        batch_tickers=batch,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    results.update(batch_frames)
                    batch_success = True
                    break
                except Exception as exc:
                    last_error = exc
                    delay = base_backoff * (2**attempt) + random.uniform(0.0, 0.35)
                    logger.warning(
                        f"yfinance batch {batch_idx + 1}/{len(batches)} failed on attempt "
                        f"{attempt + 1}/{max_retries}: {exc}. Retrying in {delay:.2f}s..."
                    )
                    if attempt < max_retries - 1:
                        time.sleep(delay)

            if not batch_success and last_error is not None:
                raise DataIngestionError(
                    f"Exhausted {max_retries} retries fetching OHLCV batch {batch_idx + 1}/{len(batches)}: {last_error}"
                ) from last_error

        return results

    def fetch_index_constituents(self, index_config: IndexConfigSchema) -> List[str]:
        """
        Resolves constituent tickers for `index_config.index_id`:
        1. Primary Source (Always First): Dynamically fetches the full live constituent list from
           the web (iShares `IWM` ETF holdings CSV for `RUT_2000`; Wikipedia S&P 400 / S&P 500
           tables for `SP_400` / `SP_500`).
        2. Secondary Fallback (Only if live HTTP fetch fails): Searches for a local CSV/TXT
           fallback file under `config/constituents/` or `config/` regardless of row count.
           If no local fallback file exists or is empty, logs an ERROR and raises `DataIngestionError`.
        """
        index_id = index_config.index_id.strip().upper()

        # 1. Primary Source: Live HTTP Constituent Fetch
        try:
            if index_id in ("RUT_2000", "RUT", "IWM") or index_config.tier == IndexTier.SMALL_CAP:
                live_tickers = self._fetch_ishares_iwm_tickers()
                logger.info(
                    f"Loaded {len(live_tickers)} live constituents for '{index_id}' from iShares IWM holdings CSV."
                )
                return live_tickers

            if index_id in ("SP_400", "MID", "MDY") or index_config.tier == IndexTier.MID_CAP:
                live_tickers = self._fetch_wikipedia_table_tickers(
                    self.WIKIPEDIA_SP400_URL, "Symbol"
                )
                logger.info(
                    f"Loaded {len(live_tickers)} live constituents for '{index_id}' from Wikipedia S&P 400 table."
                )
                return live_tickers

            if index_id in ("SP_500", "SPX", "SPY") or index_config.tier == IndexTier.LARGE_CAP:
                live_tickers = self._fetch_wikipedia_table_tickers(
                    self.WIKIPEDIA_SP500_URL, "Symbol"
                )
                logger.info(
                    f"Loaded {len(live_tickers)} live constituents for '{index_id}' from Wikipedia S&P 500 table."
                )
                return live_tickers

            raise DataIngestionError(
                f"Unrecognized index_id '{index_id}' and tier '{index_config.tier}' for live HTTP fetch."
            )
        except Exception as live_exc:
            logger.warning(
                f"Live HTTP constituent fetch for index '{index_id}' failed ({live_exc}). "
                f"Searching for local CSV/TXT fallback file..."
            )

        # 2. Secondary Fallback: Local CSV/TXT File (Regardless of Row Count)
        fallback_tickers = self._load_local_fallback_constituents(index_config)
        if fallback_tickers:
            return fallback_tickers

        error_msg = (
            f"CRITICAL: Live constituent fetch failed for index '{index_id}' and no valid local "
            f"fallback file was found under '{self.settings.base_dir / 'config'}'."
        )
        logger.error(error_msg)
        raise DataIngestionError(error_msg)

    def _load_local_fallback_constituents(self, index_config: IndexConfigSchema) -> List[str]:
        """
        Searches for local CSV/TXT constituent files under `config/constituents/` and `config/`
        regardless of row count.
        """
        index_id = index_config.index_id.strip().upper()
        alias_prefix = index_id.split("_")[0]
        tier_alias = (
            "RUT"
            if index_config.tier == IndexTier.SMALL_CAP
            else ("MID" if index_config.tier == IndexTier.MID_CAP else "SPX")
        )
        base_dir = self.settings.base_dir

        csv_candidates: List[Path] = [
            base_dir / "config" / "constituents" / f"{index_id}.csv",
            base_dir / "config" / "constituents" / f"{alias_prefix}.csv",
            base_dir / "config" / "constituents" / f"{tier_alias}.csv",
        ]
        for csv_path in csv_candidates:
            if csv_path.is_file():
                try:
                    df_csv = pd.read_csv(csv_path)
                    if not df_csv.empty:
                        col_name = (
                            "ticker" if "ticker" in df_csv.columns else str(df_csv.columns[0])
                        )
                        tickers = self._deduplicate_preserving_order(
                            [
                                self._normalize_symbol(str(val))
                                for val in df_csv[col_name].dropna().tolist()
                                if self._is_valid_equity_symbol(str(val))
                            ]
                        )
                        if tickers:
                            logger.info(
                                f"Loaded {len(tickers)} fallback constituents for '{index_id}' from {csv_path}."
                            )
                            return tickers
                except Exception as csv_exc:
                    logger.warning(f"Failed reading local fallback CSV {csv_path}: {csv_exc}")

        txt_candidates: List[Path] = [
            base_dir / "config" / f"constituents_{index_id.lower()}.txt",
            base_dir / "config" / f"constituents_{alias_prefix.lower()}.txt",
            base_dir / "config" / "constituents" / f"{index_id.lower()}.txt",
            base_dir / "config" / "constituents" / f"{alias_prefix.lower()}.txt",
        ]
        for txt_path in txt_candidates:
            if txt_path.is_file():
                try:
                    raw_lines = txt_path.read_text(encoding="utf-8").splitlines()
                    tickers = self._deduplicate_preserving_order(
                        [
                            self._normalize_symbol(line)
                            for line in raw_lines
                            if line.strip()
                            and not line.strip().startswith("#")
                            and self._is_valid_equity_symbol(line)
                        ]
                    )
                    if tickers:
                        logger.info(
                            f"Loaded {len(tickers)} fallback constituents for '{index_id}' from {txt_path}."
                        )
                        return tickers
                except Exception as txt_exc:
                    logger.warning(f"Failed reading local fallback TXT {txt_path}: {txt_exc}")

        return []

    def _fetch_ishares_iwm_tickers(self) -> List[str]:
        """
        Downloads the official iShares Russell 2000 ETF (`IWM`) holdings CSV via `httpx.Client`,
        dynamically locates the header row containing `"Ticker"` and `"Asset Class"`,
        filters strictly to `Asset Class == "Equity"`, normalizes `.` to `-`, excludes
        non-equity symbols, and deduplicates preserving order.
        """
        headers = {
            "User-Agent": self.HTTP_USER_AGENT,
            "Accept": "text/csv,text/plain,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
            response = client.get(self.ISHARES_IWM_CSV_URL)
            response.raise_for_status()
            csv_text = response.text.lstrip("\ufeff")

        lines = csv_text.splitlines()
        header_idx: Optional[int] = None
        for idx, line in enumerate(lines):
            if "Ticker" in line and "Asset Class" in line:
                header_idx = idx
                break

        if header_idx is None:
            raise DataIngestionError(
                "iShares IWM CSV header row containing 'Ticker' and 'Asset Class' not found."
            )

        csv_body = "\n".join(lines[header_idx:])
        reader = csv.DictReader(StringIO(csv_body))
        if not reader.fieldnames:
            raise DataIngestionError("iShares IWM CSV DictReader found no column fieldnames.")

        field_map = {name.strip().lower(): name for name in reader.fieldnames if name}
        ticker_col = field_map.get("ticker")
        asset_class_col = field_map.get("asset class")

        if not ticker_col or not asset_class_col:
            raise DataIngestionError(
                f"iShares IWM CSV missing required 'Ticker' or 'Asset Class' columns (found {reader.fieldnames})."
            )

        extracted_tickers: List[str] = []
        for row in reader:
            raw_asset_class = str(row.get(asset_class_col) or "").strip()
            if raw_asset_class.lower() != "equity":
                continue

            raw_ticker = str(row.get(ticker_col) or "").strip()
            if not self._is_valid_equity_symbol(raw_ticker):
                continue

            normalized_ticker = self._normalize_symbol(raw_ticker)
            extracted_tickers.append(normalized_ticker)

        deduped = self._deduplicate_preserving_order(extracted_tickers)
        if not deduped:
            raise DataIngestionError("iShares IWM CSV parsed 0 valid equity tickers.")

        return deduped

    def _fetch_wikipedia_table_tickers(self, url: str, symbol_column: str) -> List[str]:
        headers = {
            "User-Agent": self.HTTP_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            html_text = response.text

        tables = pd.read_html(StringIO(html_text))
        for tbl in tables:
            cols_map = {str(c).strip().lower(): c for c in tbl.columns}
            for target_col in (symbol_column.lower(), "symbol", "ticker", "ticker symbol"):
                if target_col in cols_map:
                    raw_series = tbl[cols_map[target_col]].dropna().astype(str).tolist()
                    cleaned = self._deduplicate_preserving_order(
                        [
                            self._normalize_symbol(val)
                            for val in raw_series
                            if self._is_valid_equity_symbol(val)
                        ]
                    )
                    if cleaned:
                        return cleaned

        raise DataIngestionError(f"No valid constituent symbol table found at {url}.")

    def fetch_current_quotes_spread_proxy(self, tickers: Sequence[str]) -> Dict[str, float]:
        """
        Queries `yf.Ticker(t).fast_info` / `.info` for `bid` and `ask` prices,
        computing relative spread `(ask - bid) / ((ask + bid) / 2)`.
        Gracefully returns `0.0` if EOD/after-hours quote fields are zero, missing, or unreachable.
        """
        spreads: Dict[str, float] = {}
        for raw_ticker in tickers:
            ticker = self._normalize_symbol(raw_ticker)
            if not ticker:
                continue

            spread_val = 0.0
            try:
                yf_obj = yf.Ticker(ticker)
                bid = 0.0
                ask = 0.0

                fast_info = getattr(yf_obj, "fast_info", None)
                if fast_info is not None:
                    try:
                        bid = float(fast_info.get("bid", 0.0) or 0.0)
                        ask = float(fast_info.get("ask", 0.0) or 0.0)
                    except Exception:
                        bid, ask = 0.0, 0.0

                if (bid <= 0.0 or ask <= 0.0) and hasattr(yf_obj, "info"):
                    info_dict = yf_obj.info or {}
                    bid = float(info_dict.get("bid", 0.0) or 0.0)
                    ask = float(info_dict.get("ask", 0.0) or 0.0)

                if bid > 0.0 and ask >= bid:
                    mid = 0.5 * (ask + bid)
                    if mid > 0.0:
                        spread_val = round((ask - bid) / mid, 6)
            except Exception as exc:
                logger.debug(f"Spread proxy fallback to 0.0 for '{ticker}': {exc}")
                spread_val = 0.0

            spreads[ticker] = spread_val

        return spreads


# =============================================================================
# 4. POINT-IN-TIME INCREMENTAL INGESTION PIPELINE
# =============================================================================


class DataIngestionPipeline:
    """
    Orchestrates Point-in-Time (PiT) incremental OHLCV synchronization:
    1. Resolves active index rosters + mandatory benchmark ETF tickers.
    2. Applies Pre-Filtering Portfolio Exclusion Gate (while never excluding benchmarks).
    3. Routes tickers into Cold-Start Full Pull (~750 calendar days) vs Delta Rolling Pull (~10 calendar days).
    4. Automatically catches `CorporateActionSplitDetectedError` at `t-1`, purges stale cache,
       and re-hydrates a clean full 500-trading-day history.
    """

    FULL_LOOKBACK_CALENDAR_DAYS = 750
    DELTA_LOOKBACK_CALENDAR_DAYS = 10
    STALE_CACHE_THRESHOLD_DAYS = 15

    def __init__(
        self,
        provider: Optional[MarketDataProvider] = None,
        repository: Optional[MarketDataRepository] = None,
        settings: Optional[SystemSettings] = None,
    ) -> None:
        self.settings: SystemSettings = settings or get_settings()
        self.provider: MarketDataProvider = provider or YFinanceMarketDataProvider(
            settings=self.settings
        )
        self.repository: MarketDataRepository = repository or ParquetMarketDataRepository(
            settings=self.settings
        )

    def sync_universe_ohlcv(
        self,
        active_indices: Dict[str, IndexConfigSchema],
        excluded_tickers: Set[str],
        as_of_date: date,
    ) -> Dict[str, List[str]]:
        """
        Synchronizes rolling Parquet caches for all eligible constituents and benchmarks up to `as_of_date`.
        Returns a dictionary mapping `index_id -> List[str]` of synced, valid constituent tickers.
        """
        if not active_indices:
            return {}

        normalized_excluded = {t.strip().upper() for t in excluded_tickers if t and t.strip()}
        benchmark_tickers = {
            cfg.benchmark_ticker.strip().upper()
            for cfg in active_indices.values()
            if cfg.is_active
        }

        index_to_candidate_tickers: Dict[str, List[str]] = {}
        all_required_tickers: Set[str] = set(benchmark_tickers)

        for idx_id, cfg in active_indices.items():
            if not cfg.is_active:
                continue
            raw_constituents = self.provider.fetch_index_constituents(cfg)
            filtered_constituents = [
                t.strip().upper()
                for t in raw_constituents
                if t.strip().upper() not in normalized_excluded
            ]
            deduped_constituents = list(dict.fromkeys(filtered_constituents))
            index_to_candidate_tickers[idx_id] = deduped_constituents
            all_required_tickers.update(deduped_constituents)

        # Categorize into Full Cold-Start vs Delta Rolling-Window buckets
        cold_start_tickers: List[str] = []
        delta_tickers: List[str] = []

        for ticker in sorted(all_required_tickers):
            latest_cached = self.repository.get_latest_cached_date(ticker)
            if (
                latest_cached is None
                or (as_of_date - latest_cached).days > self.STALE_CACHE_THRESHOLD_DAYS
            ):
                cold_start_tickers.append(ticker)
            else:
                delta_tickers.append(ticker)

        synced_tickers: Set[str] = set()

        # 1. Execute Cold-Start Full Pull (~500 trading days / ~750 calendar days)
        if cold_start_tickers:
            full_start = as_of_date - timedelta(days=self.FULL_LOOKBACK_CALENDAR_DAYS)
            logger.info(
                f"Executing full cold-start OHLCV pull ({full_start} -> {as_of_date}) "
                f"for {len(cold_start_tickers)} tickers."
            )
            full_frames = self.provider.fetch_daily_ohlcv_batch(
                tickers=cold_start_tickers,
                start_date=full_start,
                end_date=as_of_date,
            )
            for ticker, df in full_frames.items():
                try:
                    self._upsert_to_repository(ticker, df)
                    synced_tickers.add(ticker)
                except StorageError as exc:
                    logger.warning(f"Failed to persist cold-start history for '{ticker}': {exc}")

        # 2. Execute Delta Rolling-Window Pull (~10 calendar days overlap for t-1 split guard)
        if delta_tickers:
            delta_start = as_of_date - timedelta(days=self.DELTA_LOOKBACK_CALENDAR_DAYS)
            logger.info(
                f"Executing incremental delta OHLCV pull ({delta_start} -> {as_of_date}) "
                f"for {len(delta_tickers)} cached tickers."
            )
            delta_frames = self.provider.fetch_daily_ohlcv_batch(
                tickers=delta_tickers,
                start_date=delta_start,
                end_date=as_of_date,
            )

            split_recovery_queue: List[str] = []
            for ticker, df in delta_frames.items():
                try:
                    self._upsert_to_repository(ticker, df)
                    synced_tickers.add(ticker)
                except CorporateActionSplitDetectedError as split_exc:
                    logger.warning(
                        f"Corporate action / split detected at t-1 for '{ticker}' ({split_exc}). "
                        f"Purging stale Parquet cache and queuing full 500-day re-fetch."
                    )
                    self.repository.purge_ticker_history(ticker)
                    split_recovery_queue.append(ticker)
                except StorageError as exc:
                    logger.warning(f"Storage error during delta upsert for '{ticker}': {exc}")

            # 3. Automatic t-1 Split Recovery Full Pull
            if split_recovery_queue:
                full_start = as_of_date - timedelta(days=self.FULL_LOOKBACK_CALENDAR_DAYS)
                recovered_frames = self.provider.fetch_daily_ohlcv_batch(
                    tickers=split_recovery_queue,
                    start_date=full_start,
                    end_date=as_of_date,
                )
                for ticker, clean_df in recovered_frames.items():
                    try:
                        self.repository.save_ohlcv(ticker, clean_df)
                        synced_tickers.add(ticker)
                    except StorageError as exc:
                        logger.error(
                            f"Failed to save post-split re-hydrated history for '{ticker}': {exc}"
                        )

        # Build verified per-index constituent lists
        verified_index_constituents: Dict[str, List[str]] = {}
        for idx_id, candidates in index_to_candidate_tickers.items():
            verified_index_constituents[idx_id] = [
                t for t in candidates if t in synced_tickers
            ]

        return verified_index_constituents

    def _upsert_to_repository(self, ticker: str, df: pd.DataFrame) -> None:
        if isinstance(self.repository, ParquetMarketDataRepository):
            self.repository.upsert_ohlcv(
                ticker=ticker,
                incoming_df=df,
                max_window_days=self.settings.backtest_lookback_days,
            )
        else:
            self.repository.save_ohlcv(ticker, df)


# =============================================================================
# 5. BACKWARD-COMPATIBLE MULTI-INDEX ORCHESTRATOR & PROVIDER INTERFACES
# =============================================================================


class BaseMarketDataProvider(ABC):
    """
    Backward-compatible MultiIndex provider contract used by existing unit tests
    (`tests/test_quant_engine.py`) and orchestrators.
    """

    @abstractmethod
    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        """Fetches MultiIndex (date, ticker) OHLCV DataFrame for a batch of tickers."""

    @abstractmethod
    def fetch_index_constituents(self, index_id: str) -> List[str]:
        """Returns constituent symbols for the given index identifier."""


class YFinanceProvider(BaseMarketDataProvider):
    """
    Adapter bridging `YFinanceMarketDataProvider` to the `(date, ticker)` MultiIndex
    contract expected by `SmartSlidingWindowOrchestrator`.
    """

    def __init__(
        self,
        chunk_size: int = 50,
        max_retries: int = 4,
        base_backoff_sec: float = 1.5,
        constituent_lists_dir: Path = Path("config/constituents"),
    ) -> None:
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.constituent_lists_dir = constituent_lists_dir
        self._delegate = YFinanceMarketDataProvider()

    def fetch_index_constituents(self, index_id: str) -> List[str]:
        idx_upper = index_id.strip().upper()
        tier = (
            IndexTier.LARGE_CAP
            if idx_upper in ("SP_500", "SPX", "SPY")
            else (
                IndexTier.MID_CAP
                if idx_upper in ("SP_400", "MID", "MDY")
                else IndexTier.SMALL_CAP
            )
        )
        bench = (
            "SPY"
            if tier == IndexTier.LARGE_CAP
            else ("MDY" if tier == IndexTier.MID_CAP else "IWM")
        )
        cfg = IndexConfigSchema(
            index_id=idx_upper,
            display_name=idx_upper,
            benchmark_ticker=bench,
            tier=tier,
            k_stop_atr=2.0,
            k_profit_atr=4.5,
        )
        return self._delegate.fetch_index_constituents(cfg)

    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        per_ticker = self._delegate.fetch_daily_ohlcv_batch(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date_inclusive,
        )
        if not per_ticker:
            return pd.DataFrame()

        frames: List[pd.DataFrame] = []
        for ticker, df in per_ticker.items():
            sub = df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            ).copy()
            sub.index.name = "date"
            sub = sub.reset_index()
            sub["ticker"] = ticker
            sub["dividends"] = 0.0
            sub["splits"] = 0.0
            frames.append(sub)

        combined = pd.concat(frames, axis=0)
        return combined.set_index(["date", "ticker"]).sort_index()


YFinanceDataProvider = YFinanceProvider


class SmartSlidingWindowOrchestrator:
    """
    Maintains a rolling W-day historical OHLCV window (default 500 trading days)
    stored in Apache Parquet with daily 2-day Delta Fetches and t-1 Split Guard.
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
        cached_df = self._load_cached_window(as_of_date)

        if cached_df.empty:
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
        if delta_df.empty:
            return set()

        flagged_tickers: Set[str] = set()

        if "splits" in delta_df.columns and "dividends" in delta_df.columns:
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

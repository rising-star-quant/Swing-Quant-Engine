from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from io import StringIO
import logging
from pathlib import Path
import random
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple
import urllib.request

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

CANONICAL_OHLCV_COLS: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")

FALLBACK_LIQUID_CONSTITUENTS: Dict[str, List[str]] = {
    "RUT_2000": [
        "ANF", "APPF", "ATI", "AVAV", "AXON", "BOOT", "CELH", "comm", "CRS", "CVLT",
        "CWST", "DUOL", "EAT", "ELF", "ENS", "EXLS", "FAB", "FIX", "FN", "FTAI",
        "GKOS", "GTLS", "HALO", "HLNE", "HQY", "IESC", "INSM", "ITCI", "JXN", "KBH",
        "KNF", "KRYS", "LNTH", "LNW", "MOD", "MTH", "MTZ", "MUSA", "NOVT", "NXT",
        "ONTF", "OSCR", "PCVX", "PI", "POWL", "PRIM", "PSN", "RBA", "RMBS", "RVMD",
        "SANM", "SFM", "SIG", "SITM", "SKY", "SMCI", "SPXC", "SSD", "STEP", "TMDX",
        "TNET", "TOL", "UFPT", "UPBD", "URBN", "VCTR", "VRRM", "WDFC", "WFRD", "WING",
    ],
    "SP_400": [
        "AAON", "ACM", "AGCO", "AIT", "ALK", "ALLY", "AMED", "AMKR", "AN", "ARMK",
        "ARMK", "ASGN", "ASH", "AVNT", "AVT", "AYI", "AZEK", "BC", "BERY", "BJ",
        "BLD", "BRBR", "BURL", "BWXT", "CACI", "CAR", "CASY", "CBT", "CCK", "CFR",
        "CHE", "CHH", "CIEN", "CLF", "CLH", "CMC", "CNM", "CNXC", "COHR", "COLB",
        "COLM", "CORT", "CRI", "CROX", "CRS", "CSL", "CUBE", "CUZ", "CVLT", "CW",
        "DAR", "DCI", "DECK", "DINO", "DKS", "DLB", "DOCS", "DT", "EGP", "EME",
    ],
    "SP_500": [
        "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
        "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALL",
        "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN", "ANET",
        "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK-B", "BSX",
        "C", "CAT", "CB", "CCI", "CDNS", "CEG", "CF", "CFG", "CHD", "CHTR",
        "CI", "CINF", "CL", "CLX", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC",
    ],
}


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
    - Chunked batch downloading with inter-batch jitter.
    - Exponential backoff retry loops.
    - Point-in-Time (PiT) date boundary truncation and OHLCV bar sanity checks.
    - Multi-source index constituent resolution with local override and curated fallback rosters.
    """

    WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    WIKIPEDIA_SP400_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    ISHARES_IWM_CSV_URL = (
        "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
        "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    )
    HTTP_USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalizes equity symbol for Yahoo Finance compatibility (e.g., BRK.B -> BRK-B)."""
        return symbol.strip().upper().replace(".", "-").replace("/", "-")

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
        - Close > 0, Open > 0, Low > 0, Volume > 0 (drops rows where Close or Volume is NaN or <= 0)
        - Returns None if fewer than 5 valid trading bars remain.
        """
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return None

        working = df.copy()

        # Map case-insensitive column names to canonical ["Open", "High", "Low", "Close", "Volume"]
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

        # Normalize DatetimeIndex to timezone-naive UTC dates
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

        # Drop NaT index entries, deduplicate keeping last, sort ascending
        working = working.loc[~working.index.isna()]
        if working.index.has_duplicates:
            working = working[~working.index.duplicated(keep="last")]
        working = working.sort_index(ascending=True)

        # Enforce strict Point-in-Time date bounds
        if start_date is not None:
            working = working.loc[working.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            working = working.loc[working.index <= pd.Timestamp(end_date)]

        if working.empty:
            return None

        # Coerce to float64 and drop NaN / infinite rows
        for col in CANONICAL_OHLCV_COLS:
            working[col] = pd.to_numeric(working[col], errors="coerce")

        working = working.replace([np.inf, -np.inf], np.nan).dropna(
            subset=list(CANONICAL_OHLCV_COLS)
        )
        if working.empty:
            return None

        working = working.astype(np.float64)

        # Enforce numerical sanity gates (Close > 0, Volume > 0, High/Low geometry)
        sanity_mask = (
            (working["Close"] > 0.0)
            & (working["Open"] > 0.0)
            & (working["High"] > 0.0)
            & (working["Low"] > 0.0)
            & (working["Volume"] > 0.0)
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
        Downloads daily adjusted OHLCV data in batches of `settings.yfinance_batch_size`
        with exponential backoff retries and inter-batch jitter.
        """
        if start_date > end_date:
            raise DataIngestionError(
                f"Invalid date range: start_date ({start_date}) > end_date ({end_date})."
            )

        normalized_tickers = sorted(
            {self._normalize_symbol(t) for t in tickers if t and t.strip()}
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
                time.sleep(random.uniform(0.3, 0.8))

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
                    delay = base_backoff * (2**attempt) + random.uniform(0.0, 0.5)
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
        1. Checks local text override `config/constituents_{index_id.lower()}.txt` (one ticker per line).
        2. Checks local CSV roster `config/constituents/{index_id}.csv` if present.
        3. Otherwise queries public Wikipedia / iShares constituent endpoints via HTTP with User-Agent,
           falling back gracefully to a curated liquid index roster if remote endpoints are unreachable.
        """
        index_id = index_config.index_id.strip().upper()
        base_dir = self.settings.base_dir

        # 1. Check local text override file: config/constituents_{index_id.lower()}.txt
        txt_override_path = base_dir / "config" / f"constituents_{index_id.lower()}.txt"
        if txt_override_path.exists():
            raw_lines = txt_override_path.read_text(encoding="utf-8").splitlines()
            tickers = sorted(
                {
                    self._normalize_symbol(line)
                    for line in raw_lines
                    if line.strip() and not line.strip().startswith("#")
                }
            )
            if tickers:
                logger.info(
                    f"Loaded {len(tickers)} constituents for '{index_id}' from {txt_override_path}."
                )
                return tickers

        # 2. Check local CSV roster file in config/constituents/{index_id}.csv
        alias_prefix = index_id.split("_")[0]
        csv_candidates = [
            base_dir / "config" / "constituents" / f"{index_id}.csv",
            base_dir / "config" / "constituents" / f"{alias_prefix}.csv",
        ]
        for csv_path in csv_candidates:
            if csv_path.exists():
                try:
                    df_csv = pd.read_csv(csv_path)
                    col_name = "ticker" if "ticker" in df_csv.columns else df_csv.columns[0]
                    tickers = sorted(
                        {
                            self._normalize_symbol(str(val))
                            for val in df_csv[col_name].dropna().tolist()
                            if str(val).strip()
                        }
                    )
                    if tickers:
                        logger.info(
                            f"Loaded {len(tickers)} constituents for '{index_id}' from {csv_path}."
                        )
                        return tickers
                except Exception as exc:
                    logger.warning(f"Failed reading local CSV constituent roster {csv_path}: {exc}")

        # 3. Fetch public constituent tables with User-Agent header
        try:
            if index_id in ("SP_500", "SPX", "SPY") or index_config.tier == IndexTier.LARGE_CAP:
                return self._fetch_wikipedia_table_tickers(self.WIKIPEDIA_SP500_URL, "Symbol")
            if index_id in ("SP_400", "MID", "MDY") or index_config.tier == IndexTier.MID_CAP:
                return self._fetch_wikipedia_table_tickers(self.WIKIPEDIA_SP400_URL, "Symbol")
            if index_id in ("RUT_2000", "RUT", "IWM") or index_config.tier == IndexTier.SMALL_CAP:
                return self._fetch_ishares_iwm_tickers()
        except Exception as exc:
            logger.warning(
                f"Remote constituent fetch for index '{index_id}' failed ({exc}). "
                f"Using curated liquid fallback roster."
            )

        fallback_key = (
            "SP_500"
            if index_config.tier == IndexTier.LARGE_CAP
            else ("SP_400" if index_config.tier == IndexTier.MID_CAP else "RUT_2000")
        )
        fallback_list = FALLBACK_LIQUID_CONSTITUENTS.get(
            index_id, FALLBACK_LIQUID_CONSTITUENTS[fallback_key]
        )
        return sorted({self._normalize_symbol(t) for t in fallback_list})

    def _fetch_wikipedia_table_tickers(self, url: str, symbol_column: str) -> List[str]:
        req = urllib.request.Request(url, headers={"User-Agent": self.HTTP_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html_text = resp.read().decode("utf-8", errors="replace")

        tables = pd.read_html(StringIO(html_text))
        for tbl in tables:
            cols_Map = {str(c).strip().lower(): c for c in tbl.columns}
            for target_col in (symbol_column.lower(), "symbol", "ticker", "ticker symbol"):
                if target_col in cols_Map:
                    raw_series = tbl[cols_Map[target_col]].dropna().astype(str).tolist()
                    cleaned = sorted(
                        {
                            self._normalize_symbol(val)
                            for val in raw_series
                            if val.strip() and len(val.strip()) <= 10
                        }
                    )
                    if cleaned:
                        return cleaned

        raise DataIngestionError(f"No constituent symbol table found at {url}.")

    def _fetch_ishares_iwm_tickers(self) -> List[str]:
        req = urllib.request.Request(
            self.ISHARES_IWM_CSV_URL,
            headers={"User-Agent": self.HTTP_USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            csv_text = resp.read().decode("utf-8", errors="replace")

        lines = csv_text.splitlines()
        header_idx = next(
            (i for i, line in enumerate(lines) if line.startswith("Ticker,")),
            None,
        )
        if header_idx is None:
            raise DataIngestionError("iShares IWM CSV header 'Ticker,' not found.")

        df_iwm = pd.read_csv(StringIO("\n".join(lines[header_idx:])))
        if "Ticker" not in df_iwm.columns:
            raise DataIngestionError("iShares IWM CSV missing 'Ticker' column.")

        raw_tickers = df_iwm["Ticker"].dropna().astype(str).tolist()
        cleaned = sorted(
            {
                self._normalize_symbol(t)
                for t in raw_tickers
                if t.strip()
                and t.strip() != "-"
                and t.strip().replace("-", "").isalnum()
                and len(t.strip()) <= 8
            }
        )
        if not cleaned:
            raise DataIngestionError("iShares IWM CSV parsed 0 valid equity tickers.")
        return cleaned

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
    3. Routes tickers into Cold-Start Full Pull (~730 calendar days) vs Delta Rolling Pull (~10 calendar days).
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
            index_to_candidate_tickers[idx_id] = sorted(set(filtered_constituents))
            all_required_tickers.update(index_to_candidate_tickers[idx_id])

        # Categorize into Full Cold-Start vs Delta Rolling-Window buckets
        cold_start_tickers: List[str] = []
        delta_tickers: List[str] = []

        for ticker in sorted(all_required_tickers):
            latest_cached = self.repository.get_latest_cached_date(ticker)
            if latest_cached is None or (as_of_date - latest_cached).days > self.STALE_CACHE_THRESHOLD_DAYS:
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
        chunk_size: int = 100,
        max_retries: int = 3,
        base_backoff_sec: float = 2.0,
        constituent_lists_dir: Path = Path("config/constituents"),
    ) -> None:
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.constituent_lists_dir = constituent_lists_dir
        self._delegate = YFinanceMarketDataProvider()

    def fetch_index_constituents(self, index_id: str) -> List[str]:
        roster_file = self.constituent_lists_dir / f"{index_id}.csv"
        if roster_file.exists():
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

        dummy_cfg = IndexConfigSchema(
            index_id=index_id,
            display_name=index_id,
            benchmark_ticker="IWM",
            tier=IndexTier.SMALL_CAP,
            k_stop_atr=2.0,
            k_profit_atr=4.5,
        )
        return self._delegate.fetch_index_constituents(dummy_cfg)

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

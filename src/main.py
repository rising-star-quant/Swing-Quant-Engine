from __future__ import annotations

import argparse
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
import html
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
import time
from typing import Any, Dict, IO, List, Optional, Set, Tuple
from uuid import UUID
from zoneinfo import ZoneInfo

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

import pandas as pd

try:
    from src.config import (
        SystemSettings,
        get_active_indices,
        get_settings,
        load_index_registry,
    )
    from src.data_ingestion import (
        DataIngestionPipeline,
        MarketDataProvider,
        YFinanceMarketDataProvider,
    )
    from src.notifier import TelegramNotifier, TenantDailyReportPayload
    from src.quant_engine import (
        FeatureEngineer,
        MetaLabelingBacktestEngine,
        PrimaryScreeningEngine,
        TenantPortfolioReconciler,
    )
    from src.schemas import (
        ClosedTradeAuditSchema,
        DirectionalSignalSchema,
        IndexConfigSchema,
        MetaLabeledSignalSchema,
        MultiTenantStateStoreSchema,
        TripleBarrierPositionSchema,
        VirtualPortfolioLedgerSchema,
    )
    from src.storage import (
        DEFAULT_ADMIN_PORTFOLIO_ID,
        DEFAULT_ADMIN_USER_ID,
        JsonPortfolioStateRepository,
        MarketDataRepository,
        ParquetMarketDataRepository,
        PortfolioStateRepository,
    )
    from src.api_exporter import (
        PRIMARY_SIRIX_USER_ID,
        SirixCloudExporter,
        load_user_guardrails,
    )
except ImportError:
    from config import (  # type: ignore[no-redef]
        SystemSettings,
        get_active_indices,
        get_settings,
        load_index_registry,
    )
    from data_ingestion import (  # type: ignore[no-redef]
        DataIngestionPipeline,
        MarketDataProvider,
        YFinanceMarketDataProvider,
    )
    from notifier import TelegramNotifier, TenantDailyReportPayload  # type: ignore[no-redef]
    from quant_engine import (  # type: ignore[no-redef]
        FeatureEngineer,
        MetaLabelingBacktestEngine,
        PrimaryScreeningEngine,
        TenantPortfolioReconciler,
    )
    from schemas import (  # type: ignore[no-redef]
        ClosedTradeAuditSchema,
        DirectionalSignalSchema,
        IndexConfigSchema,
        MetaLabeledSignalSchema,
        MultiTenantStateStoreSchema,
        TripleBarrierPositionSchema,
        VirtualPortfolioLedgerSchema,
    )
    from storage import (  # type: ignore[no-redef]
        DEFAULT_ADMIN_PORTFOLIO_ID,
        DEFAULT_ADMIN_USER_ID,
        JsonPortfolioStateRepository,
        MarketDataRepository,
        ParquetMarketDataRepository,
        PortfolioStateRepository,
    )
    from api_exporter import (  # type: ignore[no-redef]
        PRIMARY_SIRIX_USER_ID,
        SirixCloudExporter,
        load_user_guardrails,
    )


# =============================================================================
# 1. STRUCTURED LOGGING CONFIGURATION & CUSTOM PIPELINE EXCEPTIONS
# =============================================================================


class SettlementDataDelayError(RuntimeError):
    """
    Raised when upstream T_0 settlement coverage remains below the mandatory
    98.0% completeness threshold after exhausting all automated backoff retries
    (`FAILED_DATA_DELAY`).
    """


def configure_logging(level: str = "INFO") -> logging.Logger:
    """
    Configures clean timestamped UTC stdout logging.
    """
    numeric_level = getattr(logging, level.strip().upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    formatter.converter = time.gmtime

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    if not root_logger.handlers:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

    return logging.getLogger("SwingQuantEngine.Orchestrator")


# =============================================================================
# 2. NYSE MARKET CALENDAR GATE & ATOMIC PERSISTENCE UTILITIES
# =============================================================================


def _compute_easter_sunday(year: int) -> date:
    """Computes Gregorian Easter Sunday for deterministic Good Friday calculation."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed_nyse_holiday(dt: date) -> date:
    """Shifts Saturday holidays to Friday and Sunday holidays to Monday per NYSE rules."""
    if dt.weekday() == 5:
        return dt - timedelta(days=1)
    if dt.weekday() == 6:
        return dt + timedelta(days=1)
    return dt


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Returns the n-th occurrence (1-indexed) of `weekday` (0=Mon..6=Sun) in (year, month)."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Returns the last occurrence of `weekday` (0=Mon..6=Sun) in (year, month)."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def get_nyse_holidays_for_year(year: int) -> Set[date]:
    """
    Deterministic NYSE full-day holiday calendar for a given calendar year:
    New Year's Day (incl. Dec 31 observance if Jan 1 of year+1 is Saturday),
    MLK Jr. Day, Presidents' Day, Good Friday, Memorial Day, Juneteenth (>= 2022),
    Independence Day, Labor Day, Thanksgiving Day, Christmas Day.
    """
    holidays: Set[date] = set()

    holidays.add(_observed_nyse_holiday(date(year, 1, 1)))
    next_new_year_observed = _observed_nyse_holiday(date(year + 1, 1, 1))
    if next_new_year_observed.year == year:
        holidays.add(next_new_year_observed)

    if year >= 1998:
        holidays.add(_nth_weekday_of_month(year, 1, 0, 3))  # MLK Jr. Day
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))  # Presidents' Day
    holidays.add(_compute_easter_sunday(year) - timedelta(days=2))  # Good Friday
    holidays.add(_last_weekday_of_month(year, 5, 0))  # Memorial Day
    if year >= 2022:
        holidays.add(_observed_nyse_holiday(date(year, 6, 19)))  # Juneteenth
    holidays.add(_observed_nyse_holiday(date(year, 7, 4)))  # Independence Day
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))  # Labor Day
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thanksgiving
    holidays.add(_observed_nyse_holiday(date(year, 12, 25)))  # Christmas Day

    return holidays


def is_nyse_trading_day(check_date: date) -> Tuple[bool, str]:
    """
    Evaluates whether `check_date` is an open NYSE regular trading session.
    Prefers `exchange_calendars` / `pandas_market_calendars` if installed,
    seamlessly falling back to deterministic built-in NYSE rules.
    """
    if check_date.weekday() >= 5:
        return False, "WEEKEND"

    try:
        import exchange_calendars as xcals  # type: ignore[import-not-found]

        xnys = xcals.get_calendar("XNYS")
        is_session = bool(xnys.is_session(pd.Timestamp(check_date)))
        return is_session, ("TRADING_DAY" if is_session else "NYSE_HOLIDAY")
    except Exception as exc:
        logging.getLogger("SwingQuantEngine.Orchestrator").debug(
            f"exchange_calendars unavailable, trying next calendar backend: {exc}"
        )

    try:
        import pandas_market_calendars as mcal  # type: ignore[import-not-found]

        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=check_date, end_date=check_date)
        is_session = not schedule.empty
        return is_session, ("TRADING_DAY" if is_session else "NYSE_HOLIDAY")
    except Exception as exc:
        logging.getLogger("SwingQuantEngine.Orchestrator").debug(
            f"pandas_market_calendars unavailable, using built-in NYSE rules: {exc}"
        )

    holidays = get_nyse_holidays_for_year(check_date.year)
    if check_date in holidays:
        return False, "NYSE_HOLIDAY"
    return True, "TRADING_DAY"


def check_nyse_gate_status(
    target_date: Optional[date] = None,
    force_run: Optional[bool] = None,
) -> Tuple[bool, date, str]:
    """
    Evaluates the current US Eastern (`America/New_York`) date against the NYSE
    calendar and `FORCE_RUN` / `--force-run` override policy.
    """
    ny_tz = ZoneInfo("America/New_York")
    eval_date = target_date or datetime.now(ny_tz).date()

    env_force = os.getenv("FORCE_RUN", "false").strip().lower() == "true"
    effective_force = env_force if force_run is None else bool(force_run)

    market_open, calendar_reason = is_nyse_trading_day(eval_date)
    is_trading_day = market_open or effective_force
    status_note = (
        "FORCE_RUN_OVERRIDE"
        if (not market_open and effective_force)
        else calendar_reason
    )
    return is_trading_day, eval_date, status_note


def evaluate_market_calendar_gate(
    target_date: Optional[date] = None,
    force_run: Optional[bool] = None,
) -> int:
    """
    Stage 2 NYSE Market Calendar Gate (`--check-market-calendar`):
    - Evaluates current date in `America/New_York` timezone (or `target_date` override).
    - Checks `FORCE_RUN` env var / `--force-run` (`true` overrides closed status).
    - Writes `is_trading_day=true|false` to `$GITHUB_OUTPUT` when set.
    - Logs `SKIPPED_MARKET_CLOSED` and exits `0` immediately when market is closed.
    """
    logger = logging.getLogger("SwingQuantEngine.Orchestrator")
    is_trading_day, eval_date, status_note = check_nyse_gate_status(
        target_date=target_date,
        force_run=force_run,
    )

    github_output_path = os.getenv("GITHUB_OUTPUT", "").strip()
    if github_output_path:
        output_file = Path(github_output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("a", encoding="utf-8") as fh:
            fh.write(f"is_trading_day={'true' if is_trading_day else 'false'}\n")
            fh.write(f"nyse_eval_date={eval_date.isoformat()}\n")

    if is_trading_day:
        logger.info(
            f"[Stage 2: PREFLIGHT_VERIFICATION] NYSE Market Calendar Gate PASSED "
            f"(ny_date={eval_date.isoformat()}, status={status_note}, is_trading_day=true)."
        )
    else:
        logger.info(
            f"[Stage 2: PREFLIGHT_VERIFICATION] SKIPPED_MARKET_CLOSED "
            f"(ny_date={eval_date.isoformat()}, reason={status_note}, is_trading_day=false)."
        )

    return 0


def atomic_write_json(target_path: Path, payload: Dict[str, Any]) -> None:
    """
    Atomically persists a JSON object using NamedTemporaryFile + fsync + os.replace
    so downstream consumers (Cloud Run GUI / Git sync) never observe partial writes.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    tmp_path: Optional[Path] = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(target_path.parent),
            prefix=f".{target_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(serialized)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError as cleanup_err:
                logging.getLogger("SwingQuantEngine.Orchestrator").debug(
                    f"Temporary JSON cleanup skipped for {tmp_path}: {cleanup_err}"
                )


def dispatch_cli_failure_alert(
    settings: SystemSettings,
    run_url: Optional[str] = None,
    failed_stage: Optional[str] = None,
    as_of_date: Optional[date] = None,
) -> int:
    """
    Sends high-priority `CRITICAL EOD PIPELINE FAILURE` HTML alert via TelegramNotifier
    when invoked by the GitHub Actions `if: failure()` workflow step.
    """
    logger = logging.getLogger("SwingQuantEngine.Orchestrator")
    notifier = TelegramNotifier(settings=settings)
    now_utc = datetime.now(timezone.utc)
    eval_date = as_of_date or now_utc.date()
    stage_label = (
        failed_stage
        or os.getenv("FAILED_STAGE", "").strip()
        or "GitHub Actions EOD Pipeline"
    )
    resolved_url = (run_url or os.getenv("GITHUB_RUN_URL", "")).strip()

    url_line = (
        f'<b>Workflow Run:</b> <a href="{html.escape(resolved_url, quote=True)}">'
        f"{html.escape(resolved_url)}</a>\n"
        if resolved_url
        else ""
    )
    alert_html = (
        f"🚨 <b>CRITICAL EOD PIPELINE FAILURE</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>UTC Timestamp:</b> <code>{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}</code>\n"
        f"<b>Trading Date:</b> <code>{eval_date.isoformat()}</code>\n"
        f"<b>Failed Stage:</b> <code>{html.escape(stage_label)}</code>\n"
        f"{url_line}"
        f"<i>Zero-Override Protection: Prior day portfolio state was preserved untouched.</i>"
    )

    if not notifier.is_configured:
        logger.warning(
            "Telegram credentials not configured; logged CRITICAL EOD PIPELINE FAILURE locally."
        )
        return 0

    chat_id = str(getattr(settings, "telegram_chat_id", "") or "").strip()
    sent = notifier._send_html_payload(chat_id=chat_id, text=alert_html)
    if sent:
        logger.info("Dispatched CRITICAL EOD PIPELINE FAILURE alert to Telegram.")
    else:
        logger.error("Failed to dispatch CRITICAL EOD PIPELINE FAILURE alert to Telegram.")
    return 0


# =============================================================================
# 3. AUTONOMOUS HEADLESS QUANT PIPELINE ORCHESTRATOR
# =============================================================================


class QuantPipelineOrchestrator:
    """
    Autonomous Headless Daily Execution Worker enforcing the 6-stage Step D.2
    state machine, Global Shared Compute / Isolated Tenant Reconciliation
    architecture, and the < 15-minute (900s) execution SLA.
    """

    SLA_MAX_SECONDS = 900.0
    MIN_T0_COVERAGE_RATIO = 0.98

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        provider: Optional[MarketDataProvider] = None,
        market_repo: Optional[MarketDataRepository] = None,
        state_repo: Optional[PortfolioStateRepository] = None,
        notifier: Optional[TelegramNotifier] = None,
    ) -> None:
        self.settings: SystemSettings = settings or get_settings()
        self.logger = logging.getLogger("SwingQuantEngine.Orchestrator")

        self.provider: MarketDataProvider = provider or YFinanceMarketDataProvider(
            settings=self.settings
        )
        self.market_repo: MarketDataRepository = market_repo or ParquetMarketDataRepository(
            settings=self.settings
        )
        self.state_repo: PortfolioStateRepository = state_repo or JsonPortfolioStateRepository(
            settings=self.settings
        )
        self.notifier: TelegramNotifier = notifier or TelegramNotifier(settings=self.settings)

        self.ingestion_pipeline = DataIngestionPipeline(
            provider=self.provider,
            repository=self.market_repo,
            settings=self.settings,
        )
        self.screening_engine = PrimaryScreeningEngine(settings=self.settings)
        self.backtest_engine = MetaLabelingBacktestEngine(settings=self.settings)
        self.reconciler = TenantPortfolioReconciler(settings=self.settings)
        self.cloud_exporter = SirixCloudExporter(market_repo=self.market_repo)

    def _is_effective_dry_run(self) -> bool:
        env_dry_run = os.getenv("DRY_RUN", "").strip().lower() == "true"
        return bool(self.settings.dry_run) or env_dry_run

    def _acquire_pipeline_lock(self) -> Optional[IO[str]]:
        """
        Stage 1 (LOCK_ACQUISITION):
        Acquires an exclusive non-blocking POSIX lock adjacent to the portfolio state
        file so overlapping local/cron triggers cannot interleave mutations.
        """
        lock_path = self.settings.virtual_portfolio_path.parent / ".eod_pipeline.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fh = lock_path.open("a+", encoding="utf-8")
        if fcntl is not None:
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                lock_fh.close()
                raise RuntimeError(
                    f"LOCK_ACQUISITION_CONFLICT: Another EOD pipeline instance holds '{lock_path}'."
                ) from exc
        lock_fh.seek(0)
        lock_fh.truncate()
        lock_fh.write(f"pid={os.getpid()} utc={datetime.now(timezone.utc).isoformat()}\n")
        lock_fh.flush()
        self.logger.info(f"[Stage 1: LOCK_ACQUISITION] Acquired single-instance lock ({lock_path.name}).")
        return lock_fh

    @staticmethod
    def _release_pipeline_lock(lock_fh: Optional[IO[str]]) -> None:
        if lock_fh is None:
            return
        with suppress(OSError):
            if fcntl is not None:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        with suppress(OSError):
            lock_fh.close()

    def _validate_preflight_secrets(self, effective_dry_run: bool) -> None:
        """
        Stage 2 (PREFLIGHT_VERIFICATION):
        Ensures required runtime credentials are provisioned before live production execution.
        """
        if self.settings.environment == "production" and not effective_dry_run:
            missing_secrets: List[str] = []
            if not (self.settings.telegram_bot_token and self.settings.telegram_bot_token.strip()):
                missing_secrets.append("TELEGRAM_BOT_TOKEN")
            if not (self.settings.telegram_chat_id and self.settings.telegram_chat_id.strip()):
                missing_secrets.append("TELEGRAM_CHAT_ID")
            if missing_secrets:
                raise RuntimeError(
                    f"PREFLIGHT_VERIFICATION_FAILED: Missing required production secrets: {missing_secrets}."
                )
        self.logger.info(
            f"[Stage 2: PREFLIGHT_VERIFICATION] Environment and security invariants verified "
            f"(env={self.settings.environment}, dry_run={effective_dry_run})."
        )

    def ensure_default_tenant_initialized(
        self,
        state: MultiTenantStateStoreSchema,
        as_of_date: date,
    ) -> MultiTenantStateStoreSchema:
        """
        If `state.tenant_portfolios` is empty on first cold-start boot, automatically
        initializes a default primary shadow portfolio ($100,000 cash & total equity,
        max_portfolio_heat_pct = settings.default_max_portfolio_heat_pct,
        subscribed_indices = list(active_indices.keys())) and persists it via `state_repo.save_state`.
        """
        if state.tenant_portfolios:
            return state

        active_index_ids = [
            idx_id for idx_id, cfg in state.index_registry.items() if cfg.is_active
        ]
        if not active_index_ids:
            active_index_ids = list(state.index_registry.keys())

        default_ledger = VirtualPortfolioLedgerSchema(
            portfolio_id=DEFAULT_ADMIN_PORTFOLIO_ID,
            user_id=DEFAULT_ADMIN_USER_ID,
            portfolio_name="Primary Swing Shadow Portfolio",
            as_of_date=as_of_date,
            cash_balance=100_000.0,
            total_equity=100_000.0,
            max_portfolio_heat_pct=self.settings.default_max_portfolio_heat_pct,
            max_concurrent_positions=10,
            subscribed_indices=active_index_ids,
        )

        updated_portfolios = dict(state.tenant_portfolios)
        updated_portfolios[default_ledger.portfolio_id] = default_ledger

        initialized_state = MultiTenantStateStoreSchema(
            schema_version=state.schema_version,
            last_updated_utc=datetime.now(timezone.utc),
            index_registry=state.index_registry,
            tenant_portfolios=updated_portfolios,
        )

        if not self._is_effective_dry_run():
            self.state_repo.save_state(initialized_state)

        self.logger.info(
            f"Initialized default primary shadow portfolio ({default_ledger.portfolio_id}) "
            f"subscribed to indices: {active_index_ids}."
        )
        return initialized_state

    def _audit_t0_settlement_coverage(
        self,
        tickers: Set[str],
        target_date: date,
    ) -> Tuple[float, int, int]:
        """
        Audits cached Parquet bars across `tickers` to determine what fraction contains
        valid settlement bars for `target_date` ($T_0$).
        """
        total_count = len(tickers)
        if total_count == 0:
            return 0.0, 0, 0

        valid_t0_count = 0
        for ticker in sorted(tickers):
            latest_dt = self.market_repo.get_latest_cached_date(ticker)
            if latest_dt is not None and latest_dt >= target_date:
                valid_t0_count += 1

        coverage_ratio = valid_t0_count / float(total_count)
        return coverage_ratio, valid_t0_count, total_count

    def _ingest_with_settlement_retry(
        self,
        active_indices: Dict[str, IndexConfigSchema],
        global_excluded_tickers: Set[str],
        all_open_position_tickers: Set[str],
        target_date: date,
        retry_attempts: int,
        retry_backoff_sec: int,
    ) -> Dict[str, List[str]]:
        """
        Stage 3 (DATA_INGESTION_AND_AUDIT):
        Syncs universe OHLCV data and audits >= 98% $T_0$ bar completeness.
        If coverage is below 98%, sleeps `retry_backoff_sec` and retries up to
        `retry_attempts` times before raising `SettlementDataDelayError` (`FAILED_DATA_DELAY`).
        """
        max_attempts = max(1, int(retry_attempts))
        backoff_sec = max(0, int(retry_backoff_sec))

        if not active_indices and not all_open_position_tickers:
            self.logger.info(
                "[Stage 3: DATA_INGESTION_AND_AUDIT] All indices inactive (kill-switch freeze) "
                "and zero open positions held; skipping upstream fetch."
            )
            return {}

        for attempt in range(1, max_attempts + 1):
            synced_constituents_map = (
                self.ingestion_pipeline.sync_universe_ohlcv(
                    active_indices=active_indices,
                    excluded_tickers=global_excluded_tickers,
                    as_of_date=target_date,
                )
                if active_indices
                else {}
            )

            all_synced_symbols: Set[str] = set()
            for tickers_list in synced_constituents_map.values():
                all_synced_symbols.update(tickers_list)

            unsynced_held_tickers = sorted(all_open_position_tickers - all_synced_symbols)
            if unsynced_held_tickers:
                for ticker in unsynced_held_tickers:
                    cached_df = self.market_repo.load_ohlcv(
                        ticker,
                        lookback_days=self.settings.backtest_lookback_days,
                    )
                    if cached_df is None or cached_df.empty or cached_df.index[-1].date() < target_date:
                        fetched_map = self.provider.fetch_daily_ohlcv_batch(
                            tickers=[ticker],
                            start_date=date.fromordinal(target_date.toordinal() - 35),
                            end_date=target_date,
                        )
                        if ticker in fetched_map:
                            self.ingestion_pipeline._upsert_to_repository(ticker, fetched_map[ticker])
                            all_synced_symbols.add(ticker)

            audit_universe = all_synced_symbols | all_open_position_tickers
            coverage_ratio, valid_t0_count, total_count = self._audit_t0_settlement_coverage(
                tickers=audit_universe,
                target_date=target_date,
            )

            self.logger.info(
                f"[Stage 3: DATA_INGESTION_AND_AUDIT] T_0 Settlement Audit (Attempt {attempt}/{max_attempts}): "
                f"{valid_t0_count}/{total_count} tickers settled for {target_date} ({coverage_ratio:.2%})."
            )

            if coverage_ratio >= self.MIN_T0_COVERAGE_RATIO:
                return synced_constituents_map

            if attempt < max_attempts:
                self.logger.warning(
                    f"[Stage 3: DATA_INGESTION_AND_AUDIT] T_0 coverage {coverage_ratio:.2%} < "
                    f"{self.MIN_T0_COVERAGE_RATIO:.0%}. Sleeping {backoff_sec}s before retry."
                )
                if backoff_sec > 0:
                    time.sleep(backoff_sec)
            else:
                raise SettlementDataDelayError(
                    f"FAILED_DATA_DELAY: T_0 settlement coverage for {target_date} remained at "
                    f"{coverage_ratio:.2%} ({valid_t0_count}/{total_count}) after {max_attempts} attempts "
                    f"(required >= {self.MIN_T0_COVERAGE_RATIO:.0%})."
                )

        raise SettlementDataDelayError("FAILED_DATA_DELAY: Exhausted settlement retry loop.")

    def _persist_production_state_and_heartbeat(
        self,
        state: MultiTenantStateStoreSchema,
        target_date: date,
    ) -> None:
        """
        Stage 5 (ATOMIC_STATE_PERSISTENCE):
        Delegates atomic write of `virtual_portfolio.json` and `eod_heartbeat.json`
        to `JsonPortfolioStateRepository` (preserving fallback for custom repository mocks).
        """
        self.state_repo.save_state(state)

        if hasattr(self.state_repo, "save_eod_heartbeat"):
            heartbeat_payload = self.state_repo.save_eod_heartbeat(
                state=state,
                trading_date=target_date,
                eod_status="HEALTHY",
            )
            heat_pct = float(heartbeat_payload.get("current_portfolio_heat_pct", 0.0))
            open_positions_count = int(heartbeat_payload.get("open_positions_count", 0))
            total_equity = float(heartbeat_payload.get("total_equity", 0.0))
        else:
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
            fallback_heartbeat = {
                "last_successful_eod_timestamp": now_iso,
                "last_updated_utc": now_iso,
                "eod_status": "HEALTHY",
                "trading_date": target_date.isoformat(),
                "current_portfolio_heat_pct": heat_pct,
                "portfolio_heat_pct": heat_pct,
                "open_positions_count": open_positions_count,
                "total_equity": total_equity,
            }
            atomic_write_json(
                self.settings.virtual_portfolio_path.parent / "eod_heartbeat.json",
                fallback_heartbeat,
            )

        self.logger.info(
            f"[Stage 5: ATOMIC_STATE_PERSISTENCE] Persisted ledger and eod_heartbeat.json "
            f"(trading_date={target_date.isoformat()}, status=HEALTHY, equity=${total_equity:,.2f}, "
            f"heat={heat_pct:.2f}%, open_positions={open_positions_count})."
        )

    def run_daily_cycle(
        self,
        as_of_date: Optional[date] = None,
        retry_attempts: int = 3,
        retry_backoff_sec: int = 600,
    ) -> Dict[str, Any]:
        """
        Executes the 6-stage daily EOD quantitative execution cycle:
        Stage 1/2: Load Multi-Tenant State, Guardrails & Active Index Registry
        Stage 3: Global Market Data Ingestion, t-1 Split Guard & >= 98% T_0 Audit
        Stage 4: Global Shared Compute & Per-Tenant Triple-Barrier Reconciliation
        Stage 5: Atomic State & Heartbeat Persistence (`virtual_portfolio.json` + `eod_heartbeat.json`)
        Stage 6: Mandatory Telegram EOD Telemetry & Daily Heartbeat Dispatch
        """
        start_time = time.monotonic()
        target_date: date = as_of_date or datetime.now(timezone.utc).date()
        effective_dry_run = self._is_effective_dry_run()
        current_stage = "Stage 1: LOCK_ACQUISITION"
        lock_fh: Optional[IO[str]] = None

        self.logger.info(
            f"=== Starting QuantPipelineOrchestrator Cycle (target_date={target_date}, "
            f"environment={self.settings.environment}, dry_run={effective_dry_run}) ==="
        )

        try:
            # -----------------------------------------------------------------
            # Stage 1 — Single-Instance Lock Acquisition
            # -----------------------------------------------------------------
            lock_fh = self._acquire_pipeline_lock()

            # -----------------------------------------------------------------
            # Stage 2 — Preflight Verification, Multi-Tenant State & Registry
            # -----------------------------------------------------------------
            current_stage = "Stage 2: PREFLIGHT_VERIFICATION"
            self._validate_preflight_secrets(effective_dry_run=effective_dry_run)

            user_prefs = load_user_guardrails(PRIMARY_SIRIX_USER_ID)
            kill_switch_active = user_prefs.guardrails.kill_switch_active

            state = self.state_repo.load_state()
            if self.settings.index_registry_path.is_file():
                latest_registry = load_index_registry(self.settings.index_registry_path)
                state = MultiTenantStateStoreSchema(
                    schema_version=state.schema_version,
                    last_updated_utc=state.last_updated_utc,
                    index_registry=latest_registry,
                    tenant_portfolios=state.tenant_portfolios,
                )
            elif not state.index_registry:
                registry = load_index_registry(self.settings.index_registry_path)
                state = MultiTenantStateStoreSchema(
                    schema_version=state.schema_version,
                    last_updated_utc=state.last_updated_utc,
                    index_registry=registry,
                    tenant_portfolios=state.tenant_portfolios,
                )

            state = self.ensure_default_tenant_initialized(state, target_date)

            active_indices: Dict[str, IndexConfigSchema] = {
                idx_id: cfg
                for idx_id, cfg in state.index_registry.items()
                if cfg.is_active
            }
            if not active_indices:
                self.logger.warning(
                    "[Stage 2: PREFLIGHT_VERIFICATION] Index Registry Kill-Switch active: "
                    "0 active indices (is_active=false). New entries paused; open positions will reconcile."
                )

            tenant_holding_sets: List[Set[str]] = [
                {t.strip().upper() for t in ledger.open_positions.keys()}
                for ledger in state.tenant_portfolios.values()
            ]
            all_open_position_tickers: Set[str] = (
                set().union(*tenant_holding_sets) if tenant_holding_sets else set()
            )
            universally_held_tickers: Set[str] = (
                set.intersection(*tenant_holding_sets) if tenant_holding_sets else set()
            )
            global_excluded_tickers: Set[str] = universally_held_tickers - all_open_position_tickers

            # -----------------------------------------------------------------
            # Stage 3 — Data Ingestion, t-1 Split Guard & T_0 Completeness Audit
            # -----------------------------------------------------------------
            current_stage = "Stage 3: DATA_INGESTION_AND_AUDIT"
            synced_constituents_map = self._ingest_with_settlement_retry(
                active_indices=active_indices,
                global_excluded_tickers=global_excluded_tickers,
                all_open_position_tickers=all_open_position_tickers,
                target_date=target_date,
                retry_attempts=retry_attempts,
                retry_backoff_sec=retry_backoff_sec,
            )

            benchmark_frames: Dict[str, pd.DataFrame] = {}
            for idx_id, cfg in active_indices.items():
                bench_symbol = cfg.benchmark_ticker.strip().upper()
                if bench_symbol not in benchmark_frames:
                    bench_df = self.market_repo.load_ohlcv(
                        bench_symbol,
                        lookback_days=self.settings.backtest_lookback_days,
                    )
                    if bench_df is not None and not bench_df.empty:
                        benchmark_frames[bench_symbol] = bench_df

            # -----------------------------------------------------------------
            # Stage 4 — Quant Evaluation (Screening, Meta-Labeling & Reconciliation)
            # -----------------------------------------------------------------
            current_stage = "Stage 4: QUANT_EVALUATION"
            primary_signals_by_index: Dict[str, List[DirectionalSignalSchema]] = {}
            approved_signals: List[MetaLabeledSignalSchema] = []
            vetoed_signals: List[MetaLabeledSignalSchema] = []

            for idx_id, idx_cfg in active_indices.items():
                bench_symbol = idx_cfg.benchmark_ticker.strip().upper()
                bench_df = benchmark_frames.get(bench_symbol)
                if bench_df is None or bench_df.empty:
                    self.logger.warning(
                        f"Benchmark '{bench_symbol}' unavailable for index '{idx_id}'; skipping screening."
                    )
                    continue

                constituent_tickers = synced_constituents_map.get(idx_id, [])
                ohlcv_index_map: Dict[str, pd.DataFrame] = {}
                for ticker in constituent_tickers:
                    if ticker in universally_held_tickers:
                        continue
                    t_df = self.market_repo.load_ohlcv(
                        ticker,
                        lookback_days=self.settings.backtest_lookback_days,
                    )
                    if t_df is not None and not t_df.empty:
                        ohlcv_index_map[ticker] = t_df

                spread_map = self.provider.fetch_current_quotes_spread_proxy(
                    list(ohlcv_index_map.keys())
                )

                shortlisted_primary = self.screening_engine.screen_index_universe(
                    ohlcv_map=ohlcv_index_map,
                    benchmark_df=bench_df,
                    index_cfg=idx_cfg,
                    as_of_date=target_date,
                    spread_map=spread_map,
                    excluded_tickers=universally_held_tickers,
                    top_n=self.settings.top_n_candidates_per_index,
                )
                primary_signals_by_index[idx_id] = shortlisted_primary

                for prim_sig in shortlisted_primary:
                    asset_df = ohlcv_index_map.get(prim_sig.ticker)
                    if asset_df is None or asset_df.empty:
                        continue

                    meta_sig = self.backtest_engine.evaluate_candidate(
                        signal=prim_sig,
                        asset_df=asset_df,
                        benchmark_df=bench_df,
                        index_cfg=idx_cfg,
                    )
                    if meta_sig.is_approved:
                        approved_signals.append(meta_sig)
                    else:
                        vetoed_signals.append(meta_sig)

            tenant_reports: Dict[UUID, TenantDailyReportPayload] = {}
            total_opened_count = 0
            total_closed_count = 0
            per_tenant_actions: List[
                Tuple[
                    VirtualPortfolioLedgerSchema,
                    List[TripleBarrierPositionSchema],
                    List[ClosedTradeAuditSchema],
                ]
            ] = []

            for portfolio_id, ledger in state.tenant_portfolios.items():
                tenant_open_ohlcv: Dict[str, pd.DataFrame] = {}
                for held_ticker in list(ledger.open_positions.keys()):
                    held_df = self.market_repo.load_ohlcv(
                        held_ticker,
                        lookback_days=self.settings.screening_lookback_days,
                    )
                    if held_df is not None and not held_df.empty:
                        held_df = held_df.copy()
                        held_df["ATR_14"] = FeatureEngineer.compute_atr_14(held_df, period=14)
                        tenant_open_ohlcv[held_ticker] = held_df

                closed_trades: List[ClosedTradeAuditSchema] = (
                    self.reconciler.reconcile_open_positions(
                        ledger=ledger,
                        ohlcv_map=tenant_open_ohlcv,
                        index_registry=state.index_registry,
                        as_of_date=target_date,
                    )
                )

                effective_signals = [] if kill_switch_active else approved_signals
                opened_positions: List[TripleBarrierPositionSchema] = (
                    self.reconciler.allocate_new_signals(
                        ledger=ledger,
                        approved_signals=effective_signals,
                        as_of_date=target_date,
                    )
                )

                total_closed_count += len(closed_trades)
                total_opened_count += len(opened_positions)
                per_tenant_actions.append((ledger, opened_positions, closed_trades))

            # -----------------------------------------------------------------
            # Stage 5 — Atomic State Persistence & GCS Telemetry Export
            # -----------------------------------------------------------------
            current_stage = "Stage 5: ATOMIC_STATE_PERSISTENCE"
            if not effective_dry_run:
                self._persist_production_state_and_heartbeat(state=state, target_date=target_date)
                for ledger, _, _ in per_tenant_actions:
                    self.cloud_exporter.export_all(
                        ledger=ledger,
                        user_id=PRIMARY_SIRIX_USER_ID,
                        approved_signals=approved_signals,
                        vetoed_signals=vetoed_signals,
                        as_of_date=target_date,
                    )
            else:
                self.logger.info(
                    "[Stage 5: ATOMIC_STATE_PERSISTENCE] [DRY-RUN] Skipped persistent "
                    "state writes to virtual_portfolio.json, eod_heartbeat.json, and GCS."
                )

            # -----------------------------------------------------------------
            # Stage 6 — Mandatory Daily Telemetry & Heartbeat Dispatch
            # -----------------------------------------------------------------
            current_stage = "Stage 6: TELEMETRY_AND_HEARTBEAT"
            for ledger, opened_positions, closed_trades in per_tenant_actions:
                report_payload = TenantDailyReportPayload(
                    as_of_date=target_date,
                    ledger=ledger,
                    opened_positions=opened_positions,
                    closed_trades=closed_trades,
                    approved_signals=approved_signals,
                    vetoed_signals=vetoed_signals,
                    dry_run=effective_dry_run,
                )
                tenant_reports[ledger.portfolio_id] = report_payload
                self.notifier.dispatch_tenant_report(report_payload)

            heartbeat_badge = "[DRY-RUN] " if effective_dry_run else ""
            self.logger.info(
                f"[Stage 6: TELEMETRY_AND_HEARTBEAT] {heartbeat_badge}EOD Heartbeat dispatched "
                f"(date={target_date}, opened={total_opened_count}, closed={total_closed_count}, "
                f"tenants={len(per_tenant_actions)})."
            )

            # -----------------------------------------------------------------
            # SLA Verification & Telemetry Summary
            # -----------------------------------------------------------------
            elapsed_sec = round(time.monotonic() - start_time, 2)
            if elapsed_sec > self.SLA_MAX_SECONDS:
                self.logger.warning(
                    f"SLA WARNING: Daily quant cycle elapsed {elapsed_sec:.2f}s, "
                    f"exceeding the {self.SLA_MAX_SECONDS:.1f}s (15-minute) ceiling!"
                )
            else:
                self.logger.info(
                    f"Daily quant cycle completed in {elapsed_sec:.2f}s "
                    f"(approved_signals={len(approved_signals)}, vetoed_signals={len(vetoed_signals)}, "
                    f"opened={total_opened_count}, closed={total_closed_count})."
                )

            return {
                "as_of_date": target_date,
                "elapsed_sec": elapsed_sec,
                "active_indices": list(active_indices.keys()),
                "primary_signals_count": sum(len(v) for v in primary_signals_by_index.values()),
                "approved_signals": approved_signals,
                "vetoed_signals": vetoed_signals,
                "tenant_reports": tenant_reports,
                "state": state,
            }

        except Exception as exc:
            self.logger.exception(
                f"CRITICAL PIPELINE FAILURE during {current_stage} on {target_date}: {exc}"
            )
            self.notifier.dispatch_critical_alert(
                error_message=str(exc),
                stage=current_stage,
                as_of_date=target_date,
            )
            raise
        finally:
            self._release_pipeline_lock(lock_fh)


# =============================================================================
# 4. CLI ENTRYPOINT
# =============================================================================


def parse_cli_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Swing Quant Engine - Autonomous Headless Daily Execution Worker"
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "eod", "sandbox"],
        default="daily",
        help="Execution mode: 'eod'/'daily' production/dry-run worker or 'sandbox' end-to-end harness.",
    )
    parser.add_argument(
        "--date",
        "--as-of-date",
        dest="date",
        type=str,
        default=None,
        help="Optional ISO YYYY-MM-DD target EOD date override for deterministic replays.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute pipeline in dry-run mode without mutating persistent production state.",
    )
    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Bypass the NYSE Market Calendar Gate to allow weekend or holiday runs.",
    )
    parser.add_argument(
        "--check-market-calendar",
        action="store_true",
        help="Evaluate NYSE market calendar gate, emit GITHUB_OUTPUT is_trading_day, and exit cleanly.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=3,
        help="Maximum T_0 settlement completeness retry attempts when coverage < 98%%.",
    )
    parser.add_argument(
        "--retry-backoff-sec",
        type=int,
        default=600,
        help="Backoff sleep duration in seconds between T_0 settlement completeness retries.",
    )
    parser.add_argument(
        "--notify-failure",
        action="store_true",
        help="Dispatch high-priority CRITICAL EOD PIPELINE FAILURE alert via TelegramNotifier.",
    )
    parser.add_argument(
        "--run-url",
        type=str,
        default=None,
        help="GitHub Actions workflow run URL included in critical failure alerts.",
    )
    parser.add_argument(
        "--failed-stage",
        type=str,
        default=None,
        help="Optional failed pipeline stage description for failure alert context.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_cli_args(argv)
    base_settings = get_settings()

    env_dry_run = os.getenv("DRY_RUN", "").strip().lower() == "true"
    effective_dry_run = bool(args.dry_run) or env_dry_run or bool(base_settings.dry_run)

    if effective_dry_run != base_settings.dry_run:
        settings = base_settings.model_copy(update={"dry_run": effective_dry_run})
    else:
        settings = base_settings

    configure_logging(settings.log_level)

    target_date: Optional[date] = date.fromisoformat(args.date) if args.date else None
    cli_force_override: Optional[bool] = True if args.force_run else None

    if args.check_market_calendar:
        return evaluate_market_calendar_gate(
            target_date=target_date,
            force_run=cli_force_override,
        )

    if args.notify_failure:
        return dispatch_cli_failure_alert(
            settings=settings,
            run_url=args.run_url,
            failed_stage=args.failed_stage,
            as_of_date=target_date,
        )

    if args.mode == "sandbox":
        try:
            from src.sandbox_runner import SandboxDryRunHarness
        except ImportError:
            from sandbox_runner import SandboxDryRunHarness  # type: ignore[no-redef]

        harness = SandboxDryRunHarness()
        return 0 if harness.run() else 1

    if target_date is None and not effective_dry_run:
        is_trading_day, eval_date, status_note = check_nyse_gate_status(
            target_date=None,
            force_run=cli_force_override,
        )
        if not is_trading_day:
            logging.getLogger("SwingQuantEngine.Orchestrator").info(
                f"[Stage 2: PREFLIGHT_VERIFICATION] SKIPPED_MARKET_CLOSED "
                f"(ny_date={eval_date.isoformat()}, reason={status_note}, is_trading_day=false)."
            )
            return 0

    orchestrator = QuantPipelineOrchestrator(settings=settings)
    orchestrator.run_daily_cycle(
        as_of_date=target_date,
        retry_attempts=args.retry_attempts,
        retry_backoff_sec=args.retry_backoff_sec,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

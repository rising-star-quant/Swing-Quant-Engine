from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta, timezone
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

try:
    from src.config import SystemSettings, get_settings
    from src.schemas import (
        ActivePositionDTO,
        AuditLedgerResponse,
        AuditTradeDTO,
        AuditTradeExitReasonLiteral,
        AuthSessionStatusResponse,
        EODExecutionStatus,
        EquityCurvePointDTO,
        ExitReason,
        IndexSourceLiteral,
        InternalTriggerEODResponse,
        LoginRequest,
        LoginResponse,
        MultiTenantStateStoreSchema,
        PortfolioSummaryResponse,
        SystemHealthTelemetry,
        TripleBarrierPositionSchema,
        VirtualPortfolioLedgerSchema,
    )
    from src.security import (
        AuthenticationError,
        AuthorizationError,
        RateLimitExceededError,
        SESSION_COOKIE_NAME,
        SchedulerAuthError,
        SecurityViolationError,
        SingleOriginCookieSessionManager,
        SlidingWindowLoginRateLimiter,
        verify_internal_scheduler_token,
    )
    from src.storage import (
        DEFAULT_ADMIN_PORTFOLIO_ID,
        MalformedStateError,
        StateCorruptionError,
        StatelessGCSStateReader,
        StorageError,
    )
except ImportError:
    from config import SystemSettings, get_settings  # type: ignore[no-redef]
    from schemas import (  # type: ignore[no-redef]
        ActivePositionDTO,
        AuditLedgerResponse,
        AuditTradeDTO,
        AuditTradeExitReasonLiteral,
        AuthSessionStatusResponse,
        EODExecutionStatus,
        EquityCurvePointDTO,
        ExitReason,
        IndexSourceLiteral,
        InternalTriggerEODResponse,
        LoginRequest,
        LoginResponse,
        MultiTenantStateStoreSchema,
        PortfolioSummaryResponse,
        SystemHealthTelemetry,
        TripleBarrierPositionSchema,
        VirtualPortfolioLedgerSchema,
    )
    from security import (  # type: ignore[no-redef]
        AuthenticationError,
        AuthorizationError,
        RateLimitExceededError,
        SESSION_COOKIE_NAME,
        SchedulerAuthError,
        SecurityViolationError,
        SingleOriginCookieSessionManager,
        SlidingWindowLoginRateLimiter,
        verify_internal_scheduler_token,
    )
    from storage import (  # type: ignore[no-redef]
        DEFAULT_ADMIN_PORTFOLIO_ID,
        MalformedStateError,
        StateCorruptionError,
        StatelessGCSStateReader,
        StorageError,
    )

logger = logging.getLogger("SIRIX.UnifiedAPI")

DEFAULT_INITIAL_EQUITY_USD: float = 100_000.0
EOD_SCHEDULE_HOUR_UTC: int = 21
EOD_SCHEDULE_MINUTE_UTC: int = 45


# =============================================================================
# 1. DOMAIN TRANSFORMATION & MAPPING HELPERS (STRICTLY READ-ONLY)
# =============================================================================


def _resolve_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _map_index_source(raw_index: Optional[str]) -> IndexSourceLiteral:
    normalized = (raw_index or "RUT_2000").strip().upper()
    mapping: Dict[str, IndexSourceLiteral] = {
        "RUT": "RUT_2000",
        "RUT_2000": "RUT_2000",
        "RUSSELL_2000": "RUT_2000",
        "IWM": "RUT_2000",
        "MID": "SP_400",
        "SP_400": "SP_400",
        "SP400": "SP_400",
        "MDY": "SP_400",
        "SPX": "SP_500",
        "SP_500": "SP_500",
        "SP500": "SP_500",
        "SPY": "SP_500",
    }
    return mapping.get(normalized, "RUT_2000")


def _map_exit_reason(raw_reason: ExitReason | str) -> AuditTradeExitReasonLiteral:
    value = raw_reason.value if isinstance(raw_reason, ExitReason) else str(raw_reason)
    normalized = value.strip().upper()
    if normalized in {"UPPER_BARRIER_TP", "TAKE_PROFIT"}:
        return "TAKE_PROFIT"
    if normalized in {"LOWER_BARRIER_SL", "TRAILING_STOP", "CHANDELIER_STOP", "RATCHET_STOP"}:
        return "RATCHET_STOP"
    if normalized in {"VERTICAL_BARRIER_TIME", "TIME_BARRIER", "TIME_BARRIER_14D"}:
        return "TIME_BARRIER_14D"
    if "SPLIT" in normalized or normalized == "SYSTEM_CIRCUIT_BREAKER":
        return "SPLIT_ADJUSTED_EXIT"
    return "RATCHET_STOP"


def _map_eod_status(raw_status: Optional[str]) -> EODExecutionStatus:
    normalized = (raw_status or "IDLE").strip().upper()
    mapping: Dict[str, EODExecutionStatus] = {
        "IDLE": "IDLE",
        "HEALTHY": "IDLE",
        "SUCCESS": "IDLE",
        "COMPLETED": "IDLE",
        "RUNNING": "RUNNING_EOD",
        "RUNNING_EOD": "RUNNING_EOD",
        "SKIPPED_MARKET_CLOSED": "SKIPPED_MARKET_CLOSED",
        "MARKET_CLOSED": "SKIPPED_MARKET_CLOSED",
        "FAILED_DATA_DELAY": "FAILED_DATA_DELAY",
        "DATA_DELAY": "FAILED_DATA_DELAY",
        "CRITICAL_ERROR": "CRITICAL_ERROR",
        "FAILED": "CRITICAL_ERROR",
        "ERROR": "CRITICAL_ERROR",
    }
    return mapping.get(normalized, "IDLE")


def _compute_next_scheduled_run_utc(reference_utc: Optional[datetime] = None) -> datetime:
    now_utc = reference_utc or datetime.now(timezone.utc)
    candidate_date = now_utc.date()
    scheduled_time = dt_time(hour=EOD_SCHEDULE_HOUR_UTC, minute=EOD_SCHEDULE_MINUTE_UTC, tzinfo=timezone.utc)
    candidate_dt = datetime.combine(candidate_date, scheduled_time)

    if now_utc >= candidate_dt or candidate_date.weekday() >= 5:
        candidate_date = candidate_date + timedelta(days=1)
        while candidate_date.weekday() >= 5:
            candidate_date = candidate_date + timedelta(days=1)
        candidate_dt = datetime.combine(candidate_date, scheduled_time)

    return candidate_dt


def _select_primary_ledger(state: MultiTenantStateStoreSchema) -> VirtualPortfolioLedgerSchema:
    if not state.tenant_portfolios:
        raise MalformedStateError("Portfolio state store contains zero tenant portfolios.")
    if DEFAULT_ADMIN_PORTFOLIO_ID in state.tenant_portfolios:
        return state.tenant_portfolios[DEFAULT_ADMIN_PORTFOLIO_ID]
    first_key = next(iter(state.tenant_portfolios))
    return state.tenant_portfolios[first_key]


def _clamp_meta_confidence_phi(pos: TripleBarrierPositionSchema) -> float:
    raw_phi = float(getattr(pos, "conviction_multiplier", 1.0) or 1.0)
    if not math.isfinite(raw_phi) or raw_phi <= 0.0:
        raw_phi = 1.0
    return round(min(1.25, max(0.5, raw_phi)), 4)


def _transform_active_position(
    pos: TripleBarrierPositionSchema,
    as_of_date: Any,
) -> ActivePositionDTO:
    entry_price = float(pos.entry_price)
    current_price = float(
        getattr(pos, "latest_close_price", None)
        or pos.highest_high_since_entry
        or pos.entry_price
    )
    shares = int(pos.shares)
    initial_stop = float(pos.initial_stop_price)
    ratchet_stop = float(pos.trailing_stop_price)
    take_profit = float(pos.take_profit_price)

    atr_est = float(pos.entry_atr_14) if float(pos.entry_atr_14) > 0.0 else abs(entry_price - initial_stop) / 2.0
    if atr_est <= 0.0:
        atr_est = max(0.01, round(entry_price * 0.02, 4))

    raw_days_held = int(pos.bars_held)
    if as_of_date is not None and pos.entry_date is not None:
        calendar_days = (as_of_date - pos.entry_date).days
        raw_days_held = max(raw_days_held, calendar_days)
    days_held = min(14, max(0, raw_days_held))

    unrealized_pnl_usd = round((current_price - entry_price) * shares, 2)
    unrealized_pnl_pct = round(((current_price - entry_price) / entry_price) * 100.0, 4)

    one_r_distance = max(1e-6, entry_price - initial_stop)
    unrealized_r_multiple = round((current_price - entry_price) / one_r_distance, 4)

    if ratchet_stop >= entry_price:
        open_risk_usd = 0.0
    else:
        open_risk_usd = round(max(0.0, (entry_price - ratchet_stop) * shares), 2)

    return ActivePositionDTO(
        ticker=pos.ticker,
        index_source=_map_index_source(pos.index_id),
        entry_date=pos.entry_date.isoformat(),
        entry_price=round(entry_price, 4),
        current_price=round(current_price, 4),
        shares=shares,
        initial_stop_price=round(initial_stop, 4),
        ratchet_stop_price=round(ratchet_stop, 4),
        take_profit_price=round(take_profit, 4),
        atr_14=round(atr_est, 4),
        meta_confidence_phi=_clamp_meta_confidence_phi(pos),
        days_held=days_held,
        max_holding_days=min(30, max(1, int(pos.max_holding_bars))),
        unrealized_pnl_usd=unrealized_pnl_usd,
        unrealized_pnl_pct=unrealized_pnl_pct,
        unrealized_r_multiple=unrealized_r_multiple,
        open_risk_usd=open_risk_usd,
    )


def _build_portfolio_summary(state: MultiTenantStateStoreSchema) -> PortfolioSummaryResponse:
    ledger = _select_primary_ledger(state)

    positions: List[ActivePositionDTO] = [
        _transform_active_position(pos, ledger.as_of_date)
        for pos in ledger.open_positions.values()
    ]
    positions.sort(key=lambda item: item.ticker)

    invested_capital = round(sum(p.current_price * p.shares for p in positions), 2)
    cash_balance = round(float(ledger.cash_balance), 2)
    total_equity = round(max(float(ledger.total_equity), cash_balance + invested_capital, 0.01), 2)

    total_open_risk_usd = sum(p.open_risk_usd for p in positions)
    portfolio_heat_pct = round(min(6.0, max(0.0, (total_open_risk_usd / total_equity) * 100.0)), 4)
    max_heat_cap_pct = round(float(ledger.max_portfolio_heat_pct) * 100.0, 2)

    closed_trades = ledger.closed_trades_audit
    total_closed = len(closed_trades)
    if total_closed > 0:
        wins = sum(1 for t in closed_trades if float(t.realized_pnl_dollars) > 0.0)
        win_rate_pct = round((wins / total_closed) * 100.0, 2)
        expectancy_r = round(sum(float(t.realized_r_multiple) for t in closed_trades) / total_closed, 4)
    else:
        win_rate_pct = 0.0
        expectancy_r = 0.0

    cumulative_return_pct = round(
        ((total_equity - DEFAULT_INITIAL_EQUITY_USD) / DEFAULT_INITIAL_EQUITY_USD) * 100.0,
        4,
    )

    return PortfolioSummaryResponse(
        as_of_utc=state.last_updated_utc,
        total_equity_usd=total_equity,
        cash_balance_usd=cash_balance,
        invested_capital_usd=invested_capital,
        portfolio_heat_pct=portfolio_heat_pct,
        max_heat_cap_pct=max_heat_cap_pct,
        open_positions_count=min(10, len(positions)),
        max_positions_cap=int(ledger.max_concurrent_positions),
        cumulative_return_pct=cumulative_return_pct,
        win_rate_pct=win_rate_pct,
        expectancy_r=expectancy_r,
        positions=positions,
    )


# =============================================================================
# 2. FASTAPI APPLICATION FACTORY & LIFESPAN SERVICES
# =============================================================================


def create_app(
    settings: Optional[SystemSettings] = None,
    state_reader: Optional[StatelessGCSStateReader] = None,
    session_manager: Optional[SingleOriginCookieSessionManager] = None,
    rate_limiter: Optional[SlidingWindowLoginRateLimiter] = None,
    static_gui_dir: Optional[Path] = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_reader = state_reader or StatelessGCSStateReader(settings=resolved_settings)
    resolved_sessions = session_manager or SingleOriginCookieSessionManager(settings=resolved_settings)
    resolved_limiter = rate_limiter or SlidingWindowLoginRateLimiter()
    resolved_static_dir = (
        static_gui_dir.resolve()
        if static_gui_dir is not None
        else (resolved_settings.base_dir / "static_gui").resolve()
    )

    fastapi_app = FastAPI(
        title="SIRIX Quantitative Portfolio Telemetry API",
        version="2.0.0",
        description="Unified Single-Origin Cloud Run & GCS Read-Only Quantitative Telemetry Server",
        docs_url=None if resolved_settings.environment == "production" else "/api/docs",
        redoc_url=None,
    )

    # Deliberately ZERO CORSMiddleware: strict Single-Origin architecture.
    fastapi_app.state.settings = resolved_settings
    fastapi_app.state.state_reader = resolved_reader
    fastapi_app.state.session_manager = resolved_sessions
    fastapi_app.state.rate_limiter = resolved_limiter
    fastapi_app.state.static_gui_dir = resolved_static_dir

    # -------------------------------------------------------------------------
    # Global Exception Handlers (Strict Edge-State HTTP Mapping)
    # -------------------------------------------------------------------------

    @fastapi_app.exception_handler(MalformedStateError)
    async def handle_malformed_state(_request: Request, exc: MalformedStateError) -> JSONResponse:
        logger.error(f"Malformed persisted state detected: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": "MALFORMED_STATE",
                "detail": "Portfolio telemetry state is currently unavailable or invalid.",
            },
        )

    @fastapi_app.exception_handler(StateCorruptionError)
    async def handle_corrupt_state(_request: Request, exc: StateCorruptionError) -> JSONResponse:
        logger.error(f"Corrupted persisted state detected: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": "STATE_CORRUPTION",
                "detail": "Portfolio telemetry state failed validation.",
            },
        )

    @fastapi_app.exception_handler(StorageError)
    async def handle_storage_error(_request: Request, exc: StorageError) -> JSONResponse:
        logger.error(f"Storage backend error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": "STORAGE_UNAVAILABLE",
                "detail": "State storage backend is temporarily unreachable.",
            },
        )

    @fastapi_app.exception_handler(RateLimitExceededError)
    async def handle_rate_limit(_request: Request, exc: RateLimitExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(exc.retry_after_seconds)},
            content={
                "error_code": "RATE_LIMIT_EXCEEDED",
                "detail": str(exc),
            },
        )

    @fastapi_app.exception_handler(SchedulerAuthError)
    async def handle_scheduler_auth(_request: Request, exc: SchedulerAuthError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error_code": "SCHEDULER_FORBIDDEN",
                "detail": str(exc),
            },
        )

    @fastapi_app.exception_handler(AuthenticationError)
    async def handle_auth_error(_request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error_code": "UNAUTHORIZED",
                "detail": str(exc),
            },
        )

    @fastapi_app.exception_handler(AuthorizationError)
    @fastapi_app.exception_handler(SecurityViolationError)
    async def handle_forbidden(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error_code": "FORBIDDEN",
                "detail": str(exc),
            },
        )

    # -------------------------------------------------------------------------
    # Dependency Accessors
    # -------------------------------------------------------------------------

    def get_reader(request: Request) -> StatelessGCSStateReader:
        return request.app.state.state_reader

    def get_sessions(request: Request) -> SingleOriginCookieSessionManager:
        return request.app.state.session_manager

    def get_limiter(request: Request) -> SlidingWindowLoginRateLimiter:
        return request.app.state.rate_limiter

    def require_authenticated_session(
        request: Request,
        sessions: SingleOriginCookieSessionManager = Depends(get_sessions),
    ) -> Dict[str, Any]:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        return sessions.verify_session_cookie(token)

    # -------------------------------------------------------------------------
    # Health & Operational Telemetry Endpoints (Public Read-Only)
    # -------------------------------------------------------------------------

    @fastapi_app.get("/api/health", status_code=status.HTTP_200_OK)
    @fastapi_app.get("/healthz", status_code=status.HTTP_200_OK)
    async def health_check(
        reader: StatelessGCSStateReader = Depends(get_reader),
    ) -> Dict[str, Any]:
        return {
            "status": "ok",
            "service": "sirix-unified-api",
            "storage_backend": reader.active_backend(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    @fastapi_app.get(
        "/api/system/status",
        response_model=SystemHealthTelemetry,
        status_code=status.HTTP_200_OK,
    )
    async def get_system_status(
        reader: StatelessGCSStateReader = Depends(get_reader),
    ) -> SystemHealthTelemetry:
        telemetry, backend = reader.read_eod_telemetry()

        last_ts_raw = (
            telemetry.get("last_successful_eod_timestamp")
            or telemetry.get("last_updated_utc")
        )
        last_ts: Optional[datetime] = None
        if isinstance(last_ts_raw, str) and last_ts_raw.strip():
            try:
                last_ts = datetime.fromisoformat(last_ts_raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise MalformedStateError(
                    f"Invalid ISO-8601 timestamp in EOD telemetry: '{last_ts_raw}'"
                ) from exc

        last_trading_date = (
            telemetry.get("last_trading_date_processed")
            or telemetry.get("trading_date")
        )
        if last_trading_date is not None:
            last_trading_date = str(last_trading_date).strip()

        if last_ts is None or last_trading_date is None:
            try:
                portfolio_state, p_backend = reader.read_virtual_portfolio()
                ledger = _select_primary_ledger(portfolio_state)
                if last_ts is None:
                    last_ts = portfolio_state.last_updated_utc
                if last_trading_date is None:
                    last_trading_date = ledger.as_of_date.isoformat()
                if not telemetry:
                    backend = p_backend
            except MalformedStateError:
                raise
            except Exception:
                logger.debug("Optional portfolio fallback for empty telemetry skipped.")

        raw_status = telemetry.get("eod_status") or telemetry.get("status")
        failure_reason = telemetry.get("failure_reason") or telemetry.get("error_detail")

        return SystemHealthTelemetry(
            eod_status=_map_eod_status(raw_status),
            last_successful_eod_timestamp=last_ts,
            last_trading_date_processed=last_trading_date,
            next_scheduled_run_utc=_compute_next_scheduled_run_utc(),
            storage_backend=backend,
            failure_reason=str(failure_reason) if failure_reason else None,
        )

    # -------------------------------------------------------------------------
    # Single-Origin Cookie Authentication Endpoints
    # -------------------------------------------------------------------------

    @fastapi_app.post(
        "/api/auth/login",
        response_model=LoginResponse,
        status_code=status.HTTP_200_OK,
    )
    async def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        sessions: SingleOriginCookieSessionManager = Depends(get_sessions),
        limiter: SlidingWindowLoginRateLimiter = Depends(get_limiter),
    ) -> LoginResponse:
        client_ip = _resolve_client_ip(request)
        limiter.check_allowed(client_ip)

        try:
            jwt_token, expires_at_utc = sessions.authenticate_credentials(
                username=payload.username,
                password=payload.password,
            )
        except AuthenticationError:
            limiter.record_failure(client_ip)
            raise

        limiter.reset(client_ip)
        cookie_attrs = sessions.cookie_attributes()
        response.set_cookie(
            value=jwt_token,
            **cookie_attrs,
        )
        return LoginResponse(
            authenticated=True,
            expires_at_utc=expires_at_utc,
        )

    @fastapi_app.post("/api/auth/logout", status_code=status.HTTP_200_OK)
    async def logout(
        response: Response,
        sessions: SingleOriginCookieSessionManager = Depends(get_sessions),
    ) -> Dict[str, bool]:
        attrs = sessions.cookie_attributes()
        response.delete_cookie(
            key=attrs["key"],
            path=attrs["path"],
            httponly=attrs["httponly"],
            secure=attrs["secure"],
            samesite=attrs["samesite"],
        )
        return {"authenticated": False}

    @fastapi_app.get(
        "/api/auth/me",
        response_model=AuthSessionStatusResponse,
        status_code=status.HTTP_200_OK,
    )
    async def auth_me(
        session_info: Dict[str, Any] = Depends(require_authenticated_session),
    ) -> AuthSessionStatusResponse:
        return AuthSessionStatusResponse(
            authenticated=True,
            username=str(session_info["username"]),
            role=str(session_info["role"]),
            expires_at_utc=session_info["expires_at_utc"],
        )

    # -------------------------------------------------------------------------
    # Read-Only Portfolio & Quantitative Audit Endpoints (Cookie-Protected)
    # -------------------------------------------------------------------------

    @fastapi_app.get(
        "/api/portfolio/summary",
        response_model=PortfolioSummaryResponse,
        status_code=status.HTTP_200_OK,
    )
    async def get_portfolio_summary(
        _session: Dict[str, Any] = Depends(require_authenticated_session),
        reader: StatelessGCSStateReader = Depends(get_reader),
    ) -> PortfolioSummaryResponse:
        state, _backend = reader.read_virtual_portfolio()
        return _build_portfolio_summary(state)

    @fastapi_app.get(
        "/api/portfolio/equity-curve",
        response_model=List[EquityCurvePointDTO],
        status_code=status.HTTP_200_OK,
    )
    async def get_equity_curve(
        _session: Dict[str, Any] = Depends(require_authenticated_session),
        reader: StatelessGCSStateReader = Depends(get_reader),
    ) -> List[EquityCurvePointDTO]:
        raw_points, _backend = reader.read_equity_curve()
        validated_points: List[EquityCurvePointDTO] = []

        if raw_points:
            try:
                for raw_pt in raw_points:
                    if not isinstance(raw_pt, dict):
                        raise MalformedStateError("Each equity curve entry must be a JSON object.")
                    validated_points.append(
                        EquityCurvePointDTO(
                            date=str(raw_pt["date"]),
                            portfolio_nav=float(raw_pt["portfolio_nav"]),
                            benchmark_iwm_norm=float(raw_pt.get("benchmark_iwm_norm", 100.0)),
                            benchmark_mdy_norm=float(raw_pt.get("benchmark_mdy_norm", 100.0)),
                            heat_pct=min(15.0, max(0.0, float(raw_pt.get("heat_pct", 0.0)))),
                        )
                    )
            except (KeyError, TypeError, ValueError) as exc:
                raise MalformedStateError(
                    f"Malformed entry in state/equity_curve.json: {exc}"
                ) from exc
            validated_points.sort(key=lambda pt: pt.date)
            return validated_points

        state, _p_backend = reader.read_virtual_portfolio()
        summary = _build_portfolio_summary(state)
        ledger = _select_primary_ledger(state)
        return [
            EquityCurvePointDTO(
                date=ledger.as_of_date.isoformat(),
                portfolio_nav=summary.total_equity_usd,
                benchmark_iwm_norm=100.0,
                benchmark_mdy_norm=100.0,
                heat_pct=summary.portfolio_heat_pct,
            )
        ]

    @fastapi_app.get(
        "/api/portfolio/audit-ledger",
        response_model=AuditLedgerResponse,
        status_code=status.HTTP_200_OK,
    )
    async def get_audit_ledger(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        ticker: Optional[str] = Query(default=None, max_length=12),
        exit_reason: Optional[str] = Query(default=None, max_length=32),
        _session: Dict[str, Any] = Depends(require_authenticated_session),
        reader: StatelessGCSStateReader = Depends(get_reader),
    ) -> AuditLedgerResponse:
        state, _backend = reader.read_virtual_portfolio()
        ledger = _select_primary_ledger(state)

        ticker_filter = ticker.strip().upper() if ticker else None
        reason_filter = exit_reason.strip().upper() if exit_reason else None

        transformed: List[AuditTradeDTO] = []
        for idx, trade in enumerate(ledger.closed_trades_audit):
            mapped_reason = _map_exit_reason(trade.exit_reason)
            dto = AuditTradeDTO(
                trade_id=str(trade.trade_id or f"{trade.ticker}-{trade.exit_date.isoformat()}-{idx}"),
                ticker=trade.ticker,
                index_source=_map_index_source(trade.index_id),
                entry_date=trade.entry_date.isoformat(),
                exit_date=trade.exit_date.isoformat(),
                entry_price=round(float(trade.entry_price), 4),
                exit_price=round(float(trade.exit_price), 4),
                shares=int(trade.shares),
                realized_pnl_usd=round(float(trade.realized_pnl_dollars), 2),
                realized_r_multiple=round(float(trade.realized_r_multiple), 4),
                exit_reason=mapped_reason,
                corporate_action_note=(
                    "Retroactive corporate split adjustment reconciled via Parquet PiT t-1 guard."
                    if mapped_reason == "SPLIT_ADJUSTED_EXIT"
                    else None
                ),
            )
            if ticker_filter and ticker_filter not in dto.ticker:
                continue
            if reason_filter and dto.exit_reason != reason_filter:
                continue
            transformed.append(dto)

        transformed.sort(key=lambda item: (item.exit_date, item.trade_id), reverse=True)
        total_count = len(transformed)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = transformed[start_idx:end_idx]

        return AuditLedgerResponse(
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=page_items,
        )

    # -------------------------------------------------------------------------
    # Internal Cloud Scheduler EOD Cache-Invalidation Webhook (Token-Protected)
    # -------------------------------------------------------------------------

    @fastapi_app.post(
        "/api/internal/trigger-eod",
        response_model=InternalTriggerEODResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def trigger_eod_cache_invalidation(
        request: Request,
        x_sirix_scheduler_token: Optional[str] = Header(
            default=None,
            alias="X-Sirix-Scheduler-Token",
        ),
        reader: StatelessGCSStateReader = Depends(get_reader),
    ) -> InternalTriggerEODResponse:
        _ = request
        verify_internal_scheduler_token(x_sirix_scheduler_token)
        reader.invalidate_cache()
        return InternalTriggerEODResponse(
            status="accepted",
            cache_invalidated=True,
            triggered_at_utc=datetime.now(timezone.utc),
        )

    # -------------------------------------------------------------------------
    # Unmatched /api/* Catch-All (Never fall through to SPA index.html)
    # -------------------------------------------------------------------------

    @fastapi_app.api_route(
        "/api/{rest_of_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def unmatched_api_route(rest_of_path: str) -> JSONResponse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API endpoint '/api/{rest_of_path}' does not exist.",
        )

    # -------------------------------------------------------------------------
    # Single-Origin PWA Assets & HTML5 SPA Catch-All Router
    # -------------------------------------------------------------------------

    @fastapi_app.get("/manifest.webmanifest", include_in_schema=False)
    async def serve_pwa_manifest(request: Request) -> Response:
        gui_dir: Path = request.app.state.static_gui_dir
        manifest_path = (gui_dir / "manifest.webmanifest").resolve()
        if manifest_path.is_file():
            return FileResponse(
                path=manifest_path,
                media_type="application/manifest+json",
                headers={"Cache-Control": "public, max-age=3600"},
            )
        fallback_manifest = (resolved_settings.base_dir / "frontend" / "public" / "manifest.webmanifest").resolve()
        if fallback_manifest.is_file():
            return FileResponse(
                path=fallback_manifest,
                media_type="application/manifest+json",
                headers={"Cache-Control": "public, max-age=3600"},
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifest not found.")

    @fastapi_app.get("/sw.js", include_in_schema=False)
    async def serve_service_worker(request: Request) -> Response:
        gui_dir: Path = request.app.state.static_gui_dir
        sw_path = (gui_dir / "sw.js").resolve()
        no_cache_headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        if sw_path.is_file():
            return FileResponse(
                path=sw_path,
                media_type="application/javascript",
                headers=no_cache_headers,
            )
        fallback_sw = (resolved_settings.base_dir / "frontend" / "public" / "sw.js").resolve()
        if fallback_sw.is_file():
            return FileResponse(
                path=fallback_sw,
                media_type="application/javascript",
                headers=no_cache_headers,
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service worker not found.")

    @fastapi_app.get("/", include_in_schema=False)
    @fastapi_app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_spa_or_static(request: Request, spa_path: str = "") -> Response:
        gui_dir: Path = request.app.state.static_gui_dir
        clean_rel = spa_path.lstrip("/")

        if clean_rel and gui_dir.is_dir():
            candidate = (gui_dir / clean_rel).resolve()
            if str(candidate).startswith(str(gui_dir)) and candidate.is_file():
                return FileResponse(path=candidate)

        index_html = (gui_dir / "index.html").resolve()
        if index_html.is_file():
            return FileResponse(
                path=index_html,
                media_type="text/html",
                headers={"Cache-Control": "no-cache"},
            )

        return HTMLResponse(
            status_code=status.HTTP_200_OK,
            content=(
                "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>SIRIX Quantitative Telemetry</title></head>"
                "<body><div id='root'>SIRIX Single-Origin API Ready</div></body></html>"
            ),
        )

    return fastapi_app


app: FastAPI = create_app()

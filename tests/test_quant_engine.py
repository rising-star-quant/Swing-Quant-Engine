from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Dict
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

try:
    from src.config import SystemSettings
    from src.quant_engine import (
        FeatureEngineer,
        MetaLabelingBacktestEngine,
        PrimaryScreeningEngine,
        TenantPortfolioReconciler,
    )
    from src.sandbox_runner import SandboxDryRunHarness
    from src.schemas import (
        DirectionalSignalSchema,
        ExitReason,
        IndexConfigSchema,
        IndexTier,
        MetaLabeledSignalSchema,
        TripleBarrierPositionSchema,
        UserIdentitySchema,
        UserRole,
        VirtualPortfolioLedgerSchema,
    )
    from src.security import (
        AuthenticationError,
        AuthorizationError,
        JWTManager,
        PasswordManager,
        TenantSecurityGuard,
    )
    from src.storage import (
        CorporateActionSplitDetectedError,
        ParquetMarketDataRepository,
    )
except ImportError:
    from config import SystemSettings  # type: ignore[no-redef]
    from quant_engine import (  # type: ignore[no-redef]
        FeatureEngineer,
        MetaLabelingBacktestEngine,
        PrimaryScreeningEngine,
        TenantPortfolioReconciler,
    )
    from sandbox_runner import SandboxDryRunHarness  # type: ignore[no-redef]
    from schemas import (  # type: ignore[no-redef]
        DirectionalSignalSchema,
        ExitReason,
        IndexConfigSchema,
        IndexTier,
        MetaLabeledSignalSchema,
        TripleBarrierPositionSchema,
        UserIdentitySchema,
        UserRole,
        VirtualPortfolioLedgerSchema,
    )
    from security import (  # type: ignore[no-redef]
        AuthenticationError,
        AuthorizationError,
        JWTManager,
        PasswordManager,
        TenantSecurityGuard,
    )
    from storage import (  # type: ignore[no-redef]
        CorporateActionSplitDetectedError,
        ParquetMarketDataRepository,
    )


# =============================================================================
# SHARED TEST FIXTURES & SYNTHETIC TIME-SERIES FACTORIES
# =============================================================================


@pytest.fixture
def sample_index_config() -> IndexConfigSchema:
    return IndexConfigSchema(
        index_id="RUT",
        display_name="Russell 2000 Small-Cap",
        benchmark_ticker="IWM",
        tier=IndexTier.SMALL_CAP,
        is_active=True,
        min_price=5.0,
        min_adv_30d=500_000,
        max_relative_spread=0.005,
        volume_surge_multiplier=1.5,
        weight_momentum=0.45,
        weight_volume=0.30,
        weight_rs=0.25,
        k_stop_atr=2.0,
        k_profit_atr=4.5,
        max_holding_bars=14,
    )


@pytest.fixture
def sample_directional_signal() -> DirectionalSignalSchema:
    return DirectionalSignalSchema(
        as_of_date=date(2026, 11, 10),
        ticker="ALPHA",
        index_id="RUT",
        side=1,
        close_price=100.0,
        atr_14=2.5,
        adv_30d=1_800_000.0,
        vol_adj_momentum=2.15,
        volume_zscore=2.60,
        norm_relative_strength=1.45,
        primary_score=88.5,
    )


def _build_ohlcv_dataframe(
    num_days: int = 260,
    end_date: date = date(2026, 11, 10),
    base_price: float = 50.0,
    daily_drift: float = 0.0015,
    base_volume: float = 1_500_000.0,
    trigger_breakout_on_last_bar: bool = False,
) -> pd.DataFrame:
    bdate_index = pd.bdate_range(end=pd.Timestamp(end_date), periods=num_days).normalize()
    bdate_index.name = "Date"

    opens = np.zeros(num_days, dtype=np.float64)
    highs = np.zeros(num_days, dtype=np.float64)
    lows = np.zeros(num_days, dtype=np.float64)
    closes = np.zeros(num_days, dtype=np.float64)
    volumes = np.zeros(num_days, dtype=np.float64)

    price = base_price
    for i in range(num_days):
        wave = 0.002 * np.sin(i * 0.25)
        close_p = max(1.0, price * (1.0 + daily_drift + wave))
        open_p = close_p * 0.996
        high_p = max(open_p, close_p) * 1.006
        low_p = min(open_p, close_p) * 0.994
        vol = base_volume * (1.0 + 0.05 * np.cos(i * 0.3))

        if trigger_breakout_on_last_bar and i == num_days - 1:
            prior_high = float(np.max(highs[max(0, i - 20) : i]))
            close_p = max(close_p * 1.05, prior_high * 1.02)
            open_p = close_p * 0.98
            high_p = close_p * 1.005
            low_p = open_p * 0.995
            vol = base_volume * 2.8

        opens[i] = round(open_p, 4)
        highs[i] = round(high_p, 4)
        lows[i] = round(low_p, 4)
        closes[i] = round(close_p, 4)
        volumes[i] = round(max(100.0, vol), 0)
        price = close_p

    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        },
        index=bdate_index,
    )


# =============================================================================
# 1. TEST CATEGORY 1 — PYDANTIC V2 SCHEMA & GEOMETRIC INVARIANTS (src/schemas.py)
# =============================================================================


def test_index_config_enforces_asymmetric_rr() -> None:
    """
    Verifies IndexConfigSchema raises ValidationError when:
    1. k_profit_atr < 2.0 * k_stop_atr (violating >= 2:1 Reward-to-Risk expectancy).
    2. Component scoring weights (weight_momentum + weight_volume + weight_rs) != 1.0.
    """
    # 1. Violate asymmetric R:R (k_stop_atr=2.5 requires k_profit_atr >= 5.0)
    with pytest.raises(ValidationError, match="EXPECTANCY VIOLATION"):
        IndexConfigSchema(
            index_id="RUT",
            display_name="Russell 2000",
            benchmark_ticker="IWM",
            tier=IndexTier.SMALL_CAP,
            k_stop_atr=2.5,
            k_profit_atr=4.0,
        )

    # 2. Violate convex scoring weight normalization (0.50 + 0.30 + 0.30 = 1.10 != 1.0)
    with pytest.raises(ValidationError, match="WEIGHT NORMALIZATION VIOLATION"):
        IndexConfigSchema(
            index_id="MID",
            display_name="S&P MidCap 400",
            benchmark_ticker="MDY",
            tier=IndexTier.MID_CAP,
            weight_momentum=0.50,
            weight_volume=0.30,
            weight_rs=0.30,
            k_stop_atr=2.0,
            k_profit_atr=4.5,
        )

    # 3. Valid configuration passes cleanly
    valid_cfg = IndexConfigSchema(
        index_id="spx",
        display_name="S&P 500 Large-Cap",
        benchmark_ticker="spy",
        tier=IndexTier.LARGE_CAP,
        weight_momentum=0.45,
        weight_volume=0.30,
        weight_rs=0.25,
        k_stop_atr=2.0,
        k_profit_atr=4.0,
    )
    assert valid_cfg.index_id == "SPX"
    assert valid_cfg.benchmark_ticker == "SPY"


def test_meta_labeled_signal_barrier_geometry_and_ev_gate(
    sample_directional_signal: DirectionalSignalSchema,
) -> None:
    """
    Verifies MetaLabeledSignalSchema rejects:
    1. Invalid barrier geometry where initial_stop_price >= close_price or take_profit_price <= close_price.
    2. is_approved=True when historical_ev_r_multiple <= 0.0.
    3. is_approved=False when meta_conviction_scalar != 0.0.
    """
    # 1a. Invalid stop barrier (Stop >= Entry)
    with pytest.raises(ValidationError, match="TRIPLE-BARRIER GEOMETRY VIOLATION"):
        MetaLabeledSignalSchema(
            primary_signal=sample_directional_signal,
            backtest_lookback_days=500,
            historical_win_rate=0.55,
            historical_ev_r_multiple=0.65,
            meta_conviction_scalar=0.90,
            is_approved=True,
            initial_stop_price=100.0,
            take_profit_price=112.0,
            max_holding_bars=14,
        )

    # 1b. Invalid target barrier (Target <= Entry)
    with pytest.raises(ValidationError, match="TRIPLE-BARRIER GEOMETRY VIOLATION"):
        MetaLabeledSignalSchema(
            primary_signal=sample_directional_signal,
            backtest_lookback_days=500,
            historical_win_rate=0.55,
            historical_ev_r_multiple=0.65,
            meta_conviction_scalar=0.90,
            is_approved=True,
            initial_stop_price=95.0,
            take_profit_price=99.5,
            max_holding_bars=14,
        )

    # 2. Approved signal with non-positive EV (historical_ev_r_multiple <= 0)
    with pytest.raises(ValidationError, match="APPROVAL GATE BREACH"):
        MetaLabeledSignalSchema(
            primary_signal=sample_directional_signal,
            backtest_lookback_days=500,
            historical_win_rate=0.45,
            historical_ev_r_multiple=-0.15,
            meta_conviction_scalar=0.75,
            is_approved=True,
            initial_stop_price=95.0,
            take_profit_price=112.0,
            max_holding_bars=14,
        )

    # 3. Rejected signal with non-zero conviction scalar
    with pytest.raises(ValidationError, match="INACTIVE CONVICTION BREACH"):
        MetaLabeledSignalSchema(
            primary_signal=sample_directional_signal,
            backtest_lookback_days=500,
            historical_win_rate=0.25,
            historical_ev_r_multiple=-0.30,
            meta_conviction_scalar=0.50,
            is_approved=False,
            initial_stop_price=95.0,
            take_profit_price=112.0,
            max_holding_bars=14,
        )


def test_ratchet_trailing_stop_never_moves_downward() -> None:
    """
    Verifies TripleBarrierPositionSchema.ratchet_trailing_stop:
    1. Advances trailing_stop_price upward when highest_high_since_entry increases.
    2. Strictly refuses to lower trailing_stop_price when subsequent price pulls back or ATR widens.
    3. Raises ValueError on explicit downward update_trailing_stop calls.
    4. Raises ValueError on duplicate or past current_date (Point-in-Time protection).
    """
    user_id = uuid4()
    portfolio_id = uuid4()
    entry_dt = date(2026, 11, 2)

    position = TripleBarrierPositionSchema(
        user_id=user_id,
        portfolio_id=portfolio_id,
        ticker="ALPHA",
        index_id="RUT",
        entry_date=entry_dt,
        entry_price=100.0,
        shares=50,
        entry_atr_14=2.0,
        initial_stop_price=95.0,
        trailing_stop_price=95.0,
        take_profit_price=110.0,
        highest_high_since_entry=100.0,
        bars_held=0,
        max_holding_bars=14,
        last_updated_date=entry_dt,
    )

    assert position.open_dollar_risk == 250.0

    # Day 1: Price rallies to 106.0 -> Candidate Stop = 106.0 - (2.5 * 2.0) = 101.0 (> 95.0)
    position.ratchet_trailing_stop(
        current_high=106.0,
        current_atr_14=2.0,
        k_trail=2.5,
        current_date=date(2026, 11, 3),
    )
    assert position.trailing_stop_price == 101.0
    assert position.highest_high_since_entry == 106.0
    assert position.bars_held == 1
    assert position.open_dollar_risk == 0.0  # Trailing stop is now above entry_price

    # Day 2: Price pulls back to 102.0 and ATR spikes to 4.0 -> Candidate = 106.0 - 10.0 = 96.0 (< 101.0)
    # Trailing stop MUST remain locked at 101.0
    position.ratchet_trailing_stop(
        current_high=102.0,
        current_atr_14=4.0,
        k_trail=2.5,
        current_date=date(2026, 11, 4),
    )
    assert position.trailing_stop_price == 101.0
    assert position.bars_held == 2

    # Explicit downward stop mutation attempt must raise ValueError
    with pytest.raises(ValueError, match="DOWNWARD STOP MODIFICATION REJECTED"):
        position.update_trailing_stop(99.0)

    # Duplicate or past date must raise ValueError (Point-in-Time protection)
    with pytest.raises(ValueError, match="POINT-IN-TIME DATE VIOLATION"):
        position.ratchet_trailing_stop(
            current_high=108.0,
            current_atr_14=2.0,
            k_trail=2.5,
            current_date=date(2026, 11, 4),
        )

    with pytest.raises(ValueError, match="POINT-IN-TIME DATE VIOLATION"):
        position.ratchet_trailing_stop(
            current_high=108.0,
            current_atr_14=2.0,
            k_trail=2.5,
            current_date=date(2026, 11, 3),
        )


# =============================================================================
# 2. TEST CATEGORY 2 — MULTI-TENANT ISOLATION & SECURITY (schemas.py, security.py)
# =============================================================================


def test_cross_tenant_position_injection_blocked() -> None:
    """
    Verifies VirtualPortfolioLedgerSchema raises ValidationError ('CRITICAL SECURITY BREACH')
    if a TripleBarrierPositionSchema belonging to User B is inserted into User A's ledger.
    """
    user_a = uuid4()
    portfolio_a = uuid4()
    user_b = uuid4()

    foreign_position = TripleBarrierPositionSchema(
        user_id=user_b,
        portfolio_id=portfolio_a,
        ticker="NVDA",
        index_id="RUT",
        entry_date=date(2026, 11, 10),
        entry_price=120.0,
        shares=25,
        entry_atr_14=3.0,
        initial_stop_price=114.0,
        trailing_stop_price=114.0,
        take_profit_price=135.0,
        highest_high_since_entry=121.0,
        last_updated_date=date(2026, 11, 10),
    )

    with pytest.raises(ValidationError, match="CRITICAL SECURITY BREACH"):
        VirtualPortfolioLedgerSchema(
            portfolio_id=portfolio_a,
            user_id=user_a,
            as_of_date=date(2026, 11, 10),
            cash_balance=97_000.0,
            total_equity=100_000.0,
            open_positions={"NVDA": foreign_position},
        )


def test_portfolio_heat_circuit_breaker() -> None:
    """
    Verifies VirtualPortfolioLedgerSchema raises ValidationError when cumulative
    open dollar risk exceeds max_portfolio_heat_pct (6.0%).
    """
    user_a = uuid4()
    portfolio_a = uuid4()

    # Open risk = (100.0 - 93.0) * 1,000 shares = $7,000 on $100,000 equity = 7.0% (> 6.0% cap)
    excessive_heat_position = TripleBarrierPositionSchema(
        user_id=user_a,
        portfolio_id=portfolio_a,
        ticker="TSLA",
        index_id="MID",
        entry_date=date(2026, 11, 10),
        entry_price=100.0,
        shares=1_000,
        entry_atr_14=3.5,
        initial_stop_price=93.0,
        trailing_stop_price=93.0,
        take_profit_price=115.0,
        highest_high_since_entry=100.0,
        last_updated_date=date(2026, 11, 10),
    )

    with pytest.raises(ValidationError, match="PORTFOLIO HEAT CIRCUIT BREAKER BREACHED"):
        VirtualPortfolioLedgerSchema(
            portfolio_id=portfolio_a,
            user_id=user_a,
            as_of_date=date(2026, 11, 10),
            cash_balance=0.0,
            total_equity=100_000.0,
            max_portfolio_heat_pct=0.06,
            open_positions={"TSLA": excessive_heat_position},
        )


def test_argon2_password_and_jwt_rbac_isolation() -> None:
    """
    Verifies:
    1. PasswordManager hashes and verifies Argon2id passwords and rejects weak/wrong passwords.
    2. JWTManager issues and cryptographically verifies stateless JWT tokens and blocks inactive accounts.
    3. TenantSecurityGuard.enforce_tenant_access blocks cross-tenant access (AuthorizationError).
    """
    pwd_manager = PasswordManager(time_cost=2, memory_cost=16384, parallelism=2)

    with pytest.raises(ValueError, match="at least 10 characters"):
        pwd_manager.hash_password("short123")

    strong_secret = "RenTech_Medallion_Argon2id_Pass!2026"
    password_hash = pwd_manager.hash_password(strong_secret)
    assert password_hash.startswith("$argon2id$")
    assert pwd_manager.verify_password(strong_secret, password_hash) is True
    assert pwd_manager.verify_password("Wrong_Password_Attempt!2026", password_hash) is False
    assert pwd_manager.needs_rehash(password_hash) is False

    settings = SystemSettings(
        environment="test",
        jwt_secret_key="0123456789abcdef0123456789abcdef_SUPER_SECRET_KEY_256",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
    )
    jwt_manager = JWTManager(settings=settings)

    tenant_a_user = UserIdentitySchema(
        user_id=uuid4(),
        username="trader_alpha",
        email="alpha@quant.io",
        password_hash=password_hash,
        role=UserRole.TRADER,
        is_active=True,
    )
    tenant_b_user_id = uuid4()

    token = jwt_manager.create_access_token(tenant_a_user)
    payload = jwt_manager.decode_and_verify_token(token)
    assert payload.sub == tenant_a_user.user_id
    assert payload.role == UserRole.TRADER

    # Same-tenant access succeeds
    TenantSecurityGuard.enforce_tenant_access(payload, resource_owner_id=tenant_a_user.user_id)

    # Cross-tenant access raises AuthorizationError
    with pytest.raises(AuthorizationError, match="Cross-tenant isolation breach"):
        TenantSecurityGuard.enforce_tenant_access(payload, resource_owner_id=tenant_b_user_id)

    # Non-admin worker guard raises AuthorizationError
    with pytest.raises(AuthorizationError, match="ADMIN role required"):
        TenantSecurityGuard.require_admin_worker(payload)

    # RLS claims match tenant subject and role
    rls_claims = TenantSecurityGuard.generate_supabase_rls_claims(payload)
    assert rls_claims["request.jwt.claim.sub"] == str(tenant_a_user.user_id)
    assert rls_claims["request.jwt.claim.role"] == "TRADER"

    # Inactive user cannot mint tokens
    inactive_user = UserIdentitySchema(
        user_id=uuid4(),
        username="inactive_trader",
        email="inactive@quant.io",
        password_hash=password_hash,
        role=UserRole.TRADER,
        is_active=False,
    )
    with pytest.raises(AuthenticationError, match="Inactive user account"):
        jwt_manager.create_access_token(inactive_user)


# =============================================================================
# 3. TEST CATEGORY 3 — APACHE PARQUET ROLLING WINDOW & t-1 SPLIT DETECTION
# =============================================================================


def test_parquet_rolling_window_and_t_minus_1_split_detection(tmp_path: Path) -> None:
    """
    Verifies ParquetMarketDataRepository:
    1. Saves 250 days of OHLCV data atomically to Parquet.
    2. Upserts an incremental batch matching t-1 close cleanly and trims to max_window_days.
    3. Detects a 2-for-1 stock split on t-1 (incoming_close = 0.5 * cached_close) and raises
       CorporateActionSplitDetectedError.
    """
    parquet_dir = tmp_path / "ohlcv_parquet"
    settings = SystemSettings(
        environment="test",
        base_dir=tmp_path,
        parquet_data_dir=parquet_dir,
        virtual_portfolio_path=tmp_path / "virtual_portfolio.json",
        backtest_lookback_days=250,
        split_detection_tolerance=0.15,
    )
    repo = ParquetMarketDataRepository(settings=settings)

    t_minus_1 = date(2026, 11, 9)
    t_current = date(2026, 11, 10)

    initial_250d_df = _build_ohlcv_dataframe(
        num_days=250,
        end_date=t_minus_1,
        base_price=100.0,
    )
    repo.save_ohlcv("SPLIT_TEST", initial_250d_df)

    cached_df = repo.load_ohlcv("SPLIT_TEST")
    assert cached_df is not None
    assert len(cached_df) == 250
    assert repo.get_latest_cached_date("SPLIT_TEST") == t_minus_1

    cached_t_minus_1_close = float(cached_df.loc[pd.Timestamp(t_minus_1), "Close"])

    # 1. Clean incremental delta upsert (t-1 close matches cached close within tolerance)
    clean_delta_df = pd.DataFrame(
        {
            "Open": [cached_t_minus_1_close * 0.995, cached_t_minus_1_close * 1.005],
            "High": [cached_t_minus_1_close * 1.010, cached_t_minus_1_close * 1.020],
            "Low": [cached_t_minus_1_close * 0.990, cached_t_minus_1_close * 0.998],
            "Close": [cached_t_minus_1_close, cached_t_minus_1_close * 1.015],
            "Volume": [1_500_000.0, 1_750_000.0],
        },
        index=pd.DatetimeIndex([pd.Timestamp(t_minus_1), pd.Timestamp(t_current)], name="Date"),
    )

    upserted_df = repo.upsert_ohlcv("SPLIT_TEST", clean_delta_df, max_window_days=250)
    assert len(upserted_df) == 250
    assert upserted_df.index[-1] == pd.Timestamp(t_current)

    # 2. Simulate a 2-for-1 retroactive stock split on t_current (incoming close = 0.5 * cached close)
    latest_cached_close = float(upserted_df.loc[pd.Timestamp(t_current), "Close"])
    t_plus_1 = date(2026, 11, 11)
    split_delta_df = pd.DataFrame(
        {
            "Open": [latest_cached_close * 0.5, latest_cached_close * 0.51],
            "High": [latest_cached_close * 0.52, latest_cached_close * 0.53],
            "Low": [latest_cached_close * 0.49, latest_cached_close * 0.50],
            "Close": [latest_cached_close * 0.5, latest_cached_close * 0.51],
            "Volume": [3_000_000.0, 3_200_000.0],
        },
        index=pd.DatetimeIndex([pd.Timestamp(t_current), pd.Timestamp(t_plus_1)], name="Date"),
    )

    with pytest.raises(CorporateActionSplitDetectedError, match="Split/adjustment detected"):
        repo.upsert_ohlcv("SPLIT_TEST", split_delta_df, max_window_days=250)


# =============================================================================
# 4. TEST CATEGORY 4 — QUANT SCREENING, META-LABELING & PORTFOLIO RECONCILER
# =============================================================================


def test_simons_liquidity_gates_reject_penny_and_illiquid_stocks(
    sample_index_config: IndexConfigSchema,
) -> None:
    """
    Verifies PrimaryScreeningEngine rejects stocks with Close < $5.00 or ADV_30 < 500,000,
    while passing liquid high-momentum breakout candidates.
    """
    as_of = date(2026, 11, 10)
    benchmark_df = _build_ohlcv_dataframe(
        num_days=250,
        end_date=as_of,
        base_price=100.0,
        daily_drift=0.0002,
        base_volume=5_000_000.0,
    )

    # 1. Penny stock: Close < $5.00
    penny_df = _build_ohlcv_dataframe(
        num_days=250,
        end_date=as_of,
        base_price=1.50,
        daily_drift=0.001,
        base_volume=2_000_000.0,
        trigger_breakout_on_last_bar=True,
    )

    # 2. Illiquid stock: ADV_30 < 500,000
    illiquid_df = _build_ohlcv_dataframe(
        num_days=250,
        end_date=as_of,
        base_price=45.0,
        daily_drift=0.002,
        base_volume=120_000.0,
        trigger_breakout_on_last_bar=True,
    )

    # 3. Liquid breakout leader: Close > $50, ADV_30 > 1.5M, 20d breakout on 2.8x volume
    liquid_leader_df = _build_ohlcv_dataframe(
        num_days=250,
        end_date=as_of,
        base_price=50.0,
        daily_drift=0.0025,
        base_volume=1_800_000.0,
        trigger_breakout_on_last_bar=True,
    )

    ohlcv_map: Dict[str, pd.DataFrame] = {
        "PENNY": penny_df,
        "ILLIQ": illiquid_df,
        "LEADER": liquid_leader_df,
    }

    screening_engine = PrimaryScreeningEngine()
    signals = screening_engine.screen_index_universe(
        ohlcv_map=ohlcv_map,
        benchmark_df=benchmark_df,
        index_cfg=sample_index_config,
        as_of_date=as_of,
    )

    screened_tickers = [sig.ticker for sig in signals]
    assert "PENNY" not in screened_tickers
    assert "ILLIQ" not in screened_tickers
    assert "LEADER" in screened_tickers


def test_500d_triple_barrier_backtest_vetoes_negative_ev(
    sample_index_config: IndexConfigSchema,
    sample_directional_signal: DirectionalSignalSchema,
) -> None:
    """
    Feeds a synthetic choppy/mean-reverting 500-day series (where false breakouts
    immediately reverse into the lower stop barrier) into MetaLabelingBacktestEngine.evaluate_candidate
    and asserts is_approved is False and meta_conviction_scalar == 0.0.
    """
    as_of = sample_directional_signal.as_of_date
    num_days = 500
    bdate_index = pd.bdate_range(end=pd.Timestamp(as_of), periods=num_days).normalize()
    bdate_index.name = "Date"

    benchmark_df = _build_ohlcv_dataframe(
        num_days=num_days,
        end_date=as_of,
        base_price=100.0,
        daily_drift=0.0001,
        base_volume=4_000_000.0,
    )

    # Construct a bull-trap series: periodic breakout spikes that immediately gap down and hit stop-loss
    opens = np.zeros(num_days, dtype=np.float64)
    highs = np.zeros(num_days, dtype=np.float64)
    lows = np.zeros(num_days, dtype=np.float64)
    closes = np.zeros(num_days, dtype=np.float64)
    volumes = np.zeros(num_days, dtype=np.float64)

    price = 60.0
    trap_reversal_days = 0
    for i in range(num_days):
        if i >= 210 and i < num_days - 20 and (i - 210) % 25 == 0:
            prior_20_high = float(np.max(highs[i - 20 : i]))
            close_p = max(price * 1.04, prior_20_high * 1.01)
            open_p = price * 1.005
            high_p = close_p * 1.005
            low_p = open_p * 0.995
            vol = 3_500_000.0
            trap_reversal_days = 3
        elif trap_reversal_days > 0:
            # Immediate sharp selloff through lower stop barrier
            close_p = price * 0.93
            open_p = price * 0.96
            high_p = open_p * 1.002
            low_p = close_p * 0.99
            vol = 2_500_000.0
            trap_reversal_days -= 1
        else:
            close_p = max(25.0, price * 1.0012)
            open_p = close_p * 0.998
            high_p = close_p * 1.005
            low_p = open_p * 0.995
            vol = 1_500_000.0

        opens[i] = round(open_p, 4)
        highs[i] = round(high_p, 4)
        lows[i] = round(low_p, 4)
        closes[i] = round(close_p, 4)
        volumes[i] = round(vol, 0)
        price = close_p

    choppy_asset_df = pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        },
        index=bdate_index,
    )

    backtest_engine = MetaLabelingBacktestEngine()
    meta_signal = backtest_engine.evaluate_candidate(
        signal=sample_directional_signal,
        asset_df=choppy_asset_df,
        benchmark_df=benchmark_df,
        index_cfg=sample_index_config,
    )

    assert meta_signal.is_approved is False
    assert meta_signal.meta_conviction_scalar == 0.0
    assert meta_signal.historical_ev_r_multiple <= 0.0


def test_tenant_reconciler_triple_barrier_exits_and_heat_capped_sizing(
    sample_index_config: IndexConfigSchema,
) -> None:
    """
    Verifies TenantPortfolioReconciler:
    1. Triggers LOWER_BARRIER_SL, UPPER_BARRIER_TP, and VERTICAL_BARRIER_TIME exits accurately.
    2. Caps new position share sizing so total portfolio heat never breaches 6.0%.
    """
    user_id = uuid4()
    portfolio_id = uuid4()
    prev_dt = date(2026, 11, 9)
    as_of = date(2026, 11, 10)

    ledger = VirtualPortfolioLedgerSchema(
        portfolio_id=portfolio_id,
        user_id=user_id,
        as_of_date=prev_dt,
        cash_balance=70_000.0,
        total_equity=100_000.0,
        max_portfolio_heat_pct=0.06,
        max_concurrent_positions=10,
        subscribed_indices=["RUT"],
        open_positions={
            "SL_POS": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="SL_POS",
                index_id="RUT",
                entry_date=date(2026, 11, 2),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=96.0,
                take_profit_price=109.0,
                highest_high_since_entry=101.0,
                bars_held=4,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
            "TP_POS": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="TP_POS",
                index_id="RUT",
                entry_date=date(2026, 11, 2),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=98.0,
                take_profit_price=109.0,
                highest_high_since_entry=105.0,
                bars_held=5,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
            "TIME_POS": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="TIME_POS",
                index_id="RUT",
                entry_date=date(2026, 10, 20),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=97.0,
                take_profit_price=109.0,
                highest_high_since_entry=103.0,
                bars_held=13,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
        },
    )

    dt_index = pd.DatetimeIndex([pd.Timestamp(as_of)], name="Date")
    ohlcv_map: Dict[str, pd.DataFrame] = {
        "SL_POS": pd.DataFrame(
            {"Open": [98.0], "High": [98.5], "Low": [95.0], "Close": [95.5], "Volume": [1_200_000.0], "ATR_14": [2.0]},
            index=dt_index,
        ),
        "TP_POS": pd.DataFrame(
            {"Open": [108.0], "High": [110.5], "Low": [107.5], "Close": [109.8], "Volume": [1_500_000.0], "ATR_14": [2.0]},
            index=dt_index,
        ),
        "TIME_POS": pd.DataFrame(
            {"Open": [101.0], "High": [102.0], "Low": [99.5], "Close": [101.5], "Volume": [1_100_000.0], "ATR_14": [2.0]},
            index=dt_index,
        ),
    }

    reconciler = TenantPortfolioReconciler()
    closed_audits = reconciler.reconcile_open_positions(
        ledger=ledger,
        ohlcv_map=ohlcv_map,
        index_registry={"RUT": sample_index_config},
        as_of_date=as_of,
    )

    assert len(closed_audits) == 3
    assert len(ledger.open_positions) == 0
    exit_reasons = {audit.ticker: audit.exit_reason for audit in closed_audits}
    assert exit_reasons["SL_POS"] == ExitReason.LOWER_BARRIER_SL
    assert exit_reasons["TP_POS"] == ExitReason.UPPER_BARRIER_TP
    assert exit_reasons["TIME_POS"] == ExitReason.VERTICAL_BARRIER_TIME

    # Now test heat-capped entry sizing across 8 high-conviction signals
    approved_candidates = []
    for k in range(1, 9):
        prim = DirectionalSignalSchema(
            as_of_date=as_of,
            ticker=f"SIG{k:02d}",
            index_id="RUT",
            side=1,
            close_price=50.0,
            atr_14=2.0,
            adv_30d=2_000_000.0,
            vol_adj_momentum=2.0 + 0.1 * k,
            volume_zscore=2.5,
            norm_relative_strength=1.2,
            primary_score=80.0 + k,
        )
        approved_candidates.append(
            MetaLabeledSignalSchema(
                primary_signal=prim,
                backtest_lookback_days=500,
                historical_win_rate=0.62,
                historical_ev_r_multiple=0.85,
                meta_conviction_scalar=1.25,
                is_approved=True,
                initial_stop_price=46.0,
                take_profit_price=59.0,
                max_holding_bars=14,
            )
        )

    opened_positions = reconciler.allocate_new_signals(
        ledger=ledger,
        approved_signals=approved_candidates,
        as_of_date=as_of,
    )

    assert len(opened_positions) > 0
    assert ledger.current_portfolio_heat_pct <= ledger.max_portfolio_heat_pct + 1e-5


# =============================================================================
# 5. TEST CATEGORY 5 — END-TO-END SANDBOX DRY-RUN (src/sandbox_runner.py)
# =============================================================================


def test_end_to_end_sandbox_dry_run() -> None:
    """
    Executes SandboxDryRunHarness().run() across an isolated 3-day multi-tenant
    walk-forward simulation and asserts it returns True.
    """
    harness = SandboxDryRunHarness(seed=42)
    assert harness.run() is True

import {
  AccountTier,
  AuditLogResponse,
  AuthTokenResponse,
  ClosedTradeRecord,
  HoldingSummaryCard,
  PortfolioOverviewResponse,
  PositionDeepDiveResponse,
  TickerSearchResult,
  UserPreferencesResponse,
  UserPreferencesUpdateRequest,
} from '../types/sirix';

const API_BASE_URL = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL || '';

const CACHE_PREFIX = 'sirix_eod_cache_v1_';

/* ==========================================================================
   Deterministic Institutional Sandbox Telemetry (RUT & MID Universes)
   Matches F01, F02, F03 specifications and api/main.py schemas 100%
   ========================================================================== */

const SANDBOX_HOLDINGS_FULL: HoldingSummaryCard[] = [
  {
    ticker: 'CELH',
    company_name: 'Celsius Holdings Inc.',
    universe: 'MID',
    shares: 310,
    entry_price: 58.40,
    current_price: 65.85,
    position_value: 20413.50,
    unrealized_pnl: 2309.50,
    unrealized_pnl_pct: 12.76,
    weight_pct: 18.82,
    days_held: 4,
    max_hold_days: 14,
    time_barrier_urgency: 'FRESH',
    conviction_score: 94.2,
    stop_distance_atr: 2.45,
  },
  {
    ticker: 'FN',
    company_name: 'Fabrinet',
    universe: 'RUT',
    shares: 92,
    entry_price: 214.20,
    current_price: 231.90,
    position_value: 21334.80,
    unrealized_pnl: 1628.40,
    unrealized_pnl_pct: 8.26,
    weight_pct: 19.67,
    days_held: 6,
    max_hold_days: 14,
    time_barrier_urgency: 'FRESH',
    conviction_score: 91.5,
    stop_distance_atr: 2.18,
  },
  {
    ticker: 'MOD',
    company_name: 'Modine Manufacturing Co.',
    universe: 'RUT',
    shares: 185,
    entry_price: 98.50,
    current_price: 104.25,
    position_value: 19286.25,
    unrealized_pnl: 1063.75,
    unrealized_pnl_pct: 5.84,
    weight_pct: 17.78,
    days_held: 9,
    max_hold_days: 14,
    time_barrier_urgency: 'MATURING',
    conviction_score: 88.7,
    stop_distance_atr: 1.92,
  },
  {
    ticker: 'MEDP',
    company_name: 'Medpace Holdings Inc.',
    universe: 'MID',
    shares: 48,
    entry_price: 388.00,
    current_price: 382.40,
    position_value: 18355.20,
    unrealized_pnl: -268.80,
    unrealized_pnl_pct: -1.44,
    weight_pct: 16.92,
    days_held: 11,
    max_hold_days: 14,
    time_barrier_urgency: 'MATURING',
    conviction_score: 84.1,
    stop_distance_atr: 1.35,
  },
  {
    ticker: 'ANF',
    company_name: 'Abercrombie & Fitch Co.',
    universe: 'MID',
    shares: 115,
    entry_price: 148.60,
    current_price: 159.10,
    position_value: 18296.50,
    unrealized_pnl: 1207.50,
    unrealized_pnl_pct: 7.07,
    weight_pct: 16.87,
    days_held: 13,
    max_hold_days: 14,
    time_barrier_urgency: 'CRITICAL',
    conviction_score: 86.9,
    stop_distance_atr: 1.74,
  },
];

const SANDBOX_DEEP_DIVES: Record<string, Omit<PositionDeepDiveResponse, 'account_tier' | 'is_tier_restricted'>> = {
  CELH: {
    ticker: 'CELH',
    company_name: 'Celsius Holdings Inc.',
    universe: 'MID',
    sector: 'Consumer Staples • Functional Beverages',
    entry_date: '2025-05-06',
    days_held: 4,
    max_hold_days: 14,
    days_remaining: 10,
    time_barrier_urgency: 'FRESH',
    shares: 310,
    position_value: 20413.50,
    unrealized_pnl: 2309.50,
    unrealized_pnl_pct: 12.76,
    r_multiple_current: 1.84,
    conviction_score: 94.2,
    momentum_rank_pct: 98.4,
    next_earnings_date: '2025-08-07',
    days_until_earnings: 64,
    earnings_blackout_SAFE: true,
    triple_barrier: {
      take_profit_price: 70.52,
      take_profit_pct: 7.09,
      entry_price: 58.40,
      current_price: 65.85,
      chandelier_stop_price: 60.12,
      chandelier_stop_pct: -8.70,
      atr_14: 2.34,
      stop_distance_atr: 2.45,
    },
    recent_candles: [
      { date: '2025-05-02', open: 56.90, high: 58.15, low: 56.40, close: 57.85, volume: 6820000 },
      { date: '2025-05-05', open: 57.95, high: 59.10, low: 57.60, close: 58.40, volume: 7450000 },
      { date: '2025-05-06', open: 58.45, high: 61.20, low: 58.30, close: 60.85, volume: 9120000 },
      { date: '2025-05-07', open: 60.90, high: 62.75, low: 60.40, close: 62.10, volume: 8340000 },
      { date: '2025-05-08', open: 62.20, high: 64.50, low: 61.95, close: 63.95, volume: 7910000 },
      { date: '2025-05-09', open: 64.05, high: 65.20, low: 63.50, close: 64.70, volume: 6980000 },
      { date: '2025-05-12', open: 64.80, high: 66.40, low: 64.55, close: 65.85, volume: 8150000 },
    ],
    strategy_rationale:
      'Triggered Stage-4 Breakout Rank #3 across S&P MidCap 400 with Choppiness Index at 39.4 (strong directional trend) and 2.1x institutional volume expansion. Trailing Chandelier Stop has ratcheted above entry ($60.12 vs $58.40), locking in +0.42R risk-free floor.',
  },
  FN: {
    ticker: 'FN',
    company_name: 'Fabrinet',
    universe: 'RUT',
    sector: 'Information Technology • Optical Packaging',
    entry_date: '2025-05-02',
    days_held: 6,
    max_hold_days: 14,
    days_remaining: 8,
    time_barrier_urgency: 'FRESH',
    shares: 92,
    position_value: 21334.80,
    unrealized_pnl: 1628.40,
    unrealized_pnl_pct: 8.26,
    r_multiple_current: 1.38,
    conviction_score: 91.5,
    momentum_rank_pct: 96.8,
    next_earnings_date: '2025-08-18',
    days_until_earnings: 75,
    earnings_blackout_SAFE: true,
    triple_barrier: {
      take_profit_price: 252.60,
      take_profit_pct: 8.93,
      entry_price: 214.20,
      current_price: 231.90,
      chandelier_stop_price: 216.85,
      chandelier_stop_pct: -6.49,
      atr_14: 6.90,
      stop_distance_atr: 2.18,
    },
    recent_candles: [
      { date: '2025-05-02', open: 213.80, high: 217.50, low: 212.90, close: 214.20, volume: 910000 },
      { date: '2025-05-05', open: 214.90, high: 219.80, low: 214.20, close: 218.60, volume: 980000 },
      { date: '2025-05-06', open: 218.50, high: 223.40, low: 217.90, close: 222.10, volume: 1050000 },
      { date: '2025-05-07', open: 222.40, high: 226.90, low: 221.30, close: 225.75, volume: 1120000 },
      { date: '2025-05-08', open: 225.50, high: 228.40, low: 223.80, close: 227.15, volume: 890000 },
      { date: '2025-05-09', open: 227.30, high: 230.60, low: 226.70, close: 229.80, volume: 940000 },
      { date: '2025-05-12', open: 230.10, high: 233.20, low: 229.40, close: 231.90, volume: 1080000 },
    ],
    strategy_rationale:
      'Top-decile Russell 2000 optical interconnect leader with persistent 60-day risk-adjusted momentum and low intraday wick noise. Chandelier Stop has ratcheted above entry anchor ($216.85), eliminating principal downside.',
  },
  MOD: {
    ticker: 'MOD',
    company_name: 'Modine Manufacturing Co.',
    universe: 'RUT',
    sector: 'Industrials • Data Center Thermal Systems',
    entry_date: '2025-04-29',
    days_held: 9,
    max_hold_days: 14,
    days_remaining: 5,
    time_barrier_urgency: 'MATURING',
    shares: 185,
    position_value: 19286.25,
    unrealized_pnl: 1063.75,
    unrealized_pnl_pct: 5.84,
    r_multiple_current: 0.96,
    conviction_score: 88.7,
    momentum_rank_pct: 93.1,
    next_earnings_date: '2025-07-30',
    days_until_earnings: 58,
    earnings_blackout_SAFE: true,
    triple_barrier: {
      take_profit_price: 116.80,
      take_profit_pct: 12.04,
      entry_price: 98.50,
      current_price: 104.25,
      chandelier_stop_price: 97.60,
      chandelier_stop_pct: -6.38,
      atr_14: 3.46,
      stop_distance_atr: 1.92,
    },
    recent_candles: [
      { date: '2025-05-02', open: 99.40, high: 101.20, low: 98.80, close: 100.65, volume: 1420000 },
      { date: '2025-05-05', open: 100.80, high: 102.50, low: 100.10, close: 101.90, volume: 1380000 },
      { date: '2025-05-06', open: 101.70, high: 103.10, low: 100.95, close: 102.40, volume: 1290000 },
      { date: '2025-05-07', open: 102.50, high: 103.85, low: 101.60, close: 101.95, volume: 1190000 },
      { date: '2025-05-08', open: 102.10, high: 104.10, low: 101.85, close: 103.40, volume: 1350000 },
      { date: '2025-05-09', open: 103.50, high: 104.60, low: 102.90, close: 103.85, volume: 1260000 },
      { date: '2025-05-12', open: 103.90, high: 105.15, low: 103.40, close: 104.25, volume: 1410000 },
    ],
    strategy_rationale:
      'Entered on high-tight flag breakout in RUT industrial momentum basket. Currently Day 9 of 14; requires +12.04% continuation to hit Ceiling before the Day-14 Time Barrier recycles capital.',
  },
  MEDP: {
    ticker: 'MEDP',
    company_name: 'Medpace Holdings Inc.',
    universe: 'MID',
    sector: 'Health Care • Clinical CRO',
    entry_date: '2025-04-25',
    days_held: 11,
    max_hold_days: 14,
    days_remaining: 3,
    time_barrier_urgency: 'MATURING',
    shares: 48,
    position_value: 18355.20,
    unrealized_pnl: -268.80,
    unrealized_pnl_pct: -1.44,
    r_multiple_current: -0.24,
    conviction_score: 84.1,
    momentum_rank_pct: 89.2,
    next_earnings_date: '2025-07-22',
    days_until_earnings: 50,
    earnings_blackout_SAFE: true,
    triple_barrier: {
      take_profit_price: 448.50,
      take_profit_pct: 17.29,
      entry_price: 388.00,
      current_price: 382.40,
      chandelier_stop_price: 368.10,
      chandelier_stop_pct: -3.74,
      atr_14: 10.59,
      stop_distance_atr: 1.35,
    },
    recent_candles: [
      { date: '2025-05-02', open: 389.50, high: 393.00, low: 386.20, close: 388.90, volume: 310000 },
      { date: '2025-05-05', open: 388.80, high: 391.40, low: 385.00, close: 386.50, volume: 295000 },
      { date: '2025-05-06', open: 386.20, high: 388.70, low: 383.10, close: 384.80, volume: 305000 },
      { date: '2025-05-07', open: 384.90, high: 387.20, low: 381.90, close: 383.60, volume: 280000 },
      { date: '2025-05-08', open: 383.50, high: 386.00, low: 380.40, close: 381.90, volume: 315000 },
      { date: '2025-05-09', open: 382.00, high: 384.80, low: 380.90, close: 383.10, volume: 270000 },
      { date: '2025-05-12', open: 383.20, high: 385.10, low: 381.00, close: 382.40, volume: 290000 },
    ],
    strategy_rationale:
      'Consolidating slightly below entry anchor (-0.24R) while remaining 1.35 ATR above the Chandelier Stop floor ($368.10). Protected by the 14-day Time Barrier in 3 trading days if momentum fails to resume.',
  },
  ANF: {
    ticker: 'ANF',
    company_name: 'Abercrombie & Fitch Co.',
    universe: 'MID',
    sector: 'Consumer Discretionary • Specialty Retail',
    entry_date: '2025-04-23',
    days_held: 13,
    max_hold_days: 14,
    days_remaining: 1,
    time_barrier_urgency: 'CRITICAL',
    shares: 115,
    position_value: 18296.50,
    unrealized_pnl: 1207.50,
    unrealized_pnl_pct: 7.07,
    r_multiple_current: 1.15,
    conviction_score: 86.9,
    momentum_rank_pct: 91.4,
    next_earnings_date: '2025-05-28',
    days_until_earnings: 12,
    earnings_blackout_SAFE: true,
    triple_barrier: {
      take_profit_price: 174.20,
      take_profit_pct: 9.49,
      entry_price: 148.60,
      current_price: 159.10,
      chandelier_stop_price: 150.45,
      chandelier_stop_pct: -5.44,
      atr_14: 4.97,
      stop_distance_atr: 1.74,
    },
    recent_candles: [
      { date: '2025-05-02', open: 151.20, high: 154.00, low: 150.10, close: 153.40, volume: 2150000 },
      { date: '2025-05-05', open: 153.60, high: 156.20, low: 152.80, close: 155.10, volume: 2040000 },
      { date: '2025-05-06', open: 155.00, high: 157.80, low: 154.20, close: 156.90, volume: 1980000 },
      { date: '2025-05-07', open: 157.10, high: 158.90, low: 155.60, close: 157.40, volume: 1890000 },
      { date: '2025-05-08', open: 157.50, high: 159.60, low: 156.80, close: 158.20, volume: 2110000 },
      { date: '2025-05-09', open: 158.30, high: 160.10, low: 157.50, close: 158.75, volume: 1760000 },
      { date: '2025-05-12', open: 158.80, high: 160.45, low: 158.10, close: 159.10, volume: 1930000 },
    ],
    strategy_rationale:
      'Day 13 of 14 — approaching vertical Time Barrier expiration tomorrow at EOD. Position holds +1.15R unrealized gain with Chandelier Stop locked above entry at $150.45.',
  },
};

const SANDBOX_CLOSED_TRADES: ClosedTradeRecord[] = [
  {
    trade_id: 'TRD-2025-041',
    ticker: 'WSM',
    company_name: 'Williams-Sonoma Inc.',
    universe: 'MID',
    entry_date: '2025-04-14',
    exit_date: '2025-04-28',
    days_held: 10,
    shares: 120,
    entry_price: 154.20,
    exit_price: 176.85,
    realized_pnl: 2718.00,
    realized_pnl_pct: 14.69,
    r_multiple: 2.94,
    exit_reason: 'TAKE_PROFIT_HIT',
    exit_reason_label: 'Take-Profit Ceiling Hit (+2.94R)',
  },
  {
    trade_id: 'TRD-2025-040',
    ticker: 'CRS',
    company_name: 'Carpenter Technology Corp.',
    universe: 'RUT',
    entry_date: '2025-04-09',
    exit_date: '2025-04-24',
    days_held: 11,
    shares: 190,
    entry_price: 102.40,
    exit_price: 115.90,
    realized_pnl: 2565.00,
    realized_pnl_pct: 13.18,
    r_multiple: 2.42,
    exit_reason: 'CHANDELIER_STOP_HIT',
    exit_reason_label: 'Trailing Chandelier Ratchet (+2.42R)',
  },
  {
    trade_id: 'TRD-2025-039',
    ticker: 'ELF',
    company_name: 'e.l.f. Beauty Inc.',
    universe: 'MID',
    entry_date: '2025-04-01',
    exit_date: '2025-04-21',
    days_held: 14,
    shares: 140,
    entry_price: 118.50,
    exit_price: 124.80,
    realized_pnl: 882.00,
    realized_pnl_pct: 5.32,
    r_multiple: 0.91,
    exit_reason: 'TIME_BARRIER_EXPIRED',
    exit_reason_label: '14-Day Time Barrier Recycle (+0.91R)',
  },
  {
    trade_id: 'TRD-2025-038',
    ticker: 'RMBS',
    company_name: 'Rambus Inc.',
    universe: 'RUT',
    entry_date: '2025-03-26',
    exit_date: '2025-04-03',
    days_held: 6,
    shares: 310,
    entry_price: 59.80,
    exit_price: 56.15,
    realized_pnl: -1131.50,
    realized_pnl_pct: -6.10,
    r_multiple: -1.00,
    exit_reason: 'CHANDELIER_STOP_HIT',
    exit_reason_label: 'Initial Chandelier Stop Floor (-1.00R)',
  },
  {
    trade_id: 'TRD-2025-037',
    ticker: 'WING',
    company_name: 'Wingstop Inc.',
    universe: 'MID',
    entry_date: '2025-03-18',
    exit_date: '2025-03-28',
    days_held: 8,
    shares: 52,
    entry_price: 342.00,
    exit_price: 368.40,
    realized_pnl: 1372.80,
    realized_pnl_pct: 7.72,
    r_multiple: 1.65,
    exit_reason: 'EARNINGS_BLACKOUT_EXIT',
    exit_reason_label: 'Pre-Earnings Blackout Shield (+1.65R)',
  },
  {
    trade_id: 'TRD-2025-036',
    ticker: 'POWL',
    company_name: 'Powell Industries Inc.',
    universe: 'RUT',
    entry_date: '2025-03-05',
    exit_date: '2025-03-17',
    days_held: 8,
    shares: 110,
    entry_price: 162.00,
    exit_price: 189.40,
    realized_pnl: 3014.00,
    realized_pnl_pct: 16.91,
    r_multiple: 3.05,
    exit_reason: 'TAKE_PROFIT_HIT',
    exit_reason_label: 'Take-Profit Ceiling Hit (+3.05R)',
  },
  {
    trade_id: 'TRD-2025-035',
    ticker: 'ONON',
    company_name: 'On Holding AG',
    universe: 'MID',
    entry_date: '2025-02-21',
    exit_date: '2025-03-11',
    days_held: 12,
    shares: 480,
    entry_price: 36.20,
    exit_price: 40.15,
    realized_pnl: 1896.00,
    realized_pnl_pct: 10.91,
    r_multiple: 2.10,
    exit_reason: 'CHANDELIER_STOP_HIT',
    exit_reason_label: 'Trailing Chandelier Ratchet (+2.10R)',
  },
  {
    trade_id: 'TRD-2025-034',
    ticker: 'CVLT',
    company_name: 'Commvault Systems Inc.',
    universe: 'RUT',
    entry_date: '2025-02-10',
    exit_date: '2025-02-28',
    days_held: 14,
    shares: 155,
    entry_price: 119.00,
    exit_price: 123.40,
    realized_pnl: 682.00,
    realized_pnl_pct: 3.70,
    r_multiple: 0.74,
    exit_reason: 'TIME_BARRIER_EXPIRED',
    exit_reason_label: '14-Day Time Barrier Recycle (+0.74R)',
  },
];

const SANDBOX_REJECTED_TICKERS: Record<string, Omit<TickerSearchResult, 'account_tier'>> = {
  DUOL: {
    query_ticker: 'DUOL',
    company_name: 'Duolingo Inc.',
    universe: 'MID',
    as_of_date: '2025-05-12',
    status: 'REJECTED',
    rejection_stage: 'STAGE_2_EARNINGS_BLACKOUT',
    headline_verdict: 'Blocked at Stage 2 — Quarterly Earnings in 3 Trading Days',
    plain_English_explanation:
      'DUOL passed institutional liquidity ($184M daily dollar volume) and exhibits top-decile momentum, but reports Q1 earnings in 3 trading days. SIRIX enforces a strict 5-day pre-earnings blackout shield to prevent binary overnight gap risk.',
    conviction_score: 89.4,
    gate_checks: [
      {
        stage: 'Stage 1 • Institutional Liquidity',
        passed: true,
        metric_label: '20D Avg Dollar Volume',
        metric_value: '$184.2M / day',
        threshold_required: '≥ $20.0M / day',
      },
      {
        stage: 'Stage 2 • Earnings Blackout Shield',
        passed: false,
        metric_label: 'Days Until Next Earnings',
        metric_value: '3 Trading Days',
        threshold_required: '> 5 Trading Days',
      },
      {
        stage: 'Stage 3 • Choppiness Index (CI₁₄)',
        passed: true,
        metric_label: '14-Day Choppiness Index',
        metric_value: '41.8 (Trending)',
        threshold_required: '< 50.0',
      },
      {
        stage: 'Stage 4 • Risk-Adjusted Momentum Rank',
        passed: true,
        metric_label: 'Universe Percentile',
        metric_value: '94.6th Percentile',
        threshold_required: '≥ 90.0th Percentile',
      },
    ],
  },
  MSTR: {
    query_ticker: 'MSTR',
    company_name: 'MicroStrategy Inc.',
    universe: 'RUT',
    as_of_date: '2025-05-12',
    status: 'REJECTED',
    rejection_stage: 'STAGE_3_CHOPPINESS_FILTER',
    headline_verdict: 'Blocked at Stage 3 — Excessive Whipsaw Volatility (CI₁₄ = 58.9)',
    plain_English_explanation:
      'While MSTR exhibits high raw price velocity, its 14-day Choppiness Index (58.9) exceeds the 50.0 smooth-trend threshold due to wide overlapping daily bars. Entering choppy regimes increases premature Chandelier Stop whipsaws.',
    conviction_score: 61.2,
    gate_checks: [
      {
        stage: 'Stage 1 • Institutional Liquidity',
        passed: true,
        metric_label: '20D Avg Dollar Volume',
        metric_value: '$1,420.0M / day',
        threshold_required: '≥ $20.0M / day',
      },
      {
        stage: 'Stage 2 • Earnings Blackout Shield',
        passed: true,
        metric_label: 'Days Until Next Earnings',
        metric_value: '54 Trading Days',
        threshold_required: '> 5 Trading Days',
      },
      {
        stage: 'Stage 3 • Choppiness Index (CI₁₄)',
        passed: false,
        metric_label: '14-Day Choppiness Index',
        metric_value: '58.9 (Whipsaw Regime)',
        threshold_required: '< 50.0',
      },
      {
        stage: 'Stage 4 • Risk-Adjusted Momentum Rank',
        passed: true,
        metric_label: 'Universe Percentile',
        metric_value: '91.2th Percentile',
        threshold_required: '≥ 90.0th Percentile',
      },
    ],
  },
  CAVA: {
    query_ticker: 'CAVA',
    company_name: 'CAVA Group Inc.',
    universe: 'MID',
    as_of_date: '2025-05-12',
    status: 'REJECTED',
    rejection_stage: 'PORTFOLIO_HEAT_CAP',
    headline_verdict: 'Blocked at Allocation — Portfolio Heat Cap Reached (5 Positions Active)',
    plain_English_explanation:
      'CAVA passed all 4 quantitative screening stages (Conviction 87.6), but the portfolio already holds 5 higher-ranked positions consuming 4.15% of the 5.00% Max Portfolio Heat envelope. CAVA is queued as #1 replacement candidate when ANF reaches its Day-14 Time Barrier.',
    conviction_score: 87.6,
    gate_checks: [
      {
        stage: 'Stage 1 • Institutional Liquidity',
        passed: true,
        metric_label: '20D Avg Dollar Volume',
        metric_value: '$215.8M / day',
        threshold_required: '≥ $20.0M / day',
      },
      {
        stage: 'Stage 2 • Earnings Blackout Shield',
        passed: true,
        metric_label: 'Days Until Next Earnings',
        metric_value: '16 Trading Days',
        threshold_required: '> 5 Trading Days',
      },
      {
        stage: 'Stage 3 • Choppiness Index (CI₁₄)',
        passed: true,
        metric_label: '14-Day Choppiness Index',
        metric_value: '43.1 (Smooth Trend)',
        threshold_required: '< 50.0',
      },
      {
        stage: 'Stage 4 • Risk-Adjusted Momentum Rank',
        passed: true,
        metric_label: 'Universe Percentile',
        metric_value: '92.0th Percentile (Rank #6)',
        threshold_required: 'Top 5 Open Slots',
      },
    ],
  },
};

/* ==========================================================================
   Local Snapshot Cache Helpers (Offline Resilience)
   ========================================================================== */

function saveSnapshotCache<T>(key: string, data: T): void {
  try {
    localStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify({ timestamp: Date.now(), data }));
  } catch {
    // Ignore quota errors
  }
}

function loadSnapshotCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(`${CACHE_PREFIX}${key}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { timestamp: number; data: T };
    return parsed.data;
  } catch {
    return null;
  }
}

/* ==========================================================================
   SIRIX Typed API Client Class
   ========================================================================== */

export class SirixApiClient {
  private accessToken: string | null = null;
  private accountTier: AccountTier = 'PRO';
  private simulateDefensiveCash = false;
  private isUsingFallback = false;

  public setSession(token: string | null, tier: AccountTier): void {
    this.accessToken = token;
    this.accountTier = tier;
  }

  public setTier(tier: AccountTier): void {
    this.accountTier = tier;
  }

  public getTier(): AccountTier {
    return this.accountTier;
  }

  public setSimulateDefensiveCash(active: boolean): void {
    this.simulateDefensiveCash = active;
  }

  public getSimulateDefensiveCash(): boolean {
    return this.simulateDefensiveCash;
  }

  public isOfflineOrSandbox(): boolean {
    return this.isUsingFallback || !API_BASE_URL;
  }

  private async requestWithAuth<T>(path: string, options: RequestInit = {}): Promise<T> {
    if (!API_BASE_URL) {
      throw new Error('SANDBOX_FALLBACK');
    }

    const headers = new Headers(options.headers || {});
    headers.set('Content-Type', 'application/json');
    if (this.accessToken) {
      headers.set('Authorization', `Bearer ${this.accessToken}`);
    }

    let response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      credentials: 'include',
    });

    // Silent token refresh on 401
    if (response.status === 401 && path !== '/api/v1/auth/login' && path !== '/api/v1/auth/refresh') {
      const refreshRes = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (refreshRes.ok) {
        const tokenData = (await refreshRes.json()) as AuthTokenResponse;
        this.accessToken = tokenData.access_token;
        this.accountTier = tokenData.account_tier;
        headers.set('Authorization', `Bearer ${this.accessToken}`);
        response = await fetch(`${API_BASE_URL}${path}`, {
          ...options,
          headers,
          credentials: 'include',
        });
      }
    }

    if (!response.ok) {
      throw new Error(`HTTP_${response.status}`);
    }

    this.isUsingFallback = false;
    return (await response.json()) as T;
  }

  /* ------------------------------------------------------------------------
     1. Authentication (/api/v1/auth/login)
     ------------------------------------------------------------------------ */
  public async login(email: string, password: string, preferredTier: AccountTier = 'PRO'): Promise<AuthTokenResponse> {
    try {
      const data = await this.requestWithAuth<AuthTokenResponse>('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      this.accessToken = data.access_token;
      this.accountTier = data.account_tier;
      return data;
    } catch {
      this.isUsingFallback = true;
      const resolvedTier: AccountTier = email.toLowerCase().includes('free')
        ? 'FREE'
        : email.toLowerCase().includes('expert')
        ? 'EXPERT'
        : preferredTier;
      const sandboxAuth: AuthTokenResponse = {
        access_token: `sirix_sandbox_jwt_${Date.now()}`,
        token_type: 'bearer',
        expires_in_seconds: 900,
        user_id: 'usr_sirix_institutional_01',
        account_tier: resolvedTier,
      };
      this.accessToken = sandboxAuth.access_token;
      this.accountTier = resolvedTier;
      return sandboxAuth;
    }
  }

  /* ------------------------------------------------------------------------
     2. Portfolio Overview (GET /api/v1/portfolio/overview)
     ------------------------------------------------------------------------ */
  public async getPortfolioOverview(killSwitchActive = false): Promise<PortfolioOverviewResponse> {
    const cacheKey = `overview_${this.accountTier}_${this.simulateDefensiveCash}_${killSwitchActive}`;
    try {
      const live = await this.requestWithAuth<PortfolioOverviewResponse>('/api/v1/portfolio/overview');
      saveSnapshotCache(cacheKey, live);
      return live;
    } catch {
      this.isUsingFallback = true;
      const tier = this.accountTier;

      if (this.simulateDefensiveCash || killSwitchActive) {
        const defensivePayload: PortfolioOverviewResponse = {
          as_of_timestamp: '2025-05-12T21:30:00Z',
          account_tier: tier,
          system_state: killSwitchActive ? 'HALTED_KILL_SWITCH' : 'DEFENSIVE_CASH',
          total_equity: 108450.25,
          cash_balance: 108450.25,
          invested_capital: 0,
          daily_change_usd: 0,
          daily_change_pct: 0,
          inception_return_usd: 8450.25,
          inception_return_pct: 8.45,
          portfolio_heat_pct: 0.0,
          max_portfolio_heat_pct: 5.0,
          active_positions_count: 0,
          visible_positions_count: 0,
          is_truncated_for_tier: false,
          defensive_mode_context: {
            is_active: true,
            reason_code: killSwitchActive ? 'KILL_SWITCH_ACTIVE' : 'UNIVERSE_CHOPPINESS_HIGH',
            title: killSwitchActive
              ? 'Emergency Kill-Switch Engaged — 100% Capital in Cash'
              : 'Autonomous Capital Preservation Active — High Market Choppiness',
            explanation: killSwitchActive
              ? 'All autonomous entries are halted and 100% of portfolio equity is held in cash per your Emergency Kill-Switch directive.'
              : 'SIRIX evaluated all 2,400 constituents across Russell 2000 (RUT) and S&P MidCap 400 (MID) at EOD. Median universe Choppiness Index (CI₁₄ = 56.4) exceeded the 50.0 regime threshold, so the engine preserved 100% of capital in cash rather than forcing low-probability trades.',
            candidates_evaluated: 2400,
            capital_preserved_pct: 100.0,
          },
          holdings: [],
        };
        saveSnapshotCache(cacheKey, defensivePayload);
        return defensivePayload;
      }

      const isFree = tier === 'FREE';
      const visibleHoldings = (isFree ? SANDBOX_HOLDINGS_FULL.slice(0, 2) : SANDBOX_HOLDINGS_FULL).map((h) => ({
        ...h,
        conviction_score: isFree ? null : h.conviction_score,
        stop_distance_atr: isFree ? null : h.stop_distance_atr,
      }));

      const overview: PortfolioOverviewResponse = {
        as_of_timestamp: '2025-05-12T21:30:00Z',
        account_tier: tier,
        system_state: 'NORMAL',
        total_equity: 108450.25,
        cash_balance: 10764.00,
        invested_capital: 97686.25,
        daily_change_usd: 1412.80,
        daily_change_pct: 1.32,
        inception_return_usd: 8450.25,
        inception_return_pct: 8.45,
        portfolio_heat_pct: 4.15,
        max_portfolio_heat_pct: 5.0,
        active_positions_count: SANDBOX_HOLDINGS_FULL.length,
        visible_positions_count: visibleHoldings.length,
        is_truncated_for_tier: isFree,
        defensive_mode_context: null,
        holdings: visibleHoldings,
      };

      saveSnapshotCache(cacheKey, overview);
      return overview;
    }
  }

  /* ------------------------------------------------------------------------
     3. Position Deep-Dive Inspector (GET /api/v1/portfolio/positions/{ticker})
     ------------------------------------------------------------------------ */
  public async getPositionDeepDive(ticker: string): Promise<PositionDeepDiveResponse> {
    const cleanTicker = ticker.trim().toUpperCase();
    const cacheKey = `deep_dive_${cleanTicker}_${this.accountTier}`;
    try {
      const live = await this.requestWithAuth<PositionDeepDiveResponse>(
        `/api/v1/portfolio/positions/${encodeURIComponent(cleanTicker)}`
      );
      saveSnapshotCache(cacheKey, live);
      return live;
    } catch {
      this.isUsingFallback = true;
      const base = SANDBOX_DEEP_DIVES[cleanTicker] || SANDBOX_DEEP_DIVES.CELH;
      const isFree = this.accountTier === 'FREE';

      const response: PositionDeepDiveResponse = {
        ...base,
        account_tier: this.accountTier,
        is_tier_restricted: isFree,
        r_multiple_current: isFree ? null : base.r_multiple_current,
        conviction_score: isFree ? null : base.conviction_score,
        momentum_rank_pct: isFree ? null : base.momentum_rank_pct,
        triple_barrier: isFree
          ? {
              take_profit_price: null,
              take_profit_pct: null,
              entry_price: base.triple_barrier.entry_price,
              current_price: base.triple_barrier.current_price,
              chandelier_stop_price: null,
              chandelier_stop_pct: null,
              atr_14: null,
              stop_distance_atr: null,
            }
          : base.triple_barrier,
      };

      saveSnapshotCache(cacheKey, response);
      return response;
    }
  }

  /* ------------------------------------------------------------------------
     4. Algorithmic Universe Search (GET /api/v1/universe/search?q={ticker})
     ------------------------------------------------------------------------ */
  public async searchUniverseTicker(query: string): Promise<TickerSearchResult> {
    const clean = query.trim().toUpperCase() || 'DUOL';
    try {
      return await this.requestWithAuth<TickerSearchResult>(
        `/api/v1/universe/search?q=${encodeURIComponent(clean)}`
      );
    } catch {
      this.isUsingFallback = true;
      const tier = this.accountTier;
      const isFree = tier === 'FREE';

      // Check if held in portfolio
      const heldMatch = SANDBOX_HOLDINGS_FULL.find((h) => h.ticker === clean);
      if (heldMatch) {
        return {
          query_ticker: heldMatch.ticker,
          company_name: heldMatch.company_name,
          universe: heldMatch.universe,
          as_of_date: '2025-05-12',
          account_tier: tier,
          status: 'HELD',
          rejection_stage: null,
          headline_verdict: `Active Holding — Passed All 4 Quantitative Screening Gates`,
          plain_English_explanation: `${heldMatch.ticker} (${heldMatch.company_name}) is currently held in your active autonomous portfolio (Day ${heldMatch.days_held} of ${heldMatch.max_hold_days}) with ${heldMatch.unrealized_pnl_pct >= 0 ? '+' : ''}${heldMatch.unrealized_pnl_pct.toFixed(2)}% unrealized return.`,
          conviction_score: isFree ? null : heldMatch.conviction_score,
          gate_checks: isFree
            ? []
            : [
                {
                  stage: 'Stage 1 • Institutional Liquidity',
                  passed: true,
                  metric_label: '20D Avg Dollar Volume',
                  metric_value: '$142.5M / day',
                  threshold_required: '≥ $20.0M / day',
                },
                {
                  stage: 'Stage 2 • Earnings Blackout Shield',
                  passed: true,
                  metric_label: 'Days Until Next Earnings',
                  metric_value: '> 12 Trading Days',
                  threshold_required: '> 5 Trading Days',
                },
                {
                  stage: 'Stage 3 • Choppiness Index (CI₁₄)',
                  passed: true,
                  metric_label: '14-Day Choppiness Index',
                  metric_value: '39.4 (Trending)',
                  threshold_required: '< 50.0',
                },
                {
                  stage: 'Stage 4 • Risk-Adjusted Momentum Rank',
                  passed: true,
                  metric_label: 'Universe Percentile',
                  metric_value: 'Top 2% Breakout Rank',
                  threshold_required: '≥ 90.0th Percentile',
                },
              ],
        };
      }

      // Check predefined rejected tickers
      const predefined = SANDBOX_REJECTED_TICKERS[clean];
      if (predefined) {
        return {
          ...predefined,
          account_tier: tier,
          conviction_score: isFree ? null : predefined.conviction_score,
          gate_checks: isFree ? [] : predefined.gate_checks,
        };
      }

      // Deterministic synthesized rejection for any other ticker symbol
      const charCodeSum = clean.split('').reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
      const isStage1 = charCodeSum % 2 === 0;
      const universe = charCodeSum % 3 === 0 ? 'MID' : 'RUT';

      const synthesized: TickerSearchResult = {
        query_ticker: clean,
        company_name: `${clean} Corp. (${universe} Constituent)`,
        universe,
        as_of_date: '2025-05-12',
        account_tier: tier,
        status: 'REJECTED',
        rejection_stage: isStage1 ? 'STAGE_1_LIQUIDITY' : 'STAGE_4_MOMENTUM_RANK',
        headline_verdict: isStage1
          ? `Blocked at Stage 1 — Insufficient Institutional Dollar Volume ($8.4M / day)`
          : `Blocked at Stage 4 — Momentum Rank Below Top-Decile Cutoff (68.4th Percentile)`,
        plain_English_explanation: isStage1
          ? `${clean} traded an average of $8.4M daily dollar volume over the past 20 sessions, below SIRIX's $20.0M institutional liquidity floor required to prevent slippage.`
          : `${clean} passed liquidity, earnings blackout, and trend smoothness checks, but its 60-day risk-adjusted momentum ranked in the 68.4th percentile—below the 90.0th percentile threshold required to displace current holdings.`,
        conviction_score: isFree ? null : isStage1 ? 42.5 : 71.8,
        gate_checks: isFree
          ? []
          : [
              {
                stage: 'Stage 1 • Institutional Liquidity',
                passed: !isStage1,
                metric_label: '20D Avg Dollar Volume',
                metric_value: isStage1 ? '$8.4M / day' : '$64.2M / day',
                threshold_required: '≥ $20.0M / day',
              },
              {
                stage: 'Stage 2 • Earnings Blackout Shield',
                passed: true,
                metric_label: 'Days Until Next Earnings',
                metric_value: '29 Trading Days',
                threshold_required: '> 5 Trading Days',
              },
              {
                stage: 'Stage 3 • Choppiness Index (CI₁₄)',
                passed: true,
                metric_label: '14-Day Choppiness Index',
                metric_value: '46.2 (Trending)',
                threshold_required: '< 50.0',
              },
              {
                stage: 'Stage 4 • Risk-Adjusted Momentum Rank',
                passed: false,
                metric_label: 'Universe Percentile',
                metric_value: '68.4th Percentile',
                threshold_required: '≥ 90.0th Percentile',
              },
            ],
      };

      return synthesized;
    }
  }

  /* ------------------------------------------------------------------------
     5. Closed Trades Audit Log (GET /api/v1/audit/closed-trades)
     ------------------------------------------------------------------------ */
  public async getAuditLog(): Promise<AuditLogResponse> {
    const cacheKey = `audit_${this.accountTier}`;
    try {
      const live = await this.requestWithAuth<AuditLogResponse>('/api/v1/audit/closed-trades');
      saveSnapshotCache(cacheKey, live);
      return live;
    } catch {
      this.isUsingFallback = true;
      const tier = this.accountTier;
      const isFree = tier === 'FREE';
      const visibleTrades = isFree ? SANDBOX_CLOSED_TRADES.slice(0, 5) : SANDBOX_CLOSED_TRADES;

      const audit: AuditLogResponse = {
        account_tier: tier,
        total_closed_trades: SANDBOX_CLOSED_TRADES.length,
        win_rate_pct: 87.5,
        avg_r_multiple: 1.60,
        cumulative_realized_pnl: 11998.30,
        is_truncated_for_tier: isFree,
        csv_export_allowed: tier === 'EXPERT',
        trades: visibleTrades,
      };
      saveSnapshotCache(cacheKey, audit);
      return audit;
    }
  }

  /* ------------------------------------------------------------------------
     6. User Preferences & Guardrails (GET / PATCH /api/v1/preferences)
     ------------------------------------------------------------------------ */
  public async getPreferences(): Promise<UserPreferencesResponse> {
    const cached = loadSnapshotCache<UserPreferencesResponse>('user_prefs');
    try {
      const live = await this.requestWithAuth<UserPreferencesResponse>('/api/v1/preferences');
      saveSnapshotCache('user_prefs', live);
      return live;
    } catch {
      this.isUsingFallback = true;
      const fallback: UserPreferencesResponse = cached || {
        user_id: 'usr_sirix_institutional_01',
        account_tier: this.accountTier,
        language: 'en',
        theme: 'obsidian-dark',
        notifications_enabled: true,
        guardrails_editable: this.accountTier === 'EXPERT',
        guardrails: {
          max_portfolio_heat_pct: 5.0,
          risk_per_trade_pct: 1.0,
          time_barrier_days: 14,
          earnings_blackout_days: 5,
          active_universes: ['RUT', 'MID'],
          zero_override_enforced: true,
          kill_switch_active: false,
        },
      };
      fallback.account_tier = this.accountTier;
      fallback.guardrails_editable = this.accountTier === 'EXPERT';
      return fallback;
    }
  }

  public async updatePreferences(
    current: UserPreferencesResponse,
    patch: UserPreferencesUpdateRequest
  ): Promise<UserPreferencesResponse> {
    try {
      const live = await this.requestWithAuth<UserPreferencesResponse>('/api/v1/preferences', {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      saveSnapshotCache('user_prefs', live);
      return live;
    } catch {
      this.isUsingFallback = true;
      const updated: UserPreferencesResponse = {
        ...current,
        account_tier: this.accountTier,
        language: patch.language ?? current.language,
        theme: patch.theme ?? current.theme,
        notifications_enabled: patch.notifications_enabled ?? current.notifications_enabled,
        guardrails_editable: this.accountTier === 'EXPERT',
        guardrails: {
          ...current.guardrails,
          ...(this.accountTier === 'EXPERT' && patch.guardrails ? patch.guardrails : {}),
          zero_override_enforced: true,
        },
      };
      saveSnapshotCache('user_prefs', updated);
      return updated;
    }
  }
}

export const sirixClient = new SirixApiClient();

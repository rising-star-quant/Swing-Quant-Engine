/**
 * SIRIX Data Contracts, Auth, and Edge States TypeScript Definitions
 * Strictly mirrors docs/ui-spec/F01_data_contracts_auth_edge_states_spec.md and api/main.py
 */

export type AccountTier = 'FREE' | 'PRO' | 'EXPERT';
export type SupportedLanguage = 'en' | 'he' | 'ar' | 'ru';
export type SupportedTheme = 'obsidian-dark' | 'sirius-ice-light' | 'midnight-sapphire';
export type UniverseCode = 'RUT' | 'MID';
export type SystemState = 'NORMAL' | 'DEFENSIVE_CASH' | 'HALTED_KILL_SWITCH';
export type TimeBarrierUrgency = 'FRESH' | 'MATURING' | 'CRITICAL';

export type ExitReasonCode =
  | 'TAKE_PROFIT_HIT'
  | 'CHANDELIER_STOP_HIT'
  | 'TIME_BARRIER_EXPIRED'
  | 'EARNINGS_BLACKOUT_EXIT'
  | 'KILL_SWITCH_LIQUIDATION';

export type RejectionStageCode =
  | 'STAGE_1_LIQUIDITY'
  | 'STAGE_2_EARNINGS_BLACKOUT'
  | 'STAGE_3_CHOPPINESS_FILTER'
  | 'STAGE_4_MOMENTUM_RANK'
  | 'PORTFOLIO_HEAT_CAP';

/* ==========================================================================
   1. Authentication Contracts (/api/v1/auth/*)
   ========================================================================== */

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user_id: string;
  account_tier: AccountTier;
}

/* ==========================================================================
   2. Portfolio Overview Contract (GET /api/v1/portfolio/overview)
   ========================================================================== */

export interface DefensiveModeContext {
  is_active: boolean;
  reason_code: 'REGIME_VOLATILITY_SPIKE' | 'UNIVERSE_CHOPPINESS_HIGH' | 'KILL_SWITCH_ACTIVE';
  title: string;
  explanation: string;
  candidates_evaluated: number;
  capital_preserved_pct: number;
}

export interface HoldingSummaryCard {
  ticker: string;
  company_name: string;
  universe: UniverseCode;
  shares: number;
  entry_price: number;
  current_price: number;
  position_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  weight_pct: number;
  days_held: number;
  max_hold_days: number;
  time_barrier_urgency: TimeBarrierUrgency;
  conviction_score: number | null; // Masked (null) for FREE tier
  stop_distance_atr: number | null; // Masked (null) for FREE tier
}

export interface PortfolioOverviewResponse {
  as_of_timestamp: string;
  account_tier: AccountTier;
  system_state: SystemState;
  total_equity: number;
  cash_balance: number;
  invested_capital: number;
  daily_change_usd: number;
  daily_change_pct: number;
  inception_return_usd: number;
  inception_return_pct: number;
  portfolio_heat_pct: number;
  max_portfolio_heat_pct: number;
  active_positions_count: number;
  visible_positions_count: number;
  is_truncated_for_tier: boolean;
  defensive_mode_context: DefensiveModeContext | null;
  holdings: HoldingSummaryCard[];
}

/* ==========================================================================
   3. Position Deep-Dive Inspector (GET /api/v1/portfolio/positions/{ticker})
   ========================================================================== */

export interface DailyCandleBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface TripleBarrierLevels {
  take_profit_price: number | null;
  take_profit_pct: number | null;
  entry_price: number;
  current_price: number;
  chandelier_stop_price: number | null;
  chandelier_stop_pct: number | null;
  atr_14: number | null;
  stop_distance_atr: number | null;
}

export interface PositionDeepDiveResponse {
  ticker: string;
  company_name: string;
  universe: UniverseCode;
  sector: string;
  account_tier: AccountTier;
  is_tier_restricted: boolean;
  entry_date: string;
  days_held: number;
  max_hold_days: number;
  days_remaining: number;
  time_barrier_urgency: TimeBarrierUrgency;
  shares: number;
  position_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  r_multiple_current: number | null;
  conviction_score: number | null;
  momentum_rank_pct: number | null;
  next_earnings_date: string | null;
  days_until_earnings: number | null;
  earnings_blackout_SAFE: boolean;
  triple_barrier: TripleBarrierLevels;
  recent_candles: DailyCandleBar[];
  strategy_rationale: string;
}

/* ==========================================================================
   4. Algorithmic Universe Search (GET /api/v1/universe/search)
   ========================================================================== */

export interface GateCheckResult {
  stage: string;
  passed: boolean;
  metric_label: string;
  metric_value: string;
  threshold_required: string;
}

export interface TickerSearchResult {
  query_ticker: string;
  company_name: string;
  universe: UniverseCode;
  as_of_date: string;
  account_tier: AccountTier;
  status: 'HELD' | 'REJECTED';
  rejection_stage: RejectionStageCode | null;
  headline_verdict: string;
  plain_English_explanation: string;
  conviction_score: number | null;
  gate_checks: GateCheckResult[];
}

/* ==========================================================================
   5. Audit Log (GET /api/v1/audit/closed-trades)
   ========================================================================== */

export interface ClosedTradeRecord {
  trade_id: string;
  ticker: string;
  company_name: string;
  universe: UniverseCode;
  entry_date: string;
  exit_date: string;
  days_held: number;
  shares: number;
  entry_price: number;
  exit_price: number;
  realized_pnl: number;
  realized_pnl_pct: number;
  r_multiple: number;
  exit_reason: ExitReasonCode;
  exit_reason_label: string;
}

export interface AuditLogResponse {
  account_tier: AccountTier;
  total_closed_trades: number;
  win_rate_pct: number;
  avg_r_multiple: number;
  cumulative_realized_pnl: number;
  is_truncated_for_tier: boolean;
  csv_export_allowed: boolean;
  trades: ClosedTradeRecord[];
}

/* ==========================================================================
   6. User Preferences & Risk Guardrails (GET / PATCH /api/v1/preferences)
   ========================================================================== */

export interface RiskGuardrailConfig {
  max_portfolio_heat_pct: number;
  risk_per_trade_pct: number;
  time_barrier_days: number;
  earnings_blackout_days: number;
  active_universes: UniverseCode[];
  zero_override_enforced: true;
  kill_switch_active: boolean;
}

export interface UserPreferencesResponse {
  user_id: string;
  account_tier: AccountTier;
  language: SupportedLanguage;
  theme: SupportedTheme;
  notifications_enabled: boolean;
  guardrails_editable: boolean;
  guardrails: RiskGuardrailConfig;
}

export interface UserPreferencesUpdateRequest {
  language?: SupportedLanguage;
  theme?: SupportedTheme;
  notifications_enabled?: boolean;
  guardrails?: Partial<RiskGuardrailConfig>;
}

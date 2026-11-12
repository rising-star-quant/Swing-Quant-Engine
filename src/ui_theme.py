from __future__ import annotations

from typing import List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from src.dashboard_service import (
        PortfolioDashboardSnapshotVM,
        StockConvictionCardVM,
    )
    from src.schemas import ClosedTradeAuditSchema, ExitReason
except ImportError:
    from dashboard_service import (  # type: ignore[no-redef]
        PortfolioDashboardSnapshotVM,
        StockConvictionCardVM,
    )
    from schemas import ClosedTradeAuditSchema, ExitReason  # type: ignore[no-redef]


# =============================================================================
# 1. COLOR PALETTE & SEMANTIC DESIGN TOKENS
# =============================================================================

BG_PRIMARY: str = "#0B0F19"
BG_SURFACE: str = "#111827"
BG_SIDEBAR: str = "#070A12"
BORDER_SUBTLE: str = "#1F2937"
TEXT_PRIMARY: str = "#F9FAFB"
TEXT_MUTED: str = "#9CA3AF"
ACCENT_CYAN: str = "#06B6D4"
SEMANTIC_EMERALD: str = "#10B981"
SEMANTIC_AMBER: str = "#F59E0B"
SEMANTIC_CRIMSON: str = "#EF4444"
SEMANTIC_VIOLET: str = "#8B5CF6"

_SLICE_PALETTE: Tuple[str, ...] = (
    "#3B82F6",
    "#6366F1",
    "#8B5CF6",
    "#0EA5E9",
    "#14B8A6",
    "#F59E0B",
    "#EC4899",
    "#22C55E",
    "#A855F7",
    "#06B6D4",
)


# =============================================================================
# 2. INSTITUTIONAL DARK-MODE CSS INJECTION
# =============================================================================


def inject_institutional_css() -> None:
    """
    Injects institutional dark-mode CSS tokens, glassmorphic card surfaces,
    tabular-nums monospace numeral formatting, and semantic status pills.
    """
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');

        .stApp {{
            background-color: {BG_PRIMARY};
            color: {TEXT_PRIMARY};
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        section[data-testid="stSidebar"] {{
            background-color: {BG_SIDEBAR} !important;
            border-right: 1px solid {BORDER_SUBTLE};
        }}

        .block-container {{
            padding-top: 1.4rem !important;
            padding-bottom: 2.5rem !important;
            max-width: 1440px;
        }}

        .sqe-card {{
            background: {BG_SURFACE};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 10px;
            padding: 16px 20px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
            margin-bottom: 14px;
        }}

        .sqe-kpi-card {{
            background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(11, 15, 25, 0.98) 100%);
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 10px;
            padding: 14px 18px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
            height: 100%;
        }}

        .sqe-kpi-label {{
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: {TEXT_MUTED};
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .sqe-kpi-value {{
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-variant-numeric: tabular-nums;
            font-size: 1.45rem;
            font-weight: 700;
            color: {TEXT_PRIMARY};
            line-height: 1.2;
            margin-bottom: 6px;
        }}

        .sqe-kpi-sub {{
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-variant-numeric: tabular-nums;
            font-size: 0.76rem;
            color: {TEXT_MUTED};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .sqe-mono {{
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-variant-numeric: tabular-nums;
        }}

        .sqe-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 5px;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 0.68rem;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }}

        .sqe-badge-safe {{
            background: rgba(16, 185, 129, 0.16);
            color: {SEMANTIC_EMERALD};
            border: 1px solid rgba(16, 185, 129, 0.4);
        }}

        .sqe-badge-moderate {{
            background: rgba(245, 158, 11, 0.16);
            color: {SEMANTIC_AMBER};
            border: 1px solid rgba(245, 158, 11, 0.4);
        }}

        .sqe-badge-crimson {{
            background: rgba(239, 68, 68, 0.18);
            color: {SEMANTIC_CRIMSON};
            border: 1px solid rgba(239, 68, 68, 0.45);
        }}

        .sqe-badge-cyan {{
            background: rgba(6, 182, 212, 0.16);
            color: {ACCENT_CYAN};
            border: 1px solid rgba(6, 182, 212, 0.4);
        }}

        .sqe-badge-violet {{
            background: rgba(139, 92, 246, 0.18);
            color: {SEMANTIC_VIOLET};
            border: 1px solid rgba(139, 92, 246, 0.45);
        }}

        .sqe-grid-4 {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-top: 12px;
            margin-bottom: 12px;
        }}

        .sqe-metric-box {{
            background: rgba(11, 15, 25, 0.72);
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 10px 12px;
        }}

        .sqe-progress-track {{
            width: 100%;
            height: 6px;
            background: rgba(31, 41, 55, 0.9);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 6px;
        }}

        .sqe-progress-fill {{
            height: 100%;
            border-radius: 4px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# 3. GLOBAL TOP KPI STRIP RENDERER
# =============================================================================


def render_top_kpi_strip(snapshot: PortfolioDashboardSnapshotVM) -> None:
    """
    Renders the 4-column persistent Global Telemetry Header answering the
    subscriber's 3-second capital clarity questions.
    """
    ledger = snapshot.ledger
    total_equity = ledger.total_equity
    cash_balance = ledger.cash_balance
    cash_pct = snapshot.cash_allocation_pct
    deployed_dollars = snapshot.deployed_capital_dollars

    slots_used = len(ledger.open_positions)
    max_slots = ledger.max_concurrent_positions

    current_heat_pct = ledger.current_portfolio_heat_pct * 100.0
    max_heat_pct = ledger.max_portfolio_heat_pct * 100.0

    if current_heat_pct < 3.5:
        heat_badge_cls = "sqe-badge-safe"
        heat_badge_txt = "SAFE"
        heat_val_color = SEMANTIC_EMERALD
    elif current_heat_pct <= 5.0:
        heat_badge_cls = "sqe-badge-moderate"
        heat_badge_txt = "MODERATE"
        heat_val_color = SEMANTIC_AMBER
    else:
        heat_badge_cls = "sqe-badge-crimson"
        heat_badge_txt = "HIGH HEAT"
        heat_val_color = SEMANTIC_CRIMSON

    mode_badge_cls = "sqe-badge-violet" if snapshot.is_demo_mode else "sqe-badge-safe"
    mode_badge_txt = "SANDBOX DEMO" if snapshot.is_demo_mode else "LIVE PRODUCTION"

    realized_pnl = snapshot.performance_summary.get("total_realized_pnl", 0.0)
    pnl_sign = "+" if realized_pnl >= 0.0 else ""
    pnl_color = SEMANTIC_EMERALD if realized_pnl >= 0.0 else SEMANTIC_CRIMSON

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
            <div class="sqe-kpi-card">
                <div class="sqe-kpi-label">
                    <span>TOTAL PORTFOLIO EQUITY</span>
                    <span class="sqe-badge {mode_badge_cls}">{mode_badge_txt}</span>
                </div>
                <div class="sqe-kpi-value">${total_equity:,.2f}</div>
                <div class="sqe-kpi-sub">
                    <span>Realized Audit P&amp;L:</span>
                    <span style="color: {pnl_color}; font-weight: 600;">{pnl_sign}${realized_pnl:,.2f}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="sqe-kpi-card">
                <div class="sqe-kpi-label">
                    <span>AVAILABLE DRY POWDER</span>
                    <span class="sqe-badge sqe-badge-cyan">{cash_pct:.1f}% LIQUID</span>
                </div>
                <div class="sqe-kpi-value" style="color: {SEMANTIC_EMERALD};">${cash_balance:,.2f}</div>
                <div class="sqe-kpi-sub">
                    <span>Unallocated Cash Ready for Setups</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        slot_pct = min(100.0, (slots_used / max(1, max_slots)) * 100.0)
        st.markdown(
            f"""
            <div class="sqe-kpi-card">
                <div class="sqe-kpi-label">
                    <span>ACTIVE SLOT CAPACITY</span>
                    <span class="sqe-badge sqe-badge-cyan">{slot_pct:.0f}% USED</span>
                </div>
                <div class="sqe-kpi-value">{slots_used} / {max_slots} <span style="font-size: 0.95rem; font-weight: 500; color: {TEXT_MUTED};">Positions</span></div>
                <div class="sqe-kpi-sub">
                    <span>Deployed Capital:</span>
                    <span style="color: {TEXT_PRIMARY}; font-weight: 600;">${deployed_dollars:,.2f}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="sqe-kpi-card">
                <div class="sqe-kpi-label">
                    <span>PORTFOLIO HEAT STATUS</span>
                    <span class="sqe-badge {heat_badge_cls}">{heat_badge_txt}</span>
                </div>
                <div class="sqe-kpi-value" style="color: {heat_val_color};">{current_heat_pct:.2f}% <span style="font-size: 0.95rem; color: {TEXT_MUTED};">/ {max_heat_pct:.2f}% Max</span></div>
                <div class="sqe-kpi-sub">
                    <span>Remaining Risk Budget:</span>
                    <span style="color: {TEXT_PRIMARY}; font-weight: 600;">${snapshot.remaining_dollar_risk_budget:,.2f}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =============================================================================
# 4. CORE DASHBOARD 1: PORTFOLIO HEAT RISK GAUGE
# =============================================================================


def build_portfolio_heat_gauge(
    current_heat_pct: float,
    max_heat_pct: float,
    open_dollar_risk: float,
) -> go.Figure:
    """
    Builds the semicircular Plotly risk dial visualizing current Portfolio Heat
    against Jim Simons' hard ceiling (`6.00%` default).
    Accepts either fractional (e.g., `0.0365`) or percentage (`3.65`) inputs.
    """
    norm_max = max_heat_pct * 100.0 if 0.0 < max_heat_pct <= 0.25 else max(2.0, max_heat_pct)
    norm_curr = (
        current_heat_pct * 100.0
        if 0.0 < current_heat_pct <= 0.25 and norm_max >= 1.0
        else max(0.0, current_heat_pct)
    )

    if norm_curr < 3.5:
        bar_color = SEMANTIC_EMERALD
    elif norm_curr <= 5.0:
        bar_color = SEMANTIC_AMBER
    else:
        bar_color = SEMANTIC_CRIMSON

    axis_upper = max(6.0, norm_max)
    safe_cap = min(3.5, axis_upper)
    amber_cap = min(5.0, axis_upper)

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=round(norm_curr, 2),
            number={
                "suffix": "%",
                "valueformat": ".2f",
                "font": {
                    "family": "JetBrains Mono, monospace",
                    "size": 34,
                    "color": bar_color,
                },
            },
            title={
                "text": (
                    f"<span style='font-size:13px;color:{TEXT_PRIMARY};font-weight:600;'>"
                    "PORTFOLIO HEAT (SIMONS HARD RISK CAP)</span><br>"
                    f"<span style='font-size:11px;color:{TEXT_MUTED};font-family:JetBrains Mono,monospace;'>"
                    f"Total Open Stop Risk: ${open_dollar_risk:,.2f} | Hard Ceiling: {norm_max:.2f}%</span>"
                ),
                "font": {"size": 13, "color": TEXT_PRIMARY},
            },
            gauge={
                "axis": {
                    "range": [0.0, axis_upper],
                    "ticksuffix": "%",
                    "tickwidth": 1,
                    "tickcolor": BORDER_SUBTLE,
                    "tickfont": {
                        "family": "JetBrains Mono, monospace",
                        "size": 11,
                        "color": TEXT_MUTED,
                    },
                },
                "bar": {"color": bar_color, "thickness": 0.34},
                "bgcolor": BG_PRIMARY,
                "borderwidth": 1,
                "bordercolor": BORDER_SUBTLE,
                "steps": [
                    {"range": [0.0, safe_cap], "color": "rgba(16, 185, 129, 0.22)"},
                    {"range": [safe_cap, amber_cap], "color": "rgba(245, 158, 11, 0.25)"},
                    {"range": [amber_cap, axis_upper], "color": "rgba(239, 68, 68, 0.30)"},
                ],
                "threshold": {
                    "line": {"color": SEMANTIC_CRIMSON, "width": 4},
                    "thickness": 0.85,
                    "value": norm_max,
                },
            },
        )
    )

    fig.update_layout(
        height=260,
        margin=dict(l=24, r=24, t=54, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, sans-serif", "color": TEXT_PRIMARY},
    )
    return fig


# =============================================================================
# 5. CORE DASHBOARD 2: DRY POWDER & CAPITAL ALLOCATION DONUT
# =============================================================================


def build_capital_allocation_chart(
    cash_balance: float,
    total_equity: float,
    cards: List[StockConvictionCardVM],
    max_slots: int = 10,
) -> go.Figure:
    """
    Builds the interactive `go.Pie(hole=0.68)` ring chart showing
    `"Available Cash (Dry Powder)"` vs. each active ticker's deployed capital.
    """
    safe_equity = max(1.0, total_equity)
    safe_cash = max(0.0, cash_balance)
    cash_pct = (safe_cash / safe_equity) * 100.0

    labels: List[str] = ["Available Cash (Dry Powder)"]
    values: List[float] = [round(safe_cash, 2)]
    cash_color = SEMANTIC_EMERALD if cash_pct >= 20.0 else ACCENT_CYAN
    colors: List[str] = [cash_color]

    for idx, card in enumerate(cards):
        market_val = round(card.shares * card.current_price, 2)
        if market_val > 0.0:
            labels.append(f"{card.ticker} ({card.index_id})")
            values.append(market_val)
            colors.append(_SLICE_PALETTE[idx % len(_SLICE_PALETTE)])

    slots_used = len(cards)
    safe_max_slots = max(1, max_slots)

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.68,
                marker=dict(
                    colors=colors,
                    line=dict(color=BG_PRIMARY, width=2),
                ),
                textinfo="label+percent",
                textposition="outside",
                textfont=dict(
                    family="JetBrains Mono, monospace",
                    size=11,
                    color=TEXT_PRIMARY,
                ),
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Allocation: $%{value:,.2f}<br>"
                    "Share of Equity: %{percent}<extra></extra>"
                ),
                sort=False,
            )
        ]
    )

    fig.update_layout(
        title=dict(
            text=(
                f"<span style='font-size:13px;color:{TEXT_PRIMARY};font-weight:600;'>"
                "AVAILABLE DRY POWDER &amp; CAPITAL DEPLOYMENT</span>"
            ),
            x=0.5,
            xanchor="center",
            y=0.96,
        ),
        annotations=[
            dict(
                text=(
                    f"<span style='font-size:10px;color:{TEXT_MUTED};letter-spacing:1px;'>FREE CASH</span><br>"
                    f"<span style='font-size:19px;font-weight:700;color:{TEXT_PRIMARY};"
                    f"font-family:JetBrains Mono,monospace;'>${safe_cash:,.0f}</span><br>"
                    f"<span style='font-size:10px;color:{SEMANTIC_EMERALD};"
                    f"font-family:JetBrains Mono,monospace;'>{cash_pct:.1f}% Liquid | {slots_used}/{safe_max_slots} Slots</span>"
                ),
                x=0.5,
                y=0.47,
                font=dict(size=12, color=TEXT_PRIMARY),
                showarrow=False,
            )
        ],
        height=260,
        margin=dict(l=20, r=20, t=44, b=16),
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02,
            font=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_MUTED),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# =============================================================================
# 6. CORE DASHBOARD 3: PER-STOCK PROBABILITY & CONVICTION CARD
# =============================================================================


def render_stock_conviction_card(
    card: StockConvictionCardVM,
    show_copy_ticket: bool = True,
) -> None:
    """
    Renders a high-contrast institutional card displaying the stock's 500-day
    Meta-Labeling statistical edge, Triple-Barrier order execution parameters,
    R-Multiple progress bar, and optional one-click copy broker ticket.
    """
    if card.action_type == "NEW_ENTRY":
        action_badge_cls = "sqe-badge-safe"
        action_badge_txt = "NEW BUY ENTRY"
    elif card.action_type == "STOP_RATCHETED":
        action_badge_cls = "sqe-badge-moderate"
        action_badge_txt = "STOP RATCHETED UP"
    elif card.action_type == "BARRIER_EXIT":
        action_badge_cls = "sqe-badge-crimson"
        action_badge_txt = "BARRIER EXIT"
    else:
        action_badge_cls = "sqe-badge-cyan"
        action_badge_txt = "ACTIVE HOLD"

    time_badge_cls = (
        "sqe-badge-moderate" if card.bars_held >= 10 else "sqe-badge-cyan"
    )

    if card.historical_win_rate_pct >= 50.0:
        wr_color = SEMANTIC_EMERALD
    elif card.historical_win_rate_pct >= 35.0:
        wr_color = ACCENT_CYAN
    else:
        wr_color = SEMANTIC_AMBER

    pnl_sign = "+" if card.unrealized_pnl_dollars >= 0.0 else ""
    pnl_color = SEMANTIC_EMERALD if card.unrealized_pnl_dollars >= 0.0 else SEMANTIC_CRIMSON
    r_sign = "+" if card.unrealized_r_multiple >= 0.0 else ""

    stop_label = (
        f"RATCHETED STOP (WAS ${card.initial_stop_price:,.2f})"
        if card.trailing_stop_price > card.initial_stop_price + 1e-4
        else "INITIAL STOP-LOSS (-1R)"
    )

    st.markdown(
        f"""
        <div class="sqe-card">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;border-bottom:1px solid {BORDER_SUBTLE};padding-bottom:10px;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <span class="sqe-mono" style="font-size:1.35rem;font-weight:700;color:{TEXT_PRIMARY};">{card.ticker}</span>
                    <span class="sqe-badge sqe-badge-cyan">{card.index_id}</span>
                    <span class="sqe-badge {action_badge_cls}">{action_badge_txt}</span>
                    <span class="sqe-badge {time_badge_cls}">⏱️ DAY {card.bars_held}/{card.max_holding_bars}</span>
                </div>
                <div class="sqe-mono" style="font-size:0.86rem;">
                    <span style="color:{TEXT_MUTED};">LAST PX:</span>
                    <span style="color:{TEXT_PRIMARY};font-weight:700;"> ${card.current_price:,.2f}</span>
                    <span style="margin-left:10px;color:{pnl_color};font-weight:600;">
                        ({pnl_sign}${card.unrealized_pnl_dollars:,.2f} | {r_sign}{card.unrealized_r_multiple:.2f}R)
                    </span>
                </div>
            </div>

            <div class="sqe-grid-4">
                <div class="sqe-metric-box">
                    <div style="font-size:0.68rem;color:{TEXT_MUTED};text-transform:uppercase;font-weight:600;">500D WIN RATE</div>
                    <div class="sqe-mono" style="font-size:1.15rem;font-weight:700;color:{wr_color};margin-top:2px;">
                        {card.historical_win_rate_pct:.1f}%
                    </div>
                    <div class="sqe-progress-track">
                        <div class="sqe-progress-fill" style="width:{min(100.0, card.historical_win_rate_pct):.1f}%;background:{wr_color};"></div>
                    </div>
                </div>

                <div class="sqe-metric-box">
                    <div style="font-size:0.68rem;color:{TEXT_MUTED};text-transform:uppercase;font-weight:600;">EXPECTED VALUE (EV)</div>
                    <div class="sqe-mono" style="font-size:1.15rem;font-weight:700;color:{SEMANTIC_EMERALD};margin-top:2px;">
                        +{card.historical_ev_r_multiple:.2f} R / Trade
                    </div>
                    <div style="font-size:0.68rem;color:{TEXT_MUTED};margin-top:4px;">500d Walk-Forward Edge</div>
                </div>

                <div class="sqe-metric-box">
                    <div style="font-size:0.68rem;color:{TEXT_MUTED};text-transform:uppercase;font-weight:600;">PRIMARY BREAKOUT SCORE</div>
                    <div class="sqe-mono" style="font-size:1.15rem;font-weight:700;color:{ACCENT_CYAN};margin-top:2px;">
                        {card.primary_score:.1f} <span style="font-size:0.8rem;color:{TEXT_MUTED};">/ 100</span>
                    </div>
                    <div style="font-size:0.68rem;color:{TEXT_MUTED};margin-top:4px;">Mom 45% • Vol 30% • RS 25%</div>
                </div>

                <div class="sqe-metric-box">
                    <div style="font-size:0.68rem;color:{TEXT_MUTED};text-transform:uppercase;font-weight:600;">META-CONVICTION SCALAR</div>
                    <div style="margin-top:4px;">
                        <span class="sqe-badge sqe-badge-violet" style="font-size:0.86rem;padding:4px 10px;">
                            {card.meta_conviction_scalar:.2f}x Sizing Conviction
                        </span>
                    </div>
                    <div style="font-size:0.68rem;color:{TEXT_MUTED};margin-top:4px;">López de Prado &phi;<sub>meta</sub></div>
                </div>
            </div>

            <div class="sqe-grid-4" style="margin-bottom:8px;">
                <div class="sqe-metric-box">
                    <div style="font-size:0.66rem;color:{TEXT_MUTED};text-transform:uppercase;">BUY QUANTITY &amp; COST</div>
                    <div class="sqe-mono" style="font-size:0.98rem;font-weight:700;color:{TEXT_PRIMARY};margin-top:2px;">
                        {card.shares:,} Shares
                    </div>
                    <div class="sqe-mono" style="font-size:0.74rem;color:{TEXT_MUTED};">Cost: ${card.position_cost_dollars:,.2f}</div>
                </div>

                <div class="sqe-metric-box">
                    <div style="font-size:0.66rem;color:{TEXT_MUTED};text-transform:uppercase;">ENTRY PRICE</div>
                    <div class="sqe-mono" style="font-size:0.98rem;font-weight:700;color:{ACCENT_CYAN};margin-top:2px;">
                        ${card.entry_price:,.2f}
                    </div>
                    <div class="sqe-mono" style="font-size:0.74rem;color:{TEXT_MUTED};">Opened: {card.entry_date.isoformat()}</div>
                </div>

                <div class="sqe-metric-box">
                    <div style="font-size:0.66rem;color:{TEXT_MUTED};text-transform:uppercase;">{stop_label}</div>
                    <div class="sqe-mono" style="font-size:0.98rem;font-weight:700;color:{SEMANTIC_CRIMSON};margin-top:2px;">
                        ${card.trailing_stop_price:,.2f}
                    </div>
                    <div class="sqe-mono" style="font-size:0.74rem;color:{TEXT_MUTED};">Open Risk: ${card.open_dollar_risk:,.2f}</div>
                </div>

                <div class="sqe-metric-box">
                    <div style="font-size:0.66rem;color:{TEXT_MUTED};text-transform:uppercase;">TAKE-PROFIT TARGET (+3R)</div>
                    <div class="sqe-mono" style="font-size:0.98rem;font-weight:700;color:{SEMANTIC_EMERALD};margin-top:2px;">
                        ${card.take_profit_price:,.2f}
                    </div>
                    <div class="sqe-mono" style="font-size:0.74rem;color:{TEXT_MUTED};">Target: +${card.expected_profit_dollars:,.2f}</div>
                </div>
            </div>

            <div style="margin-top:6px;">
                <div style="display:flex;justify-content:space-between;font-size:0.70rem;color:{TEXT_MUTED};" class="sqe-mono">
                    <span>🛡️ STOP: ${card.trailing_stop_price:,.2f}</span>
                    <span>CAGE TRAJECTORY PROGRESS: {card.r_progress_pct:.1f}%</span>
                    <span>🎯 TARGET: ${card.take_profit_price:,.2f}</span>
                </div>
                <div class="sqe-progress-track">
                    <div class="sqe-progress-fill" style="width:{card.r_progress_pct:.1f}%;background:linear-gradient(90deg, {ACCENT_CYAN} 0%, {SEMANTIC_EMERALD} 100%);"></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if show_copy_ticket:
        st.code(card.broker_order_ticket_text, language="text")


# =============================================================================
# 7. CORE DASHBOARD 4: INTERACTIVE TRIPLE-BARRIER PRICE CAGE CHART
# =============================================================================


def build_triple_barrier_cage_chart(
    ohlcv_df: pd.DataFrame,
    card: StockConvictionCardVM,
) -> go.Figure:
    """
    Plots the trailing 60-day OHLC candlesticks + 20-day SMA overlaid with
    the Triple-Barrier protective cage (`Take-Profit`, `Entry`, `Active Chandelier Stop`,
    and `Initial Stop` ghost floor if ratcheted), plus shaded reward/risk zones.
    """
    fig = go.Figure()

    if ohlcv_df is None or ohlcv_df.empty:
        fig.update_layout(
            height=440,
            paper_bgcolor=BG_SURFACE,
            plot_bgcolor=BG_PRIMARY,
            title="No OHLCV data available for selected ticker",
            font=dict(color=TEXT_PRIMARY),
        )
        return fig

    df = ohlcv_df.tail(60).copy()
    if "SMA_20" not in df.columns:
        df["SMA_20"] = df["Close"].rolling(window=20, min_periods=1).mean().round(2)

    x_dates = df.index
    x_start = x_dates[0]
    x_end = x_dates[-1]

    # 1. Reward vs. Risk Shaded Boxes
    fig.add_shape(
        type="rect",
        xref="x",
        yref="y",
        x0=x_start,
        x1=x_end,
        y0=card.entry_price,
        y1=card.take_profit_price,
        fillcolor="rgba(16, 185, 129, 0.07)",
        line=dict(width=0),
        layer="below",
    )
    fig.add_shape(
        type="rect",
        xref="x",
        yref="y",
        x0=x_start,
        x1=x_end,
        y0=card.trailing_stop_price,
        y1=card.entry_price,
        fillcolor="rgba(239, 68, 68, 0.08)",
        line=dict(width=0),
        layer="below",
    )

    # 2. 60-Day OHLC Candlesticks
    fig.add_trace(
        go.Candlestick(
            x=x_dates,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=f"{card.ticker} OHLC",
            increasing_line_color=SEMANTIC_EMERALD,
            increasing_fillcolor=SEMANTIC_EMERALD,
            decreasing_line_color=SEMANTIC_CRIMSON,
            decreasing_fillcolor=SEMANTIC_CRIMSON,
        )
    )

    # 3. 20-Day SMA Trend Support Line
    fig.add_trace(
        go.Scatter(
            x=x_dates,
            y=df["SMA_20"],
            mode="lines",
            name="20-Day SMA",
            line=dict(color="#6366F1", width=1.6),
            hovertemplate="SMA 20: $%{y:.2f}<extra></extra>",
        )
    )

    # 4. Upper Barrier: Take-Profit Target (+3R)
    fig.add_hline(
        y=card.take_profit_price,
        line_dash="dash",
        line_color=SEMANTIC_EMERALD,
        line_width=2,
        annotation_text=f"🎯 TAKE PROFIT (+3R): ${card.take_profit_price:.2f}",
        annotation_position="top right",
        annotation_font=dict(
            family="JetBrains Mono, monospace",
            size=11,
            color=SEMANTIC_EMERALD,
        ),
    )

    # 5. Reference Line: Entry Price
    fig.add_hline(
        y=card.entry_price,
        line_dash="solid",
        line_color=ACCENT_CYAN,
        line_width=1.8,
        annotation_text=f"ENTRY: ${card.entry_price:.2f}",
        annotation_position="top left",
        annotation_font=dict(
            family="JetBrains Mono, monospace",
            size=11,
            color=ACCENT_CYAN,
        ),
    )

    # 6. Lower Barrier: Active Ratcheted Chandelier Stop
    fig.add_hline(
        y=card.trailing_stop_price,
        line_dash="solid",
        line_color=SEMANTIC_CRIMSON,
        line_width=2,
        annotation_text=f"🛡️ ACTIVE STOP (Chandelier): ${card.trailing_stop_price:.2f}",
        annotation_position="bottom right",
        annotation_font=dict(
            family="JetBrains Mono, monospace",
            size=11,
            color=SEMANTIC_CRIMSON,
        ),
    )

    # 7. Initial Stop Ghost Line (if Chandelier Stop has ratcheted upward)
    if card.trailing_stop_price > card.initial_stop_price + 1e-4:
        initial_1r = max(1e-4, card.entry_price - card.initial_stop_price)
        locked_r = (card.trailing_stop_price - card.initial_stop_price) / initial_1r
        fig.add_hline(
            y=card.initial_stop_price,
            line_dash="dot",
            line_color=TEXT_MUTED,
            line_width=1.3,
            annotation_text=(
                f"Initial Stop: ${card.initial_stop_price:.2f} (Protected +{locked_r:.2f}R)"
            ),
            annotation_position="bottom left",
            annotation_font=dict(
                family="JetBrains Mono, monospace",
                size=10,
                color=TEXT_MUTED,
            ),
        )

    remaining_days = max(0, card.max_holding_bars - card.bars_held)
    y_min = min(float(df["Low"].min()), card.initial_stop_price, card.trailing_stop_price) * 0.975
    y_max = max(float(df["High"].max()), card.take_profit_price) * 1.025

    fig.update_layout(
        title=dict(
            text=(
                f"<span style='font-size:15px;font-weight:700;color:{TEXT_PRIMARY};'>"
                f"{card.ticker} ({card.index_id}) — TRIPLE-BARRIER PROTECTIVE CAGE</span>"
                f"<span style='font-size:12px;color:{SEMANTIC_AMBER if remaining_days <= 4 else ACCENT_CYAN};"
                f"font-family:JetBrains Mono,monospace;margin-left:16px;'>"
                f"⏱️ Time Barrier: Day {card.bars_held} of {card.max_holding_bars} "
                f"({remaining_days} Trading Days Left)</span>"
            ),
            x=0.01,
            xanchor="left",
        ),
        height=440,
        margin=dict(l=16, r=24, t=48, b=20),
        paper_bgcolor=BG_SURFACE,
        plot_bgcolor=BG_PRIMARY,
        xaxis=dict(
            rangeslider=dict(visible=False),
            gridcolor=BORDER_SUBTLE,
            showgrid=True,
            tickfont=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_MUTED),
        ),
        yaxis=dict(
            range=[y_min, y_max],
            tickprefix="$",
            gridcolor=BORDER_SUBTLE,
            showgrid=True,
            side="right",
            tickfont=dict(family="JetBrains Mono, monospace", size=11, color=TEXT_PRIMARY),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1.0,
            font=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_MUTED),
        ),
        hovermode="x unified",
    )
    return fig


# =============================================================================
# 8. CORE DASHBOARD 5: TRACK RECORD & R-MULTIPLE DISTRIBUTION CHARTS
# =============================================================================


def build_performance_charts(
    closed_trades: List[ClosedTradeAuditSchema],
    initial_capital: float = 100_000.0,
) -> Tuple[go.Figure, go.Figure]:
    """
    Returns `(equity_curve_fig, r_distribution_fig)`:
    1. Chronological Cumulative Equity Curve with High-Water Mark overlay.
    2. Realized R-Multiple Distribution bar chart colored Emerald (>= 0R) vs Crimson (< 0R).
    Gracefully handles empty `closed_trades` lists without errors.
    """
    base_cap = max(1_000.0, float(initial_capital))

    # -------------------------------------------------------------------------
    # Chart A: Cumulative Equity Curve + High-Water Mark
    # -------------------------------------------------------------------------
    equity_fig = go.Figure()

    if not closed_trades:
        x_labels = ["Start", "Current"]
        y_equity = [base_cap, base_cap]
        y_hwm = [base_cap, base_cap]
    else:
        sorted_trades = sorted(closed_trades, key=lambda t: (t.exit_date, t.entry_date))
        x_labels = ["Initial"]
        y_equity = [base_cap]
        y_hwm = [base_cap]

        running_eq = base_cap
        running_hwm = base_cap
        for idx, trade in enumerate(sorted_trades, start=1):
            running_eq = round(running_eq + trade.realized_pnl_dollars, 2)
            running_hwm = max(running_hwm, running_eq)
            x_labels.append(f"#{idx} {trade.ticker} ({trade.exit_date.strftime('%m/%d')})")
            y_equity.append(running_eq)
            y_hwm.append(running_hwm)

    equity_fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=y_equity,
            mode="lines+markers",
            name="Cumulative Equity ($)",
            line=dict(color=ACCENT_CYAN, width=2.5),
            marker=dict(size=6, color=ACCENT_CYAN),
            fill="tozeroy",
            fillcolor="rgba(6, 182, 212, 0.12)",
            hovertemplate="<b>%{x}</b><br>Equity: $%{y:,.2f}<extra></extra>",
        )
    )

    equity_fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=y_hwm,
            mode="lines",
            name="High-Water Mark",
            line=dict(color=SEMANTIC_EMERALD, width=1.5, dash="dot"),
            hovertemplate="High-Water Mark: $%{y:,.2f}<extra></extra>",
        )
    )

    min_eq = min(y_equity) * 0.985
    max_eq = max(y_hwm) * 1.015

    equity_fig.update_layout(
        title=dict(
            text=(
                f"<span style='font-size:13px;font-weight:600;color:{TEXT_PRIMARY};'>"
                "CHRONOLOGICAL CUMULATIVE EQUITY &amp; HIGH-WATER MARK</span>"
            ),
            x=0.01,
            xanchor="left",
        ),
        height=320,
        margin=dict(l=16, r=16, t=44, b=24),
        paper_bgcolor=BG_SURFACE,
        plot_bgcolor=BG_PRIMARY,
        xaxis=dict(
            gridcolor=BORDER_SUBTLE,
            tickfont=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_MUTED),
        ),
        yaxis=dict(
            range=[min_eq, max_eq],
            tickprefix="$",
            gridcolor=BORDER_SUBTLE,
            tickfont=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_PRIMARY),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_MUTED),
        ),
        hovermode="x unified",
    )

    # -------------------------------------------------------------------------
    # Chart B: Realized R-Multiple Distribution Bar Chart
    # -------------------------------------------------------------------------
    r_fig = go.Figure()

    if not closed_trades:
        r_fig.add_annotation(
            text="No Closed Trades Recorded Yet (100% Capital Preservation)",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(family="JetBrains Mono, monospace", size=12, color=TEXT_MUTED),
        )
    else:
        sorted_trades = sorted(closed_trades, key=lambda t: (t.exit_date, t.entry_date))
        trade_labels = [
            f"#{i} {t.ticker}" for i, t in enumerate(sorted_trades, start=1)
        ]
        r_values = [round(t.realized_r_multiple, 2) for t in sorted_trades]
        bar_colors = [
            SEMANTIC_EMERALD if r >= 0.0 else SEMANTIC_CRIMSON for r in r_values
        ]
        reason_labels = [
            t.exit_reason.value if isinstance(t.exit_reason, ExitReason) else str(t.exit_reason)
            for t in sorted_trades
        ]

        r_fig.add_trace(
            go.Bar(
                x=trade_labels,
                y=r_values,
                marker_color=bar_colors,
                text=[f"{r:+.2f}R" for r in r_values],
                textposition="outside",
                textfont=dict(
                    family="JetBrains Mono, monospace",
                    size=10,
                    color=TEXT_PRIMARY,
                ),
                customdata=reason_labels,
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Realized Outcome: %{y:+.2f} R<br>"
                    "Exit Trigger: %{customdata}<extra></extra>"
                ),
                name="Realized R",
            )
        )

        r_fig.add_hline(
            y=0.0,
            line_color=BORDER_SUBTLE,
            line_width=1.5,
        )

    r_fig.update_layout(
        title=dict(
            text=(
                f"<span style='font-size:13px;font-weight:600;color:{TEXT_PRIMARY};'>"
                "REALIZED R-MULTIPLE DISTRIBUTION (ASYMMETRIC PAYOFF PROFILE)</span>"
            ),
            x=0.01,
            xanchor="left",
        ),
        height=320,
        margin=dict(l=16, r=16, t=44, b=24),
        paper_bgcolor=BG_SURFACE,
        plot_bgcolor=BG_PRIMARY,
        xaxis=dict(
            gridcolor=BORDER_SUBTLE,
            tickfont=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_MUTED),
        ),
        yaxis=dict(
            ticksuffix=" R",
            gridcolor=BORDER_SUBTLE,
            tickfont=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_PRIMARY),
        ),
        showlegend=False,
    )

    return equity_fig, r_fig

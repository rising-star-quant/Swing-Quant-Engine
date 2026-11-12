from __future__ import annotations

from typing import List, Literal
import pandas as pd
import streamlit as st

from src.dashboard_service import (
    DashboardDataService,
    GUIAuthController,
    PortfolioDashboardSnapshotVM,
    StockConvictionCardVM,
)
from src.schemas import ExitReason
from src.ui_theme import (
    ACCENT_CYAN,
    BG_PRIMARY,
    BG_SURFACE,
    BORDER_SUBTLE,
    SEMANTIC_AMBER,
    SEMANTIC_CRIMSON,
    SEMANTIC_EMERALD,
    SEMANTIC_VIOLET,
    TEXT_MUTED,
    TEXT_PRIMARY,
    build_capital_allocation_chart,
    build_performance_charts,
    build_portfolio_heat_gauge,
    build_triple_barrier_cage_chart,
    inject_institutional_css,
    render_stock_conviction_card,
    render_top_kpi_strip,
)

# =============================================================================
# 1. BOOTSTRAP & PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Swing Quant Engine | Institutional Terminal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_institutional_css()

auth_controller = GUIAuthController()
data_service = DashboardDataService()

SubscriptionTierType = Literal["FREE", "PRO", "ELITE"]

# =============================================================================
# 2. SESSION STATE INITIALIZATION
# =============================================================================

if "subscription_tier" not in st.session_state:
    st.session_state["subscription_tier"] = "ELITE"

if "force_demo_mode" not in st.session_state:
    st.session_state["force_demo_mode"] = False

if "custom_equity" not in st.session_state:
    st.session_state["custom_equity"] = 100_000.0

if "demo_subscribed_indices" not in st.session_state:
    st.session_state["demo_subscribed_indices"] = ["RUT_2000", "SP_400"]

if "demo_max_heat_pct" not in st.session_state:
    st.session_state["demo_max_heat_pct"] = 0.06


# =============================================================================
# 3. LEFT SIDEBAR NAVIGATION & COMMERCIAL TIER RAIL
# =============================================================================

with st.sidebar:
    is_demo_active = bool(st.session_state["force_demo_mode"])
    env_badge_cls = "sqe-badge-violet" if is_demo_active else "sqe-badge-safe"
    env_badge_txt = "🧪 SANDBOX DEMO" if is_demo_active else "🟢 LIVE PRODUCTION"

    st.markdown(
        f"""
        <div style="padding-bottom:12px;border-bottom:1px solid {BORDER_SUBTLE};margin-bottom:14px;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;">
                <span style="font-size:1.05rem;font-weight:700;letter-spacing:0.04em;color:{TEXT_PRIMARY};">
                    🏛️ SWING QUANT ENGINE
                </span>
            </div>
            <div style="margin-top:6px;display:flex;align-items:center;justify-content:space-between;">
                <span style="font-size:0.72rem;color:{TEXT_MUTED};">Institutional Execution Cockpit</span>
                <span class="sqe-badge {env_badge_cls}">{env_badge_txt}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    toggled_demo = st.toggle(
        "🧪 Interactive Sandbox Demo (5 Positions)",
        value=st.session_state["force_demo_mode"],
        help="Switch between the live virtual_portfolio.json ledger and a populated 5-position institutional demo book.",
    )
    if toggled_demo != st.session_state["force_demo_mode"]:
        st.session_state["force_demo_mode"] = toggled_demo
        st.rerun()

    tier_options: List[SubscriptionTierType] = ["ELITE", "PRO", "FREE"]
    current_tier_idx = (
        tier_options.index(st.session_state["subscription_tier"])
        if st.session_state["subscription_tier"] in tier_options
        else 0
    )
    selected_tier = st.selectbox(
        "Subscriber Tier Preview",
        options=tier_options,
        index=current_tier_idx,
        help="Preview commercial tier entitlements: Institutional (ELITE), Quant Trader (PRO), or Explorer (FREE).",
    )
    st.session_state["subscription_tier"] = selected_tier

    user_claims, jwt_token = auth_controller.get_quick_preview_session(tier=selected_tier)
    st.session_state["jwt_token"] = jwt_token

    with st.expander("🔐 Subscriber Login Gate", expanded=False):
        login_email = st.text_input(
            "Subscriber Email",
            value="elite.owner@swingquant.io",
            key="sidebar_login_email",
        )
        login_password = st.text_input(
            "Password",
            type="password",
            value="",
            placeholder="QuantEngine#2026!",
            key="sidebar_login_password",
        )
        if st.button("Authenticate Session", use_container_width=True):
            try:
                verified_claims, signed_tok = auth_controller.authenticate_session(
                    email=login_email,
                    password=login_password,
                    tier=selected_tier,
                )
                user_claims = verified_claims
                st.session_state["jwt_token"] = signed_tok
                st.success(f"Authenticated ({verified_claims.role.value})")
            except Exception as auth_exc:
                st.error(str(auth_exc))

    custom_equity_input = st.number_input(
        "Broker Account Capital ($)",
        min_value=10_000.0,
        max_value=5_000_000.0,
        value=float(st.session_state["custom_equity"]),
        step=5_000.0,
        disabled=(selected_tier == "FREE"),
        help="Dynamically scales share quantities and dollar risk budgets to match your real-world brokerage account equity.",
    )
    st.session_state["custom_equity"] = float(custom_equity_input)

    st.markdown(
        f"<hr style='border:0;border-top:1px solid {BORDER_SUBTLE};margin:12px 0;'>",
        unsafe_allow_html=True,
    )

    active_view = st.radio(
        "COCKPIT NAVIGATION",
        options=[
            "🎯 Today's Orders (Action Bridge)",
            "🛡️ Active Risk Book (Live Positions)",
            "📈 Track Record & Audit Lab",
            "⚙️ Control Room & Settings",
        ],
        index=0,
    )

# =============================================================================
# 4. SNAPSHOT LOADING & SIDEBAR FOOTER TELEMETRY
# =============================================================================

snapshot: PortfolioDashboardSnapshotVM = data_service.load_dashboard_snapshot(
    portfolio_id=GUIAuthController.DEFAULT_PORTFOLIO_ID,
    user_claims=user_claims,
    force_demo_mode=bool(st.session_state["force_demo_mode"]),
    custom_account_equity=float(st.session_state["custom_equity"]),
    subscription_tier=selected_tier,
)

if snapshot.is_demo_mode:
    snapshot.ledger.subscribed_indices = list(st.session_state["demo_subscribed_indices"])
    snapshot.ledger.max_portfolio_heat_pct = float(st.session_state["demo_max_heat_pct"])

with st.sidebar:
    st.markdown(
        f"<hr style='border:0;border-top:1px solid {BORDER_SUBTLE};margin:12px 0;'>",
        unsafe_allow_html=True,
    )
    idx_badges_html = " ".join(
        f"<span class='sqe-badge sqe-badge-cyan'>{idx}</span>"
        for idx in snapshot.ledger.subscribed_indices
    )
    st.markdown(
        f"""
        <div style="font-size:0.74rem;color:{TEXT_MUTED};line-height:1.6;">
            <div><b>Portfolio:</b> <span style="color:{TEXT_PRIMARY};">{snapshot.ledger.portfolio_name}</span></div>
            <div><b>Last EOD Sync:</b> <span class="sqe-mono" style="color:{TEXT_PRIMARY};">{snapshot.ledger.as_of_date.isoformat()}</span></div>
            <div><b>RBAC Role:</b> <span class="sqe-mono" style="color:{ACCENT_CYAN};">{user_claims.role.value} ({selected_tier})</span></div>
            <div style="margin-top:6px;"><b>Active Indices:</b><br>{idx_badges_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("🔄 Refresh Cached State", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# =============================================================================
# 5. GLOBAL TOP KPI STRIP & SMART 100%-CASH EMPTY-STATE BANNER
# =============================================================================

render_top_kpi_strip(snapshot)

if not snapshot.is_demo_mode and len(snapshot.active_conviction_cards) == 0:
    st.markdown(
        f"""
        <div class="sqe-card" style="border-left: 4px solid {SEMANTIC_EMERALD}; margin-top: 10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                <div>
                    <div style="font-size:1.08rem;font-weight:700;color:{TEXT_PRIMARY};">
                        🛡️ Active Capital Preservation Mode (100% Cash — $0.00 Open Stop Risk)
                    </div>
                    <div style="font-size:0.86rem;color:{TEXT_MUTED};margin-top:4px;">
                        The 500-day Walk-Forward Meta-Labeling &amp; Simons liquidity gates filtered out low-expectancy noise on
                        <span class="sqe-mono" style="color:{TEXT_PRIMARY};">{snapshot.ledger.as_of_date.isoformat()}</span>.
                        Your live production ledger is <b>100% liquid (${snapshot.ledger.cash_balance:,.2f})</b> awaiting asymmetric 1:3 R/R setups.
                    </div>
                </div>
                <span class="sqe-badge sqe-badge-safe">CAPITAL PROTECTED</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "🧪 Switch to Populated Demo Portfolio (5 Active Trades)",
        type="primary",
        use_container_width=False,
    ):
        st.session_state["force_demo_mode"] = True
        st.rerun()


# =============================================================================
# 6. VIEW 1: DAILY ACTION BRIDGE (TODAY'S ORDERS)
# =============================================================================

if active_view == "🎯 Today's Orders (Action Bridge)":
    st.markdown(
        f"""
        <div style="margin-top:8px;margin-bottom:14px;">
            <h2 style="margin:0;font-size:1.35rem;font-weight:700;color:{TEXT_PRIMARY};">
                🎯 Daily Post-Market Action Bridge
            </h2>
            <p style="margin:4px 0 0 0;font-size:0.85rem;color:{TEXT_MUTED};">
                Copy-pasteable broker instructions generated from Point-in-Time EOD settlement ({snapshot.ledger.as_of_date.isoformat()}).
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # Section A: Urgent Barrier Exits & Ratcheted Stop Updates
    # -------------------------------------------------------------------------
    st.markdown(
        f"<h4 style='color:{TEXT_PRIMARY};font-size:1.0rem;margin-bottom:8px;'>"
        "🚨 Section A — Urgent Barrier Exits &amp; Chandelier Stop Ratchets</h4>",
        unsafe_allow_html=True,
    )

    col_exits, col_ratchets = st.columns(2)

    with col_exits:
        if not snapshot.todays_closed_exits:
            st.markdown(
                f"""
                <div class="sqe-card" style="padding:12px 16px;">
                    <span class="sqe-badge sqe-badge-cyan">NO BARRIER EXITS TODAY</span>
                    <div style="font-size:0.82rem;color:{TEXT_MUTED};margin-top:6px;">
                        Zero active positions hit their Take-Profit, Stop-Loss, or 14-Day Time Barrier today.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            for closed in snapshot.todays_closed_exits:
                exit_badge = (
                    "sqe-badge-safe"
                    if closed.realized_pnl_dollars >= 0.0
                    else "sqe-badge-crimson"
                )
                pnl_sign = "+" if closed.realized_pnl_dollars >= 0.0 else ""
                r_sign = "+" if closed.realized_r_multiple >= 0.0 else ""
                reason_str = (
                    closed.exit_reason.value
                    if isinstance(closed.exit_reason, ExitReason)
                    else str(closed.exit_reason)
                )
                st.markdown(
                    f"""
                    <div class="sqe-card" style="border-left:4px solid {SEMANTIC_EMERALD if closed.realized_pnl_dollars >= 0 else SEMANTIC_CRIMSON};">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span class="sqe-mono" style="font-size:1.1rem;font-weight:700;color:{TEXT_PRIMARY};">{closed.ticker}</span>
                                <span class="sqe-badge sqe-badge-cyan" style="margin-left:6px;">{closed.index_id}</span>
                                <span class="sqe-badge {exit_badge}" style="margin-left:6px;">{reason_str}</span>
                            </div>
                            <span class="sqe-mono" style="font-weight:700;color:{SEMANTIC_EMERALD if closed.realized_pnl_dollars >= 0 else SEMANTIC_CRIMSON};">
                                {pnl_sign}${closed.realized_pnl_dollars:,.2f} ({r_sign}{closed.realized_r_multiple:.2f}R)
                            </span>
                        </div>
                        <div class="sqe-mono" style="font-size:0.78rem;color:{TEXT_MUTED};margin-top:6px;">
                            LIQUIDATED {closed.shares:,} SHARES @ ${closed.exit_price:,.2f} (Entry: ${closed.entry_price:,.2f} | Held {closed.bars_held}d)
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with col_ratchets:
        if not snapshot.todays_ratcheted_stops:
            st.markdown(
                f"""
                <div class="sqe-card" style="padding:12px 16px;">
                    <span class="sqe-badge sqe-badge-cyan">NO STOP RATCHETS TODAY</span>
                    <div style="font-size:0.82rem;color:{TEXT_MUTED};margin-top:6px;">
                        All open GTC stop-loss orders remain at their current protective floor.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            for r_card in snapshot.todays_ratcheted_stops:
                st.markdown(
                    f"""
                    <div class="sqe-card" style="border-left:4px solid {SEMANTIC_AMBER};">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span class="sqe-mono" style="font-size:1.1rem;font-weight:700;color:{TEXT_PRIMARY};">{r_card.ticker}</span>
                                <span class="sqe-badge sqe-badge-moderate" style="margin-left:6px;">RAISE GTC STOP-LOSS</span>
                            </div>
                            <span class="sqe-mono" style="font-size:0.85rem;color:{SEMANTIC_AMBER};font-weight:700;">
                                ${r_card.initial_stop_price:,.2f} &rarr; ${r_card.trailing_stop_price:,.2f}
                            </span>
                        </div>
                        <div class="sqe-mono" style="font-size:0.78rem;color:{TEXT_MUTED};margin-top:6px;">
                            Update broker GTC stop for {r_card.shares:,} shares to lock in Chandelier floor (${r_card.trailing_stop_price:,.2f}).
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # -------------------------------------------------------------------------
    # Section B: Approved Meta-Labeled Buy Entries
    # -------------------------------------------------------------------------
    st.markdown(
        f"<hr style='border:0;border-top:1px solid {BORDER_SUBTLE};margin:14px 0;'>",
        unsafe_allow_html=True,
    )

    hdr_col1, hdr_col2 = st.columns([3, 1])
    with hdr_col1:
        st.markdown(
            f"<h4 style='color:{TEXT_PRIMARY};font-size:1.0rem;margin:0;'>"
            "🎯 Section B — Approved Meta-Labeled Execution Tickets</h4>",
            unsafe_allow_html=True,
        )
    with hdr_col2:
        show_all_tickets = st.checkbox(
            "Show All Active Book Tickets",
            value=False,
            help="Display all active positions in addition to today's newly entered setups.",
        )

    if selected_tier == "FREE":
        st.markdown(
            f"""
            <div class="sqe-card" style="border-left:4px solid {SEMANTIC_VIOLET};padding:12px 16px;">
                <span class="sqe-badge sqe-badge-violet">EXPLORER (FREE) TIER PREVIEW</span>
                <span style="font-size:0.84rem;color:{TEXT_PRIMARY};margin-left:8px;">
                    Displaying Top-1 Signal Preview. Upgrade to <b>PRO</b> or <b>ELITE</b> in the sidebar for the full EOD feed and custom account sizing.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    target_cards: List[StockConvictionCardVM] = (
        snapshot.active_conviction_cards
        if show_all_tickets
        else snapshot.todays_new_entries
    )
    if selected_tier == "FREE" and len(target_cards) > 1:
        target_cards = target_cards[:1]

    if not target_cards:
        st.markdown(
            f"""
            <div class="sqe-card" style="text-align:center;padding:24px;">
                <div style="font-size:0.95rem;font-weight:600;color:{TEXT_PRIMARY};">
                    No New Buy Orders Triggered Today
                </div>
                <div style="font-size:0.82rem;color:{TEXT_MUTED};margin-top:4px;">
                    Toggle <b>"Show All Active Book Tickets"</b> above or enable <b>🧪 Interactive Sandbox Demo</b> in the sidebar to inspect 5 live conviction cards.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for card in target_cards:
            render_stock_conviction_card(card, show_copy_ticket=True)


# =============================================================================
# 7. VIEW 2: LIVE RISK & PORTFOLIO COMMAND (ACTIVE RISK BOOK)
# =============================================================================

elif active_view == "🛡️ Active Risk Book (Live Positions)":
    st.markdown(
        f"""
        <div style="margin-top:8px;margin-bottom:14px;">
            <h2 style="margin:0;font-size:1.35rem;font-weight:700;color:{TEXT_PRIMARY};">
                🛡️ Active Risk Book &amp; Triple-Barrier Cage Command
            </h2>
            <p style="margin:4px 0 0 0;font-size:0.85rem;color:{TEXT_MUTED};">
                Real-time portfolio heat monitoring, dry powder allocation, and interactive 60-day Triple-Barrier price cages.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    total_open_dollar_risk = sum(
        p.open_dollar_risk for p in snapshot.ledger.open_positions.values()
    )

    gauge_col, donut_col = st.columns(2)
    with gauge_col:
        heat_fig = build_portfolio_heat_gauge(
            current_heat_pct=snapshot.ledger.current_portfolio_heat_pct * 100.0,
            max_heat_pct=snapshot.ledger.max_portfolio_heat_pct * 100.0,
            open_dollar_risk=total_open_dollar_risk,
        )
        st.plotly_chart(heat_fig, use_container_width=True)

    with donut_col:
        alloc_fig = build_capital_allocation_chart(
            cash_balance=snapshot.ledger.cash_balance,
            total_equity=snapshot.ledger.total_equity,
            cards=snapshot.active_conviction_cards,
            max_slots=snapshot.ledger.max_concurrent_positions,
        )
        st.plotly_chart(alloc_fig, use_container_width=True)

    st.markdown(
        f"<hr style='border:0;border-top:1px solid {BORDER_SUBTLE};margin:12px 0;'>",
        unsafe_allow_html=True,
    )

    if not snapshot.active_conviction_cards:
        st.info(
            "No active positions in the current ledger. Enable '🧪 Interactive Sandbox Demo' in the sidebar to inspect the 5-position book and interactive Triple-Barrier Price Cage."
        )
    else:
        st.markdown(
            f"<h4 style='color:{TEXT_PRIMARY};font-size:1.05rem;margin-bottom:8px;'>"
            "🔍 Interactive Triple-Barrier Price Cage Explorer</h4>",
            unsafe_allow_html=True,
        )

        ticker_map = {c.ticker: c for c in snapshot.active_conviction_cards}
        ticker_options = list(ticker_map.keys())

        selected_ticker = st.selectbox(
            "Select Active Holding to Inspect Protective Barrier Cage (60-Day OHLCV + SMA_20)",
            options=ticker_options,
            format_func=lambda tk: (
                f"{tk} ({ticker_map[tk].index_id}) — Entry: ${ticker_map[tk].entry_price:.2f} | "
                f"Active Stop: ${ticker_map[tk].trailing_stop_price:.2f} | "
                f"Target: ${ticker_map[tk].take_profit_price:.2f} | "
                f"Win Rate: {ticker_map[tk].historical_win_rate_pct:.1f}%"
            ),
        )

        selected_card = ticker_map[selected_ticker]
        ohlcv_df = data_service.load_ticker_cage_ohlcv(
            ticker=selected_ticker,
            card=selected_card,
            is_demo=snapshot.is_demo_mode,
        )
        cage_fig = build_triple_barrier_cage_chart(ohlcv_df=ohlcv_df, card=selected_card)
        st.plotly_chart(cage_fig, use_container_width=True)

        render_stock_conviction_card(selected_card, show_copy_ticket=True)

        st.markdown(
            f"<h4 style='color:{TEXT_PRIMARY};font-size:1.05rem;margin-top:18px;margin-bottom:8px;'>"
            "📋 Active Positions Telemetry Table</h4>",
            unsafe_allow_html=True,
        )

        positions_rows = [
            {
                "Ticker": c.ticker,
                "Index": c.index_id,
                "Status": c.action_type,
                "Shares": c.shares,
                "Entry $": round(c.entry_price, 2),
                "Current $": round(c.current_price, 2),
                "Initial Stop $": round(c.initial_stop_price, 2),
                "Active Stop $": round(c.trailing_stop_price, 2),
                "Target (+3R) $": round(c.take_profit_price, 2),
                "Open Risk $": round(c.open_dollar_risk, 2),
                "Unrealized P&L $": round(c.unrealized_pnl_dollars, 2),
                "Unrealized R": round(c.unrealized_r_multiple, 2),
                "500d Win Rate %": round(c.historical_win_rate_pct, 1),
                "EV (R)": round(c.historical_ev_r_multiple, 2),
                "Days Held": f"{c.bars_held} / {c.max_holding_bars}",
            }
            for c in snapshot.active_conviction_cards
        ]
        st.dataframe(
            pd.DataFrame(positions_rows),
            use_container_width=True,
            hide_index=True,
        )


# =============================================================================
# 8. VIEW 3: TRACK RECORD & AUDIT LAB
# =============================================================================

elif active_view == "📈 Track Record & Audit Lab":
    st.markdown(
        f"""
        <div style="margin-top:8px;margin-bottom:14px;">
            <h2 style="margin:0;font-size:1.35rem;font-weight:700;color:{TEXT_PRIMARY};">
                📈 Track Record &amp; Non-Repudiation Audit Lab
            </h2>
            <p style="margin:4px 0 0 0;font-size:0.85rem;color:{TEXT_MUTED};">
                Immutable Triple-Barrier exit attribution, cumulative equity growth, and realized R-Multiple payoff distribution.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    perf = snapshot.performance_summary
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Closed Trades", f"{int(perf.get('total_trades', 0))}")
    m2.metric("Realized Win Rate", f"{perf.get('win_rate_pct', 0.0):.1f}%")
    m3.metric("Avg Expectancy (R)", f"{perf.get('avg_r_multiple', 0.0):+.2f} R")
    m4.metric("Profit Factor", f"{perf.get('profit_factor', 0.0):.2f}x")
    m5.metric("Net Realized P&L", f"${perf.get('total_realized_pnl', 0.0):,.2f}")

    eq_fig, r_fig = build_performance_charts(
        closed_trades=snapshot.ledger.closed_trades_audit,
        initial_capital=float(st.session_state["custom_equity"]),
    )

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.plotly_chart(eq_fig, use_container_width=True)
    with chart_col2:
        st.plotly_chart(r_fig, use_container_width=True)

    st.markdown(
        f"<h4 style='color:{TEXT_PRIMARY};font-size:1.05rem;margin-top:14px;margin-bottom:8px;'>"
        "📜 Closed Trades Audit Ledger</h4>",
        unsafe_allow_html=True,
    )

    closed_list = snapshot.ledger.closed_trades_audit
    if selected_tier == "FREE":
        closed_list = closed_list[-10:]

    if not closed_list:
        st.info(
            "No closed trades recorded in this portfolio yet. Switch to '🧪 Interactive Sandbox Demo' in the sidebar to explore 12 historical Triple-Barrier audit records."
        )
    else:
        reason_filter = st.multiselect(
            "Filter by Exit Barrier Trigger",
            options=[r.value for r in ExitReason],
            default=[r.value for r in ExitReason],
        )

        audit_rows = []
        for t in sorted(closed_list, key=lambda x: x.exit_date, reverse=True):
            r_val = t.exit_reason.value if isinstance(t.exit_reason, ExitReason) else str(t.exit_reason)
            if r_val in reason_filter:
                audit_rows.append(
                    {
                        "Ticker": t.ticker,
                        "Index": t.index_id,
                        "Entry Date": t.entry_date.isoformat(),
                        "Exit Date": t.exit_date.isoformat(),
                        "Entry $": round(t.entry_price, 2),
                        "Exit $": round(t.exit_price, 2),
                        "Shares": t.shares,
                        "Bars Held": t.bars_held,
                        "Exit Barrier": r_val,
                        "Realized P&L $": round(t.realized_pnl_dollars, 2),
                        "Realized R": round(t.realized_r_multiple, 2),
                    }
                )

        audit_df = pd.DataFrame(audit_rows)
        st.dataframe(audit_df, use_container_width=True, hide_index=True)

        if selected_tier in ("PRO", "ELITE") and not audit_df.empty:
            csv_bytes = audit_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Export Closed Trade Audit Ledger (CSV)",
                data=csv_bytes,
                file_name=f"swing_quant_audit_{snapshot.ledger.as_of_date.isoformat()}.csv",
                mime="text/csv",
            )
        elif selected_tier == "FREE":
            st.caption("🔒 Full CSV/JSON audit export is enabled for PRO and ELITE subscribers.")


# =============================================================================
# 9. VIEW 4: CONTROL ROOM & SETTINGS
# =============================================================================

elif active_view == "⚙️ Control Room & Settings":
    st.markdown(
        f"""
        <div style="margin-top:8px;margin-bottom:14px;">
            <h2 style="margin:0;font-size:1.35rem;font-weight:700;color:{TEXT_PRIMARY};">
                ⚙️ Multi-Tenant Control Room &amp; Risk Governance
            </h2>
            <p style="margin:4px 0 0 0;font-size:0.85rem;color:{TEXT_MUTED};">
                Configure subscribed market indices and Portfolio Heat boundaries within Jim Simons' hard 6.00% risk cap.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("tenant_settings_form"):
        st.markdown(
            f"<h4 style='color:{TEXT_PRIMARY};font-size:1.0rem;margin-bottom:6px;'>"
            "1. Subscribed Market Indices</h4>",
            unsafe_allow_html=True,
        )

        current_subs = set(snapshot.ledger.subscribed_indices)
        idx_c1, idx_c2, idx_c3 = st.columns(3)

        with idx_c1:
            sub_rut = st.checkbox(
                "RUT_2000 — Russell 2000 Small-Cap",
                value=("RUT_2000" in current_subs),
            )
        with idx_c2:
            sub_sp400 = st.checkbox(
                "SP_400 — S&P MidCap 400",
                value=("SP_400" in current_subs),
            )
        with idx_c3:
            sub_sp500 = st.checkbox(
                "SP_500 — S&P 500 Large-Cap (ELITE)",
                value=("SP_500" in current_subs),
                disabled=(selected_tier != "ELITE"),
            )

        st.markdown(
            f"<h4 style='color:{TEXT_PRIMARY};font-size:1.0rem;margin-top:16px;margin-bottom:6px;'>"
            "2. Simons Portfolio Heat Ceiling (2.0% – 6.0% Hard Cap)</h4>",
            unsafe_allow_html=True,
        )

        current_max_heat_pct = round(snapshot.ledger.max_portfolio_heat_pct * 100.0, 2)
        new_max_heat_pct = st.slider(
            "Maximum Open Portfolio Heat (%)",
            min_value=2.0,
            max_value=6.0,
            value=min(6.0, max(2.0, current_max_heat_pct)),
            step=0.25,
            disabled=(selected_tier != "ELITE"),
            help="Configurable for ELITE tier between 2.00% and the hard 6.00% Simons ceiling.",
        )

        submitted = st.form_submit_button(
            "💾 Save Portfolio Risk & Index Preferences",
            type="primary",
        )

        if submitted:
            chosen_indices: List[str] = []
            if sub_rut:
                chosen_indices.append("RUT_2000")
            if sub_sp400:
                chosen_indices.append("SP_400")
            if sub_sp500 and selected_tier == "ELITE":
                chosen_indices.append("SP_500")

            if not chosen_indices:
                st.error("At least one market index (e.g., RUT_2000 or SP_400) must be selected.")
            elif selected_tier == "FREE":
                st.warning("Explorer (FREE) tier is read-only. Switch to PRO or ELITE in the sidebar to save preferences.")
            elif snapshot.is_demo_mode:
                st.session_state["demo_subscribed_indices"] = chosen_indices
                st.session_state["demo_max_heat_pct"] = round(new_max_heat_pct / 100.0, 4)
                st.success(
                    f"Updated Sandbox Demo preferences in memory: Indices={chosen_indices}, Max Heat={new_max_heat_pct:.2f}%."
                )
                st.rerun()
            else:
                try:
                    updated_ledger = data_service.update_tenant_preferences(
                        portfolio_id=snapshot.ledger.portfolio_id,
                        user_claims=user_claims,
                        subscribed_indices=chosen_indices,
                        max_heat_pct=round(new_max_heat_pct / 100.0, 4),
                    )
                    st.success(
                        f"Persisted live production settings atomically: Indices={updated_ledger.subscribed_indices}, "
                        f"Max Portfolio Heat={updated_ledger.max_portfolio_heat_pct * 100.0:.2f}%."
                    )
                    st.rerun()
                except Exception as save_exc:
                    st.error(f"Failed to update portfolio preferences: {save_exc}")

    st.markdown(
        f"<h4 style='color:{TEXT_PRIMARY};font-size:1.05rem;margin-top:18px;margin-bottom:8px;'>"
        "📐 Registered Index Triple-Barrier &amp; Liquidity Parameters</h4>",
        unsafe_allow_html=True,
    )

    registry_rows = [
        {
            "Index ID": cfg.index_id,
            "Display Name": cfg.display_name,
            "Benchmark ETF": cfg.benchmark_ticker,
            "Tier": cfg.tier.value,
            "Min Price ($)": cfg.min_price,
            "Min 30d ADV": f"{cfg.min_adv_30d:,}",
            "Stop ATR (k_stop)": f"{cfg.k_stop_atr:.2f}x",
            "Target ATR (k_profit)": f"{cfg.k_profit_atr:.2f}x",
            "Max Time Barrier": f"{cfg.max_holding_bars} Days",
        }
        for cfg in snapshot.available_indices.values()
    ]
    st.dataframe(pd.DataFrame(registry_rows), use_container_width=True, hide_index=True)

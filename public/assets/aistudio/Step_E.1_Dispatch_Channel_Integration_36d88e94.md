# Step E.1: Dispatch Channel Integration Specification (Telegram Bot API)

## 1. Architectural Overview & Executive Telemetry Philosophy

The **Dispatch Channel Integration Layer** (`src/notifier.py`) serves as the outbound telemetry and executive audit interface of the **Swing Quant Engine**. Operating downstream from the Quant Engine Logic Layer (Step C.2) and Atomic State Repository (Step D.1), this module formats and dispatches End-of-Day (EOD) portfolio updates, **Triple-Barrier** liquidations, **Chandelier Ratchet** trailing stop adjustments, and newly allocated **Meta-Labeled** entries to isolated Telegram channels.

In strict adherence to **Jim Simons' Zero-Override Policy** (*Renaissance Technologies*), the dispatch layer is strictly a **read-only telemetry sink**:
1. **State Precedes Telemetry:** The Multi-Tenant Portfolio Ledger (`virtual_portfolio.json` or PostgreSQL) is committed atomically *before* any outbound network call to Telegram is attempted.
2. **Non-Blocking Fail-Safe:** External messaging outages, HTTP 5xx errors, or Telegram rate limits (`HTTP 429`) are handled via exponential backoff and logged cleanly without corrupting or rolling back the completed quantitative state transition.
3. **HTML Parse Mode Stability:** Rather than using Telegram's fragile `MarkdownV2` parser (which frequently fails on unescaped `.`, `-`, or `+` characters in ticker symbols like `BRK-B` or floating-point $R$-multiples), all payloads are rendered in strict, sanitized **Telegram HTML** (`parse_mode="HTML"`).

```
+-------------------------------------------------------------------------+
|        Completed Daily Quant Cycle & Atomic State Commit (Step D.1)     |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               Per-Tenant Telemetry Routing (`portfolio_id`)             |
|    - Resolves Tenant-Specific `chat_id` (or Default Admin Channel)      |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               HTML Executive Report Builder (`notifier.py`)             |
|  1. Portfolio Health: Equity, Cash, Open Slots, Portfolio Heat (<=6%)   |
|  2. Triple-Barrier Exits: TP / SL / 14d Time-Stop + Realized R-Multiple |
|  3. Chandelier Ratchet Updates: Locked-in Trailing Stop Advances        |
|  4. New Meta-Labeled Entries: Conviction Scalar, Shares & Barrier Cage  |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|            HTML-Safe Smart Chunker (<= 4,000 Chars per Payload)         |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|        Resilient Telegram HTTP Dispatcher (Exponential Backoff)         |
|          - Handles HTTP 429 `retry_after` & Transient 5xx Errors        |
+-------------------------------------------------------------------------+
```

---

## 2. Executive Report Structure & Quantitative Telemetry Fields

Every daily EOD dispatch is organized into five deterministic sections:

1. **Header & Tenant Scope:** Displays the portfolio name, `as_of_date`, and execution mode (`LIVE EOD LEDGER` vs. `SANDBOX DRY-RUN`).
2. **Executive Portfolio Summary:**
   * **Total Equity ($E_{\text{total}}$)** and **Available Cash ($C_{\text{avail}}$)**.
   * **Active Capacity:** Open positions count relative to $N_{\max} = 10$.
   * **Simons Portfolio Heat ($H_{\text{portfolio}}$):** Aggregate open downside risk to current trailing stops relative to the $6.00\%$ circuit breaker cap.
3. **Triple-Barrier Liquidations (Closed Today):** Lists every position closed during today's session, specifying the exact barrier triggered (`UPPER_BARRIER_TP`, `LOWER_BARRIER_SL`, or `VERTICAL_BARRIER_TIME`), realized PnL in dollars, and realized payoff in $R$-multiples.
4. **New Meta-Labeled Allocations (Opened Today):** Details new swing entries, including parent index (`RUT_2000`, `SP_400`), allocated shares, entry price, initial stop ($k_{\text{stop}} \times \text{ATR}_{14}$), take-profit target ($k_{\text{profit}} \times \text{ATR}_{14}$), and vertical time barrier ($14\text{ days}$).
5. **Active Open Positions & Chandelier Ratchet Book:** Summarizes all surviving positions, their current ratcheted trailing stop, days held ($t / 14$), and remaining open dollar risk.

---

## 3. Production Python Implementation (`src/notifier.py`)

```python
from datetime import date
import html
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID

import requests

from config import EngineSettings
from schemas import (
    ClosedTradeAuditSchema,
    ExitReason,
    MetaLabeledSignalSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)

logger = logging.getLogger("SwingQuantEngine.Notifier")


class TelegramDispatchService:
    """
    Resilient, multi-tenant HTML telemetry dispatcher for the Telegram Bot API.
    Enforces HTML entity escaping, line-aware 4096-character chunking,
    HTTP 429 rate-limit adherence, and non-blocking fail-safe execution.
    """

    TELEGRAM_API_BASE = "https://api.telegram.org"
    MAX_MESSAGE_LENGTH = 4000  # Safety margin below Telegram's hard 4096-char ceiling

    def __init__(
        self,
        settings: EngineSettings,
        max_retries: int = 3,
        base_backoff_sec: float = 2.0,
        request_timeout_sec: float = 10.0,
    ) -> None:
        self.settings = settings
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.request_timeout_sec = request_timeout_sec

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.telegram_bot_token is not None
            and self.settings.telegram_chat_id is not None
            and self.settings.telegram_bot_token.get_secret_value().strip()
            and self.settings.telegram_chat_id.get_secret_value().strip()
        )

    # =========================================================================
    # 1. PUBLIC TELEMETRY DISPATCH ENTRYPOINTS
    # =========================================================================

    def dispatch_tenant_daily_report(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        opened_positions: List[TripleBarrierPositionSchema],
        closed_trades: List[ClosedTradeAuditSchema],
        approved_signals: List[MetaLabeledSignalSchema],
        as_of_date: date,
        dry_run: bool = False,
        tenant_chat_id_override: Optional[str] = None,
    ) -> bool:
        """
        Formats and dispatches the daily EOD executive report for a single isolated
        tenant portfolio. Never raises unhandled exceptions to callers.
        """
        if not self.is_configured and not tenant_chat_id_override:
            logger.warning(
                "Telegram credentials not configured; skipping EOD telemetry dispatch."
            )
            return False

        target_chat_id = (
            tenant_chat_id_override
            if tenant_chat_id_override
            else self.settings.telegram_chat_id.get_secret_value()  # type: ignore[union-attr]
        )

        report_html = self.format_daily_portfolio_report_html(
            portfolio=portfolio,
            opened_positions=opened_positions,
            closed_trades=closed_trades,
            approved_signals=approved_signals,
            as_of_date=as_of_date,
            dry_run=dry_run,
        )

        chunks = self._chunk_html_message(report_html)
        all_succeeded = True

        for idx, chunk in enumerate(chunks, start=1):
            header_prefix = (
                f"<i>[Part {idx}/{len(chunks)}]</i>\n" if len(chunks) > 1 else ""
            )
            ok = self._send_html_payload(
                chat_id=target_chat_id,
                text=f"{header_prefix}{chunk}",
            )
            if not ok:
                all_succeeded = False

        return all_succeeded

    def dispatch_system_circuit_breaker_alert(
        self,
        stage: str,
        error_summary: str,
        as_of_date: Optional[date] = None,
    ) -> bool:
        """
        Dispatches an urgent operational alert if a pre-flight gate or data sync
        encounters a critical anomaly.
        """
        if not self.is_configured:
            return False

        target_chat_id = self.settings.telegram_chat_id.get_secret_value()  # type: ignore[union-attr]
        dt_str = as_of_date.isoformat() if as_of_date else "N/A"
        safe_stage = html.escape(stage)
        safe_err = html.escape(error_summary[:1200])

        alert_html = (
            f"🚨 <b>CRITICAL: SWING QUANT ENGINE CIRCUIT BREAKER</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Date:</b> <code>{dt_str}</code>\n"
            f"<b>Failed Stage:</b> <code>{safe_stage}</code>\n"
            f"<b>Error Detail:</b>\n<pre>{safe_err}</pre>\n"
            f"<i>Zero-Override Protection: Portfolio state was left untouched.</i>"
        )
        return self._send_html_payload(chat_id=target_chat_id, text=alert_html)

    # =========================================================================
    # 2. DETERMINISTIC HTML REPORT FORMATTER
    # =========================================================================

    def format_daily_portfolio_report_html(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        opened_positions: List[TripleBarrierPositionSchema],
        closed_trades: List[ClosedTradeAuditSchema],
        approved_signals: List[MetaLabeledSignalSchema],
        as_of_date: date,
        dry_run: bool = False,
    ) -> str:
        mode_badge = "🧪 SANDBOX DRY-RUN" if dry_run else "⚡ EOD PRODUCTION LEDGER"
        safe_name = html.escape(portfolio.portfolio_name)
        heat_pct = portfolio.current_portfolio_heat_pct * 100.0
        max_heat_pct = portfolio.max_portfolio_heat_pct * 100.0

        lines: List[str] = [
            f"🏛️ <b>SWING QUANT ENGINE | {mode_badge}</b>",
            f"<b>Portfolio:</b> {safe_name} (<code>{str(portfolio.portfolio_id)[:8]}</code>)",
            f"<b>Market Date:</b> <code>{as_of_date.isoformat()}</code>",
            "━━━━━━━━━━━━━━━━━━",
            "📊 <b>EXECUTIVE PORTFOLIO TELEMETRY</b>",
            f"• <b>Total Equity:</b> <code>${portfolio.total_equity:,.2f}</code>",
            f"• <b>Cash Balance:</b> <code>${portfolio.cash_balance:,.2f}</code>",
            f"• <b>Active Capacity:</b> <code>{len(portfolio.open_positions)} / {portfolio.max_concurrent_positions} Slots</code>",
            f"• <b>Portfolio Heat:</b> <code>{heat_pct:.2f}% / {max_heat_pct:.2f}% Max</code>",
            "━━━━━━━━━━━━━━━━━━",
        ]

        # Section A: Triple-Barrier Liquidations (Exits Executed Today)
        lines.append(f"🎯 <b>TRIPLE-BARRIER EXITS ({len(closed_trades)})</b>")
        if not closed_trades:
            lines.append("<i>No barrier exits triggered during today's session.</i>")
        else:
            for trade in closed_trades:
                badge = self._format_exit_reason_badge(trade.exit_reason)
                pnl_sign = "+" if trade.realized_pnl_dollars >= 0 else ""
                r_sign = "+" if trade.realized_r_multiple >= 0 else ""
                lines.append(
                    f"• <b>{html.escape(trade.ticker)}</b> [{html.escape(trade.index_id)}] — {badge}\n"
                    f"  Exit: <code>${trade.exit_price:,.2f}</code> (Entry: <code>${trade.entry_price:,.2f}</code> | Held: <code>{trade.bars_held}d</code>)\n"
                    f"  Realized: <code>{pnl_sign}${trade.realized_pnl_dollars:,.2f}</code> (<b>{r_sign}{trade.realized_r_multiple:.2f}R</b>)"
                )
        lines.append("━━━━━━━━━━━━━━━━━━")

        # Section B: Newly Allocated Meta-Labeled Positions
        lines.append(f"🚀 <b>NEW META-LABELED ENTRIES ({len(opened_positions)})</b>")
        if not opened_positions:
            lines.append("<i>No new positions allocated (filtered by Meta-Labeling or Heat Gate).</i>")
        else:
            sig_lookup: Dict[str, MetaLabeledSignalSchema] = {
                s.primary_signal.ticker: s for s in approved_signals
            }
            for pos in opened_positions:
                meta_info = sig_lookup.get(pos.ticker)
                score_str = (
                    f"Score: {meta_info.primary_signal.primary_score:.1f} | "
                    f"φ: {meta_info.meta_conviction_scalar:.2f}x | "
                    f"EV: +{meta_info.historical_ev_r_multiple:.2f}R"
                    if meta_info
                    else "Meta-Validated"
                )
                notional = pos.shares * pos.entry_price
                lines.append(
                    f"• <b>{html.escape(pos.ticker)}</b> [{html.escape(pos.index_id)}] — <code>{pos.shares} sh</code> @ <code>${pos.entry_price:,.2f}</code> (<code>${notional:,.0f}</code>)\n"
                    f"  <i>{score_str}</i>\n"
                    f"  Cage: SL <code>${pos.initial_stop_price:,.2f}</code> | TP <code>${pos.take_profit_price:,.2f}</code> | Max <code>{pos.max_holding_bars}d</code>"
                )
        lines.append("━━━━━━━━━━━━━━━━━━")

        # Section C: Active Open Book & Ratchet Trailing Stops
        lines.append(f"🛡️ <b>ACTIVE TRIPLE-BARRIER BOOK ({len(portfolio.open_positions)})</b>")
        if not portfolio.open_positions:
            lines.append("<i>Portfolio is currently 100% in cash.</i>")
        else:
            for ticker, pos in sorted(portfolio.open_positions.items()):
                locked_profit_flag = (
                    "🔒 <i>(Risk-Free / Stop >= Entry)</i>"
                    if pos.trailing_stop_price >= pos.entry_price
                    else f"Open Risk: <code>${pos.open_dollar_risk:,.0f}</code>"
                )
                lines.append(
                    f"• <b>{html.escape(ticker)}</b> (<code>{pos.bars_held}/{pos.max_holding_bars}d</code>) — "
                    f"Entry: <code>${pos.entry_price:,.2f}</code> | "
                    f"Ratchet SL: <code>${pos.trailing_stop_price:,.2f}</code> | "
                    f"TP: <code>${pos.take_profit_price:,.2f}</code> | {locked_profit_flag}"
                )

        return "\n".join(lines)

    @staticmethod
    def _format_exit_reason_badge(reason: ExitReason) -> str:
        if reason == ExitReason.UPPER_BARRIER_TP:
            return "✅ <b>TAKE-PROFIT BARRIER</b>"
        if reason == ExitReason.LOWER_BARRIER_SL:
            return "🛑 <b>TRAILING STOP BARRIER</b>"
        if reason == ExitReason.VERTICAL_BARRIER_TIME:
            return "⏱️ <b>14-DAY TIME BARRIER</b>"
        return "⚠️ <b>CIRCUIT BREAKER EXIT</b>"

    # =========================================================================
    # 3. LINE-AWARE HTML CHUNKING & EXPONENTIAL BACKOFF HTTP CLIENT
    # =========================================================================

    def _chunk_html_message(self, html_text: str) -> List[str]:
        """
        Splits long HTML reports on newline boundaries so individual payloads
        never exceed Telegram's 4096-character limit or sever HTML tags mid-line.
        """
        if len(html_text) <= self.MAX_MESSAGE_LENGTH:
            return [html_text]

        chunks: List[str] = []
        current_lines: List[str] = []
        current_len = 0

        for line in html_text.split("\n"):
            line_len = len(line) + 1
            if current_len + line_len > self.MAX_MESSAGE_LENGTH and current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = [line]
                current_len = line_len
            else:
                current_lines.append(line)
                current_len += line_len

        if current_lines:
            chunks.append("\n".join(current_lines))

        return chunks

    def _send_html_payload(self, chat_id: str, text: str) -> bool:
        token = self.settings.telegram_bot_token.get_secret_value()  # type: ignore[union-attr]
        url = f"{self.TELEGRAM_API_BASE}/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.request_timeout_sec,
                )
                if response.status_code == 200:
                    return True

                # Handle Telegram HTTP 429 Too Many Requests rate-limiting
                if response.status_code == 429:
                    retry_after = int(
                        response.json()
                        .get("parameters", {})
                        .get("retry_after", self.base_backoff_sec ** attempt)
                    )
                    logger.warning(
                        f"Telegram API rate limit hit (HTTP 429). Waiting {retry_after}s before retry..."
                    )
                    time.sleep(retry_after)
                    continue

                logger.warning(
                    f"Telegram API returned HTTP {response.status_code} "
                    f"(Attempt {attempt}/{self.max_retries}): {response.text[:200]}"
                )
            except requests.RequestException as exc:
                logger.warning(
                    f"Telegram network transport error (Attempt {attempt}/{self.max_retries}): {exc}"
                )

            if attempt < self.max_retries:
                time.sleep(self.base_backoff_sec ** attempt)

        logger.error("Exhausted all Telegram dispatch retries. Continuing without crashing.")
        return False
```

---

## 4. Wiring `TelegramDispatchService` into `src/main.py`

In `src/main.py` (defined in Step D.1), after `repo.save_state_atomically(state_store)` commits the updated ledger, the orchestrator invokes the dispatch service for each tenant portfolio:

```python
    # 6. Dispatch EOD Executive Telemetry to Telegram (Non-Blocking)
    notifier = TelegramDispatchService(settings=settings)
    for portfolio_id, telemetry in dispatch_telemetry.items():
        tenant_portfolio = state_store.tenant_portfolios[portfolio_id]
        notifier.dispatch_tenant_daily_report(
            portfolio=tenant_portfolio,
            opened_positions=telemetry["opened_positions"],
            closed_trades=telemetry["closed_trades"],
            approved_signals=telemetry["approved_signals"],
            as_of_date=target_date,
            dry_run=args.dry_run,
        )
```

---

## 5. Sample Rendered Telegram Output

```text
🏛️ SWING QUANT ENGINE | ⚡ EOD PRODUCTION LEDGER
Portfolio: Primary Swing Shadow Portfolio (00000000)
Market Date: 2026-11-11
━━━━━━━━━━━━━━━━━━
📊 EXECUTIVE PORTFOLIO TELEMETRY
• Total Equity: $104,820.50
• Cash Balance: $62,140.50
• Active Capacity: 4 / 10 Slots
• Portfolio Heat: 3.12% / 6.00% Max
━━━━━━━━━━━━━━━━━━
🎯 TRIPLE-BARRIER EXITS (1)
• CRS [SP_400] — ✅ TAKE-PROFIT BARRIER
  Exit: $178.40 (Entry: $159.20 | Held: 9d)
  Realized: +$1,920.00 (+2.25R)
━━━━━━━━━━━━━━━━━━
🚀 NEW META-LABELED ENTRIES (1)
• FN [RUT_2000] — 45 sh @ $214.50 ($9,652)
  Score: 86.4 | φ: 1.25x | EV: +0.68R
  Cage: SL $198.10 | TP $247.30 | Max 14d
━━━━━━━━━━━━━━━━━━
🛡️ ACTIVE TRIPLE-BARRIER BOOK (4)
• ANF (6/14d) — Entry: $148.00 | Ratchet SL: $151.20 | TP: $172.00 | 🔒 (Risk-Free / Stop >= Entry)
• FN (0/14d) — Entry: $214.50 | Ratchet SL: $198.10 | TP: $247.30 | Open Risk: $738
```
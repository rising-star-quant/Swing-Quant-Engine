from __future__ import annotations

from datetime import date
import html
import logging
import time
from typing import Dict, List, Optional

import httpx

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
    Resilient, multi-tenant HTML telemetry dispatcher for the Telegram Bot API
    built on httpx. Enforces HTML entity escaping, line-aware 4,096-character
    smart chunking, HTTP 429 exponential backoff, and multi-tenant chat routing.
    """

    TELEGRAM_API_BASE = "https://api.telegram.org"
    MAX_MESSAGE_LENGTH = 4000

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
            f"<b>Tenant User:</b> <code>{str(portfolio.user_id)[:8]}</code>",
            f"<b>Market Date:</b> <code>{as_of_date.isoformat()}</code>",
            "━━━━━━━━━━━━━━━━━━",
            "📊 <b>EXECUTIVE PORTFOLIO TELEMETRY</b>",
            f"• <b>Total Equity:</b> <code>${portfolio.total_equity:,.2f}</code>",
            f"• <b>Cash Balance:</b> <code>${portfolio.cash_balance:,.2f}</code>",
            f"• <b>Active Capacity:</b> <code>{len(portfolio.open_positions)} / {portfolio.max_concurrent_positions} Slots</code>",
            f"• <b>Portfolio Heat:</b> <code>{heat_pct:.2f}% / {max_heat_pct:.2f}% Max</code>",
            "━━━━━━━━━━━━━━━━━━",
        ]

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

    def _chunk_html_message(self, html_text: str) -> List[str]:
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

        with httpx.Client(timeout=self.request_timeout_sec) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = client.post(url, json=payload)
                    if response.status_code == 200:
                        return True

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
                except httpx.HTTPError as exc:
                    logger.warning(
                        f"Telegram network transport error (Attempt {attempt}/{self.max_retries}): {exc}"
                    )

                if attempt < self.max_retries:
                    time.sleep(self.base_backoff_sec ** attempt)

        logger.error("Exhausted all Telegram dispatch retries. Continuing without crashing.")
        return False

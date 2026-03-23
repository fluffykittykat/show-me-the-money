"""
Insider Timing Analyzer — Stock Trade Timing vs Committee Activity
Analyzes the timing of congressional stock trades relative to committee hearings and votes.
Currently works with seed data. Will integrate with real eFD + Congress.gov data later.
"""
import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Scoring weights
TIMING_THRESHOLDS = {
    "critical": 7,    # days - trade within 7 days of hearing
    "high": 14,        # days
    "moderate": 30,    # days
    "low": 60,         # days
}


class InsiderTimingAnalyzer:
    """Analyzes stock trade timing relative to committee activity and information access."""

    def calculate_information_access_score(self, trade: dict[str, Any]) -> int:
        """
        Score 1-10 based on:
        - How close the trade was to a committee hearing (0-4 points)
        - Whether the trade direction aligned with the outcome (0-3 points)
        - Whether the official sits on a relevant committee (0-2 points)
        - Whether there's a pattern of similar trades (0-1 points)
        """
        score = 0

        days_before = trade.get("days_before_committee_hearing")
        if days_before is not None:
            if days_before <= TIMING_THRESHOLDS["critical"]:
                score += 4
            elif days_before <= TIMING_THRESHOLDS["high"]:
                score += 3
            elif days_before <= TIMING_THRESHOLDS["moderate"]:
                score += 2
            elif days_before <= TIMING_THRESHOLDS["low"]:
                score += 1

        # Trade direction alignment
        movement = trade.get("stock_movement_after", "")
        tx_type = trade.get("transaction_type", "")
        if movement:
            pct = float(movement.replace("%", "").replace("+", ""))
            if (tx_type == "sell" and pct < 0) or (tx_type == "buy" and pct > 0):
                score += 3  # Trade aligned with outcome
            elif (tx_type == "sell" and pct > 0) or (tx_type == "buy" and pct < 0):
                score += 0  # Trade went against outcome (bad timing)

        # Committee relevance (assume relevant if hearing data exists)
        if trade.get("hearing_topic"):
            score += 2

        # Pattern bonus
        if trade.get("pattern_flag") in ("TRADE_BEFORE_HEARING", "BUY_BEFORE_FAVORABLE"):
            score += 1

        return min(score, 10)

    def analyze_trades(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze a list of trades and return summary statistics."""
        if not trades:
            return {"total_trades_analyzed": 0, "trades_within_30_days_of_hearing": 0}

        within_30 = sum(1 for t in trades if (t.get("days_before_committee_hearing") or 999) <= 30)
        favorable = sum(
            1 for t in trades if t.get("pattern_flag") in ("TRADE_BEFORE_HEARING", "BUY_BEFORE_FAVORABLE")
        )
        unfavorable = sum(1 for t in trades if t.get("pattern_flag") == "TRADE_AGAINST_OUTCOME")

        scores = [self.calculate_information_access_score(t) for t in trades]
        avg_score = sum(scores) / len(scores) if scores else 0

        return {
            "total_trades_analyzed": len(trades),
            "trades_within_30_days_of_hearing": within_30,
            "trades_before_favorable_outcome": favorable,
            "trades_before_unfavorable_outcome": unfavorable,
            "average_information_access_score": round(avg_score, 1),
            "overall_pattern": self._describe_pattern(len(trades), within_30, favorable),
            "why_this_matters": self._generate_why_it_matters(len(trades), within_30, favorable, avg_score),
        }

    def _describe_pattern(self, total: int, within_30: int, favorable: int) -> str:
        ratio = within_30 / total if total > 0 else 0
        if ratio >= 0.5:
            return (
                f"{within_30} of {total} stock trades occurred within 30 days of a related "
                f"committee hearing. In {favorable} cases, the trade direction aligned with "
                f"the outcome that would benefit the senator financially. This pattern is "
                f"stronger than random chance would predict."
            )
        elif ratio >= 0.25:
            return (
                f"{within_30} of {total} trades were near committee activity. Some timing "
                f"correlation exists but isn't overwhelming."
            )
        return f"Only {within_30} of {total} trades were near committee activity. No strong pattern detected."

    def _generate_why_it_matters(self, total: int, within_30: int, favorable: int, avg_score: float) -> str:
        if avg_score >= 7:
            return (
                "Members of Congress trade stocks while having access to information that "
                "regular investors don't. This senator's trades show a clear pattern: they "
                "consistently happen right before their own committee takes action on related "
                "issues. Each trade alone could be a coincidence. But when you see the same "
                "pattern over and over — selling before bad news, buying before good news — "
                "it raises a question that deserves an answer."
            )
        elif avg_score >= 4:
            return (
                "Some of this senator's stock trades happened suspiciously close to committee "
                "activity on related topics. It's not a smoking gun, but it's enough to raise "
                "eyebrows. Members of Congress have access to non-public briefings and advance "
                "knowledge of upcoming hearings — information that regular investors would pay "
                "a fortune for."
            )
        return (
            "This senator's trading pattern doesn't show strong evidence of suspicious timing. "
            "The trades don't consistently align with committee activity. That said, any "
            "stock trading by officials who regulate those industries is worth monitoring."
        )

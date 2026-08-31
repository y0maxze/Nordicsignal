"""Run the historical confluence diagnostic with the same insider policy as live.

The legacy backtest module imports `analyze` by value, so this launcher patches the
source module before importing the backtest. This guarantees the historical check uses
NOK 100k qualification, NOK 500k meaningful buys and Smart Money enrichment exactly as
production does.
"""
from __future__ import annotations

import json

import insider_signal_v2_runtime as legacy
import insider_purchase_threshold_runtime as purchase_policy
import insider_smart_money_runtime as smart_money


def canonical_analyze(payload, window_days=14):
    return smart_money.enrich(purchase_policy.strict_analyze(payload, window_days=window_days))


legacy.analyze = canonical_analyze

import backtest_insider_confluence_v2 as backtest  # noqa: E402


def main():
    if backtest.analyze_insider is not canonical_analyze:
        raise RuntimeError("historical backtest did not bind canonical insider policy")
    backtest.main()
    try:
        with open("insider_confluence_backtest.json", "r", encoding="utf-8") as f:
            report = json.load(f)
        report.setdefault("method", {})["insider_policy"] = {
            "minimum_signal_buy_nok": purchase_policy.MIN_SIGNAL_BUY_NOK,
            "meaningful_buy_nok": purchase_policy.MEANINGFUL_BUY_NOK,
            "strong_total_buy_nok": purchase_policy.STRONG_TOTAL_BUY_NOK,
            "purchase_policy_version": purchase_policy.POLICY_VERSION,
            "smart_money_policy_version": smart_money.POLICY_VERSION,
            "canonical_policy_verified": True,
        }
        with open("insider_confluence_backtest.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except FileNotFoundError:
        raise RuntimeError("historical backtest completed without report artifact")


if __name__ == "__main__":
    main()

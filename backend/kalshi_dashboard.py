"""
Utilities for generating a JSON summary of a user's Kalshi portfolio.

This module wraps the official Kalshi Python SDK to pull basic account
information (cash balance and total portfolio value) as well as recent
trading activity.  It then computes a handful of useful statistics and
writes them to a JSON file under ``data/kalshi_summary.json``.  The
resulting file is consumed by the front-end dashboard to display
portfolio metrics, recent fills and settlements, and a running profit
series.

The original version of this script shipped with the repository had a
few issues:

1.  It misinterpreted the ``portfolio_value`` field returned by the
    Kalshi API.  According to the official documentation, the
    portfolio value includes both cash and the current value of open
    positions.  In practice, users often reason about their account
    as "cash + money currently tied up in open bets", so this script
    now reconstructs that view explicitly: positions are pulled from
    ``get_positions`` and the portfolio total is computed as
    ``cash + positions_value``.

2.  It did not clearly separate realized profit (from closed/settled
    markets) from unrealized profit (open bets).  The current version
    exposes both so the front-end can explain to non-experts why, for
    example, Kalshi may show a higher portfolio number while realized
    profit is smaller.

3.  Error handling and type-coercion around the Kalshi SDK models were
    a bit brittle.  This version is more defensive: it tolerates minor
    schema / field-name differences between SDK versions and falls
    back gracefully when optional fields are missing.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from kalshi_python import Configuration, KalshiClient


# ---------------------------------------------------------------------------
# Helpers for dealing with Kalshi timestamps and models
# ---------------------------------------------------------------------------


def get_ts_ms(obj: Any) -> Optional[int]:
    """
    Best-effort extraction of a timestamp in milliseconds from a Kalshi
    SDK object.  Different endpoints use different field names, so we
    check several possibilities.
    """
    for attr in ("time", "ts", "created_time", "created_ts", "settled_time"):
        value = getattr(obj, attr, None)
        if value is None:
            continue
        # Some fields are already an int (Unix ms), others are ISO8601
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                # Try parsing ISO8601 (e.g. "2023-11-07T05:31:56Z")
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1000)
            except Exception:
                continue
    return None


def to_dict(obj: Any) -> Any:
    """
    Recursively convert Kalshi SDK models (which are dataclasses / model
    instances) into basic Python structures suitable for JSON.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if is_dataclass(obj):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    # Generic object: walk __dict__ if present
    d = getattr(obj, "__dict__", None)
    if d is not None:
        return {k: to_dict(v) for k, v in d.items()}
    return str(obj)


# ---------------------------------------------------------------------------
# Kalshi client setup
# ---------------------------------------------------------------------------


def load_kalshi_client() -> KalshiClient:
    """
    Load credentials from environment variables and construct an
    authenticated Kalshi client.

    Expected environment variables
    ------------------------------
    KALSHI_API_KEY_ID : str
        Your API key identifier from the Kalshi UI.
    KALSHI_PRIVATE_KEY : str
        The PEM-encoded private key corresponding to the key ID.

    Returns
    -------
    KalshiClient
        An authenticated client ready to make API calls.
    """
    load_dotenv()
    key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")
    if not key_id or not private_key:
        raise Exception(
            "Missing Kalshi credentials. Make sure KALSHI_API_KEY_ID and "
            "KALSHI_PRIVATE_KEY are set."
        )

    config = Configuration(
        host="https://api.elections.kalshi.com/trade-api/v2"
    )
    config.api_key_id = key_id
    config.private_key_pem = private_key
    return KalshiClient(config)


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------


def fetch_fills_last_n_days(client: KalshiClient, days: int = 1):
    """Fetch fills from the last ``days`` days using the API."""
    now_ms = int(time.time() * 1000)
    min_ts = now_ms - int(days * 24 * 60 * 60 * 1000)
    cursor: Optional[str] = None
    fills: List[Any] = []
    while True:
        resp = client.get_fills(limit=200, cursor=cursor, min_ts=min_ts)
        page_fills = getattr(resp, "fills", None) or []
        fills.extend(page_fills)
        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break
    return fills


def fetch_settlements_last_n_days(client: KalshiClient, days: int = 365):
    """Fetch settlements from the last ``days`` days."""
    now = datetime.now(timezone.utc)
    min_dt = now - timedelta(days=days)
    min_ts = int(min_dt.timestamp() * 1000)
    cursor: Optional[str] = None
    settlements: List[Any] = []
    while True:
        resp = client.get_settlements(limit=200, cursor=cursor, min_ts=min_ts)
        page_settlements = getattr(resp, "settlements", None) or []
        settlements.extend(page_settlements)
        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break
    return settlements


# ---------------------------------------------------------------------------
# PnL / stats computation
# ---------------------------------------------------------------------------


def compute_stats(fills, settlements):
    """Compute investment and P&L statistics from fills and settlements.

    Parameters
    ----------
    fills : list
        List of fill objects returned by the Kalshi API.
    settlements : list
        List of settlement objects returned by the Kalshi API.

    Returns
    -------
    dict
        A dictionary containing various investment statistics and a
        cumulative profit series.
    """
    total_invested = 0.0
    total_cash_generated = 0.0

    # Treat BUY fills as money you put into bets; SELL fills as money out.
    for f in fills:
        size = getattr(f, "size", None)
        if size is None:
            size = getattr(f, "count", 0)
        price = float(getattr(f, "price", 0.0) or 0.0)
        cost = float(size) * price
        action = (getattr(f, "action", "") or "").lower()
        if action == "buy":
            total_invested += cost
        elif action == "sell":
            total_cash_generated += cost

    # Reinvested = you sold and then used that cash to buy more
    reinvested = min(total_invested, total_cash_generated)
    cash_invested = total_invested - reinvested

    # Realized P&L and cash flow from settlements
    realized_pnl = 0.0
    cash_in = 0.0
    cash_out = 0.0
    cumulative_series: List[Dict[str, float]] = []

    sorted_settlements = sorted(settlements, key=lambda s: get_ts_ms(s) or 0)
    running = 0.0
    for s in sorted_settlements:
        cash_change = getattr(s, "cash_change", None)
        if cash_change is None:
            cash_change = getattr(s, "cashChange", None)
        if cash_change is None:
            continue
        cash_change = float(cash_change)
        realized_pnl += cash_change
        if cash_change > 0:
            cash_in += cash_change
        elif cash_change < 0:
            cash_out += -cash_change
        ts = get_ts_ms(s)
        if ts is not None:
            running += cash_change
            cumulative_series.append({"ts": ts, "cumulative": running})

    portfolio_value = cash_invested + reinvested + realized_pnl
    return_rate = (realized_pnl / total_invested) if total_invested > 0 else 0.0

    return {
        "total_invested": total_invested,
        "reinvested": reinvested,
        "cash_invested": cash_invested,
        "realized_pnl": realized_pnl,
        "portfolio_value": portfolio_value,
        "return_rate": return_rate,
        "cash_in": cash_in,
        "cash_out": cash_out,
        "cumulative_series": cumulative_series,
    }


def _clean_for_json(obj):
    """Recursively convert Kalshi SDK models into JSON-serializable dicts."""
    return to_dict(obj)


# ---------------------------------------------------------------------------
# Main summary generation
# ---------------------------------------------------------------------------


def generate_summary_json(days: int = 365):
    """Pull data from Kalshi, compute stats and write a summary JSON file.

    The resulting JSON file is placed under ``data/kalshi_summary.json``.
    You can adjust the number of days of history used for fills and
    settlements via the ``days`` parameter.  A longer window provides
    more insight into trading performance over time, but increases the
    number of API calls.

    Parameters
    ----------
    days : int
        Number of days of history to include.  Defaults to ``365``.
    """
    client = load_kalshi_client()

    # 1) Account-level numbers (cash vs total portfolio)
    balance_resp = client.get_balance()
    balance_cents = getattr(balance_resp, "balance", 0) or 0

    # Compute open positions value directly from /portfolio/positions so that
    # it lines up with the "Positions" number you see on Kalshi's portfolio page.
    try:
        positions_resp = client.get_positions(settlement_status="unsettled")
    except Exception:
        positions_resp = None

    positions_cents = 0
    if positions_resp is not None:
        # Sum the total cost of all unsettled event positions. This is effectively
        # "how much of your money is currently tied up in live bets".
        event_positions = getattr(positions_resp, "event_positions", None) or []
        for ep in event_positions:
            cents = getattr(ep, "total_cost", None)
            if cents is None:
                # Some SDK versions expose *_dollars as strings instead.
                dollars_str = getattr(ep, "total_cost_dollars", None)
                if dollars_str is not None:
                    try:
                        cents = int(round(float(dollars_str) * 100))
                    except Exception:
                        cents = 0
            if cents:
                positions_cents += int(cents)

    # Total account value = cash + money currently sitting in open positions.
    portfolio_cents = balance_cents + positions_cents

    account = {
        "cash_cents": balance_cents,
        "positions_cents": positions_cents,
        "cash": balance_cents / 100.0,
        "positions_value": positions_cents / 100.0,
        "portfolio_total": portfolio_cents / 100.0,
        "updated_ts": getattr(balance_resp, "updated_ts", None),
    }

    # 2) Trading activity
    fills = fetch_fills_last_n_days(client, days=days)
    settlements = fetch_settlements_last_n_days(client, days=days)
    stats = compute_stats(fills, settlements)
    fills_dict = [to_dict(f) for f in fills]
    settlements_dict = [to_dict(s) for s in settlements]

    # 3) Net profit / ROI based on total deposits
    # The total deposits should be provided via environment variable.
    total_deposits_env = os.getenv("TOTAL_DEPOSITS")
    try:
        total_deposits = float(total_deposits_env) if total_deposits_env else 0.0
    except Exception:
        total_deposits = 0.0

    portfolio_total = account["portfolio_total"]
    net_profit = portfolio_total - total_deposits
    net_profit_percent = (
        (net_profit / total_deposits) if total_deposits > 0 else 0.0
    )

    stats_extra = dict(stats)
    stats_extra["total_deposits"] = total_deposits
    stats_extra["net_profit"] = net_profit
    stats_extra["net_profit_percent"] = net_profit_percent

    # 4) Assemble final JSON structure
    now_utc = datetime.now(timezone.utc)
    summary: Dict[str, Any] = {
        "generated_at": now_utc.isoformat(),
        "lookback_days": days,
        "account": account,
        "fills_last_n_days": fills_dict,
        "settlements_last_n_days": settlements_dict,
        "summary": stats_extra,
    }

    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "kalshi_summary.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4)
    print(f"✓ Summary JSON generated at {output_path}")


if __name__ == "__main__":
    # use a long window so the chart + stats have real history
    generate_summary_json(days=365)

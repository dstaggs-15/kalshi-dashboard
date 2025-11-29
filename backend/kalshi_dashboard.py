"""
Generate a JSON summary of your Kalshi portfolio for the dashboard.

What this script does:
- Pulls from Kalshi:
    * Cash balance
    * Open positions exposure
    * Fills (trades)
    * Settlements (closed/settled markets)
- Computes:
    * Total deposits (env TOTAL_DEPOSITS, default 40.0)
    * Net profit = portfolio_value - deposits
    * Realized P&L (closed bets)
    * Unrealized P&L (open bets) – but forced to 0 when you have no positions
    * Cumulative P&L series for a chart
- Writes everything to data/kalshi_summary.json for the frontend.
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
# Utility helpers
# ---------------------------------------------------------------------------


def get_ts_ms(obj: Any) -> Optional[int]:
    """
    Extract a timestamp in milliseconds from a Kalshi SDK object.
    Handles several possible field names and formats.
    """
    for attr in ("time", "ts", "created_time", "created_ts", "settled_time"):
        value = getattr(obj, attr, None)
        if value is None:
            continue
        if isinstance(value, int):
            # If it's > 1e12, assume ms; otherwise it's seconds.
            return value if value > 1_000_000_000_000 else value * 1000
        if isinstance(value, float):
            return int(value * 1000)
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1000)
            except Exception:
                continue
    return None


def to_dict(obj: Any) -> Any:
    """
    Recursively convert Kalshi SDK models into JSON-serializable primitives.
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
    d = getattr(obj, "__dict__", None)
    if d is not None:
        return {k: to_dict(v) for k, v in d.items()}
    return str(obj)


# ---------------------------------------------------------------------------
# Kalshi client setup
# ---------------------------------------------------------------------------


def load_kalshi_client() -> KalshiClient:
    """
    Load credentials from env/.env and return an authenticated Kalshi client.

    Env vars:
      - KALSHI_API_KEY_ID
      - KALSHI_PRIVATE_KEY  (PEM string)
    """
    load_dotenv()
    key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")
    if not key_id or not private_key:
        raise Exception(
            "Missing Kalshi credentials. Set KALSHI_API_KEY_ID and "
            "KALSHI_PRIVATE_KEY in your environment or .env file."
        )

    config = Configuration(
        host="https://api.elections.kalshi.com/trade-api/v2"
    )
    config.api_key_id = key_id
    config.private_key_pem = private_key
    return KalshiClient(config)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_fills_last_n_days(client: KalshiClient, days: int = 365):
    """
    Fetch fills from the last `days` days using min_ts on get_fills.
    """
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
    """
    Fetch settlements from the last `days` days.

    get_settlements in your SDK does NOT accept min_ts keyword arg,
    so we paginate everything and filter client-side by timestamp.
    """
    now = datetime.now(timezone.utc)
    min_dt = now - timedelta(days=days)
    min_ts_ms = int(min_dt.timestamp() * 1000)

    cursor: Optional[str] = None
    settlements: List[Any] = []

    while True:
        resp = client.get_settlements(limit=200, cursor=cursor)
        page_settlements = getattr(resp, "settlements", None) or []

        for s in page_settlements:
            ts = get_ts_ms(s)
            if ts is None:
                continue
            if ts >= min_ts_ms:
                settlements.append(s)

        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

    return settlements


# ---------------------------------------------------------------------------
# P&L / stats computation
# ---------------------------------------------------------------------------


def compute_stats(fills, settlements):
    """
    Compute investment and P&L statistics from fills and settlements.

    Returns a dict with:
      - total_invested
      - reinvested
      - cash_invested
      - realized_pnl
      - return_rate
      - cash_in
      - cash_out
      - cumulative_series (for chart)
    """
    total_invested = 0.0
    total_cash_generated = 0.0

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

    reinvested = min(total_invested, total_cash_generated)
    cash_invested = total_invested - reinvested

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

    return_rate = (realized_pnl / total_invested) if total_invested > 0 else 0.0

    return {
        "total_invested": total_invested,
        "reinvested": reinvested,
        "cash_invested": cash_invested,
        "realized_pnl": realized_pnl,
        "return_rate": return_rate,
        "cash_in": cash_in,
        "cash_out": cash_out,
        "cumulative_series": cumulative_series,
    }


# ---------------------------------------------------------------------------
# Main summary generation
# ---------------------------------------------------------------------------


def generate_summary_json(days: int = 365):
    """
    Pull data from Kalshi, compute stats, and write data/kalshi_summary.json.
    """
    client = load_kalshi_client()

    # ----- 1) Account-level numbers: cash + open positions = portfolio -----
    balance_resp = client.get_balance()
    balance_cents = getattr(balance_resp, "balance", 0) or 0

    # Try to grab open positions (unsettled exposure)
    try:
        positions_resp = client.get_positions(settlement_status="unsettled")
    except Exception:
        positions_resp = None

    positions_cents = 0
    if positions_resp is not None:
        event_positions = getattr(positions_resp, "event_positions", None) or []

        def add_dollars(dollars_str: Optional[str]):
            nonlocal positions_cents
            if not dollars_str:
                return
            try:
                positions_cents += int(round(float(dollars_str) * 100))
            except Exception:
                pass

        # Use event_exposure_dollars as main source, fallback to total_cost_dollars
        for ep in event_positions:
            exposure_dollars = getattr(ep, "event_exposure_dollars", None)
            if exposure_dollars:
                add_dollars(exposure_dollars)
            else:
                add_dollars(getattr(ep, "total_cost_dollars", None))

    portfolio_cents = balance_cents + positions_cents

    account = {
        "cash_cents": balance_cents,
        "positions_cents": positions_cents,
        "cash": balance_cents / 100.0,
        "positions_value": positions_cents / 100.0,
        "portfolio_total": portfolio_cents / 100.0,
        "updated_ts": getattr(balance_resp, "updated_ts", None),
    }

    # ----- 2) Trading activity -----
    fills = fetch_fills_last_n_days(client, days=days)
    settlements = fetch_settlements_last_n_days(client, days=days)
    stats = compute_stats(fills, settlements)

    fills_dict = [to_dict(f) for f in fills]
    settlements_dict = [to_dict(s) for s in settlements]

    # ----- 3) Net profit / ROI based on TOTAL_DEPOSITS -----
    # DEFAULT: if env var is missing or invalid, assume you've deposited $40.
    total_deposits_env = os.getenv("TOTAL_DEPOSITS")
    if total_deposits_env:
        try:
            total_deposits = float(total_deposits_env)
        except Exception:
            total_deposits = 40.0
    else:
        total_deposits = 40.0

    portfolio_total = account["portfolio_total"]
    realized_pnl = stats.get("realized_pnl", 0.0)
    positions_value = account["positions_value"]

    # Core numbers
    net_profit = portfolio_total - total_deposits

    # If you have no open positions, unrealized P&L should just be 0,
    # even if you're up – everything is realized into cash.
    if positions_value <= 1e-6:
        unrealized_pnl = 0.0
    else:
        unrealized_pnl = net_profit - realized_pnl

    net_profit_percent = (
        (net_profit / total_deposits) if total_deposits > 0 else 0.0
    )

    stats_extra = dict(stats)
    stats_extra["total_deposits"] = total_deposits
    stats_extra["net_profit"] = net_profit
    stats_extra["net_profit_percent"] = net_profit_percent
    stats_extra["unrealized_pnl"] = unrealized_pnl

    # ----- 4) Final JSON -----
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
    generate_summary_json(days=365)

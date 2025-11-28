import os
import json
from datetime import datetime, timedelta, timezone

import kalshi_python
from kalshi_python.api import PortfolioApi


# ------------ CONFIG ------------

# How many days back to include in the JSON
DAYS_BACK = 14

# Paths relative to repo layout
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
OUTPUT_JSON = os.path.join(DATA_DIR, "kalshi_summary.json")


# ------------ HELPERS ------------

def make_client():
    """
    Initialize Kalshi Python SDK client using API key + private key.

    Expects these environment variables (we'll set them in GitHub Secrets):

      - KALSHI_API_KEY_ID   -> your Kalshi API key ID
      - KALSHI_PRIVATE_KEY  -> the full contents of your PEM private key
    """
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")

    if not api_key_id or not private_key_pem:
        raise RuntimeError(
            "Missing KALSHI_API_KEY_ID or KALSHI_PRIVATE_KEY env vars. "
            "Set them as GitHub Secrets or environment variables."
        )

    config = kalshi_python.Configuration(
        host="https://api.elections.kalshi.com/trade-api/v2"
    )
    config.api_key_id = api_key_id
    config.private_key_pem = private_key_pem

    client = kalshi_python.KalshiClient(config)
    return client


def unix_ts(dt: datetime) -> int:
    """Convert datetime to Unix timestamp in seconds (UTC)."""
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


# ------------ CORE FETCHES ------------

def fetch_balance(portfolio_api: PortfolioApi):
    """
    Get current account balance and portfolio value.
    """
    resp = portfolio_api.get_balance()

    balance_cents = getattr(resp, "balance", 0)
    portfolio_value_cents = getattr(resp, "portfolio_value", balance_cents)
    updated_ts = getattr(resp, "updated_ts", int(datetime.now(timezone.utc).timestamp()))

    return {
        "balance_cents": balance_cents,
        "portfolio_value_cents": portfolio_value_cents,
        "updated_ts": updated_ts,
    }


def fetch_settlements_last_n_days(portfolio_api: PortfolioApi, days_back: int):
    """
    Fetch realized settlements (closed outcomes) for the last N days.
    """
    now = datetime.now(timezone.utc)
    min_dt = now - timedelta(days=days_back)
    min_ts = unix_ts(min_dt)
    max_ts = unix_ts(now)

    settlements = []
    cursor = None

    while True:
        resp = portfolio_api.get_settlements(
            limit=200,
            cursor=cursor,
            min_ts=min_ts,
            max_ts=max_ts,
        )
        settlements.extend(getattr(resp, "settlements", []))

        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

    return settlements


def group_daily_pnl_from_settlements(settlements):
    """
    Aggregate realized P&L per day from settlement objects.

    NOTE: You will probably need to adjust the field names after we
    see a real example of your settlement data.
    """
    daily = {}

    for s in settlements:
        # Guess timestamp field name.
        ts = getattr(s, "ts", None) or getattr(s, "settled_ts", None)
        if ts is None:
            continue

        # If ts looks like ms, convert to seconds.
        if ts > 10_000_000_000:
            ts = ts / 1000.0

        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        day_str = dt.date().isoformat()

        # Guess P&L field.
        cash_change_cents = getattr(s, "cash_change", None)
        if cash_change_cents is None:
            cash_change_cents = getattr(s, "amount", 0)

        if day_str not in daily:
            daily[day_str] = {
                "realized_pnl_cents": 0,
                "num_settlements": 0,
            }

        daily[day_str]["realized_pnl_cents"] += cash_change_cents
        daily[day_str]["num_settlements"] += 1

    return daily


def build_summary_json(balance_info, daily_pnl):
    """
    Build JSON structure for frontend consumption.
    """
    sorted_days = sorted(daily_pnl.items(), key=lambda x: x[0], reverse=True)

    daily_rows = []
    lifetime_realized_cents = 0

    for day_str, stats in sorted_days:
        pnl = stats["realized_pnl_cents"]
        lifetime_realized_cents += pnl
        daily_rows.append({
            "date": day_str,
            "realized_pnl_cents": pnl,
            "realized_pnl_dollars": round(pnl / 100.0, 2),
            "num_settlements": stats["num_settlements"],
        })

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "days_back": DAYS_BACK,
        },
        "account": {
            "available_balance_cents": balance_info["balance_cents"],
            "available_balance_dollars": round(balance_info["balance_cents"] / 100.0, 2),
            "portfolio_value_cents": balance_info["portfolio_value_cents"],
            "portfolio_value_dollars": round(balance_info["portfolio_value_cents"] / 100.0, 2),
        },
        "performance": {
            "lifetime_realized_pnl_cents_in_window": lifetime_realized_cents,
            "lifetime_realized_pnl_dollars_in_window": round(lifetime_realized_cents / 100.0, 2),
        },
        "daily": daily_rows,
    }

    return summary


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    client = make_client()
    portfolio_api = PortfolioApi(client)

    balance_info = fetch_balance(portfolio_api)
    settlements = fetch_settlements_last_n_days(portfolio_api, DAYS_BACK)
    daily_pnl = group_daily_pnl_from_settlements(settlements)
    summary = build_summary_json(balance_info, daily_pnl)

    with open(OUTPUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote summary to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()

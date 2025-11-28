import os
import json
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
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

def load_env():
    """
    Load environment variables from backend/.env
    (We will create this file locally later; it is gitignored.)
    """
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        raise RuntimeError("backend/.env not found. Create it with your Kalshi keys.")


def make_client():
    """
    Initialize Kalshi Python SDK client using API key + private key.

    NOTE: This assumes you're using key-based auth.
    You will need:
      - KALSHI_API_KEY_ID  in backend/.env
      - KALSHI_PRIVATE_KEY_PATH  path to your PEM in backend/.env
    """
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")

    if not api_key_id or not key_path:
        raise RuntimeError("Missing KALSHI_API_KEY_ID or KALSHI_PRIVATE_KEY_PATH in backend/.env")

    if not os.path.isabs(key_path):
        # Treat as relative to backend/
        key_path = os.path.join(os.path.dirname(__file__), key_path)

    if not os.path.exists(key_path):
        raise RuntimeError(f"Private key file not found at: {key_path}")

    with open(key_path, "r") as f:
        private_key_pem = f.read()

    # Base config – this host may be updated by Kalshi; adjust if needed per docs.
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

    Uses /portfolio/balance endpoint via SDK.
    """
    resp = portfolio_api.get_balance()
    # Depending on SDK version, these field names may differ slightly.
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

    We'll use this to approximate realized P&L per day.
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
        # resp.settlements should be a list of settlement objects
        settlements.extend(getattr(resp, "settlements", []))

        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

    return settlements


def group_daily_pnl_from_settlements(settlements):
    """
    Aggregate realized P&L per day from settlement objects.

    IMPORTANT:
    - You will likely need to adjust the field names here
      after printing an example settlement from your account.
    """
    daily = {}

    for s in settlements:
        # Guess likely timestamp field names:
        ts = getattr(s, "ts", None) or getattr(s, "settled_ts", None)
        if ts is None:
            # Try another common one, or skip.
            continue

        # If ts is in ms instead of seconds, divide by 1000.
        if ts > 10_000_000_000:
            ts = ts / 1000.0

        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        day_str = dt.date().isoformat()

        # Guess P&L / cash change field.
        # You will need to inspect your own data to confirm.
        cash_change_cents = getattr(s, "cash_change", None)
        if cash_change_cents is None:
            # As a fallback, try generic 'amount' or 'payout'
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
    # Sort days descending (newest first)
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
    load_env()

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

import os
import json
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
from kalshi_python import ApiClient, Configuration
from kalshi_python.api.portfolio_api import PortfolioApi


# -------------------------
# Load Kalshi credentials
# -------------------------
def load_kalshi_client():
    load_dotenv()

    key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")

    if not key_id or not private_key:
        raise Exception("Missing Kalshi credentials in environment variables.")

    config = Configuration(
        api_key={
            "key_id": key_id,
            "private_key": private_key
        },
        host="https://api.elections.kalshi.com/trade-api/v2"
    )
    return ApiClient(config)


# -------------------------
# Fetch Fills
# -------------------------
def fetch_fills_last_n_days(client, days=1):
    portfolio = PortfolioApi(client)

    min_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    max_ts = int(datetime.utcnow().timestamp())

    fills = []
    cursor = None

    while True:
        resp = portfolio.get_fills(
            min_ts=min_ts,
            max_ts=max_ts,
            limit=200,
            cursor=cursor
        )

        if hasattr(resp, "fills") and resp.fills:
            fills.extend(resp.fills)

        if not hasattr(resp, "cursor") or not resp.cursor:
            break

        cursor = resp.cursor

    return fills


# -------------------------
# Fetch Settlements Without Invalid Params
# -------------------------
def fetch_settlements_last_n_days(client, days=1):
    portfolio = PortfolioApi(client)

    min_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    max_ts = int(datetime.utcnow().timestamp())

    settlements = []
    cursor = None

    while True:
        resp = portfolio.get_settlements(
            limit=200,
            cursor=cursor
        )

        # Filter after receiving
        for s in getattr(resp, "settlements", []):
            ts_val = getattr(s, "ts", None)
            if ts_val is None:
                continue

            # Convert ms → seconds if needed
            if ts_val > 10_000_000_000:
                ts_val = ts_val / 1000

            if ts_val < min_ts or ts_val > max_ts:
                continue

            settlements.append(s)

        if not hasattr(resp, "cursor") or not resp.cursor:
            break

        cursor = resp.cursor

    return settlements


# -------------------------
# Convert response objects to dict
# -------------------------
def to_dict(obj):
    if not obj:
        return None

    if hasattr(obj, "to_dict"):
        return obj.to_dict()

    try:
        return vars(obj)
    except Exception:
        return str(obj)


# -------------------------
# MAIN EXPORT FUNCTION
# -------------------------
def generate_summary_json():
    client = load_kalshi_client()

    fills = fetch_fills_last_n_days(client, days=1)
    settlements = fetch_settlements_last_n_days(client, days=1)

    fills_dict = [to_dict(f) for f in fills]
    settlements_dict = [to_dict(s) for s in settlements]

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "fills_last_1_day": fills_dict,
        "settlements_last_1_day": settlements_dict
    }

    os.makedirs("data", exist_ok=True)

    with open("data/kalshi_summary.json", "w") as f:
        json.dump(summary, f, indent=4)

    print("✓ Summary JSON generated successfully.")


# -------------------------
# Script entry point
# -------------------------
if __name__ == "__main__":
    generate_summary_json()

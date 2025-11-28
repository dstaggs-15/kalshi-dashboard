import os
import json
from datetime import datetime, timedelta

from dotenv import load_dotenv
from kalshi_python import Configuration, KalshiClient


# -------------------------
# Load Kalshi client
# -------------------------
def load_kalshi_client():
    # Load from .env (local) or environment (GitHub Actions)
    load_dotenv()

    key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")

    if not key_id or not private_key:
        raise Exception(
            "Missing Kalshi credentials. "
            "Make sure KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY are set."
        )

    # Configure Kalshi client (production elections API)
    config = Configuration(
        host="https://api.elections.kalshi.com/trade-api/v2"
    )

    # These field names are EXACTLY what the SDK expects
    config.api_key_id = key_id
    config.private_key_pem = private_key

    client = KalshiClient(config)
    return client


# -------------------------
# Fetch fills from last N days
# -------------------------
def fetch_fills_last_n_days(client, days=1):
    now = datetime.utcnow()
    min_ts = int((now - timedelta(days=days)).timestamp())
    max_ts = int(now.timestamp())

    fills = []
    cursor = None

    while True:
        resp = client.get_fills(
            min_ts=min_ts,
            max_ts=max_ts,
            limit=200,
            cursor=cursor,
        )

        if getattr(resp, "fills", None):
            fills.extend(resp.fills)

        # Pagination: stop when no cursor is returned
        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

    return fills


# -------------------------
# Fetch settlements from last N days
# (API does NOT accept min_ts/max_ts, so we filter locally)
# -------------------------
def fetch_settlements_last_n_days(client, days=1):
    now = datetime.utcnow()
    min_ts = int((now - timedelta(days=days)).timestamp())
    max_ts = int(now.timestamp())

    settlements = []
    cursor = None

    while True:
        resp = client.get_settlements(
            limit=200,
            cursor=cursor,
        )

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

        # Pagination: stop when no cursor is returned
        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

    return settlements


# -------------------------
# JSON cleaning helpers
# -------------------------
def _clean_for_json(obj):
    """
    Recursively convert Kalshi SDK objects (and nested stuff)
    into JSON-serializable types.

    - datetime -> ISO string
    - objects with .to_dict() -> dict, then cleaned
    - objects with __dict__ -> dict, then cleaned
    - lists/tuples -> clean each element
    - dicts -> clean each value
    - everything else -> str(obj) as a fallback
    """
    # Basic JSON types
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # Datetime -> ISO string
    if isinstance(obj, datetime):
        return obj.isoformat()

    # Lists / tuples
    if isinstance(obj, (list, tuple)):
        return [_clean_for_json(x) for x in obj]

    # Dicts
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}

    # Kalshi / pydantic style objects
    if hasattr(obj, "to_dict"):
        return _clean_for_json(obj.to_dict())

    # Generic Python objects with __dict__
    try:
        return _clean_for_json(vars(obj))
    except Exception:
        # Last resort: string representation
        return str(obj)


def to_dict(obj):
    """Public helper that just calls the cleaner."""
    return _clean_for_json(obj)


# -------------------------
# Main: generate summary JSON
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
        "settlements_last_1_day": settlements_dict,
    }

    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "kalshi_summary.json")

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=4)

    print(f"✓ Summary JSON generated at {output_path}")


if __name__ == "__main__":
    generate_summary_json()

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
# Timestamp helper (ms since epoch)
# -------------------------
def get_ts_ms(obj):
    """
    Try to pull a timestamp (ms) off a Kalshi object or dict.
    Looks at ts / timestamp / created_time.
    """
    ts_val = getattr(obj, "ts", None) or getattr(obj, "timestamp", None)

    if ts_val is None:
        # created_time may be datetime or ISO string
        created = getattr(obj, "created_time", None)
        if isinstance(created, datetime):
            return int(created.timestamp() * 1000)
        if isinstance(created, str):
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1000)
            except Exception:
                return None

    # If still None, bail
    if ts_val is None:
        return None

    # number: seconds vs ms
    if isinstance(ts_val, (int, float)):
        if ts_val > 10_000_000_000:  # looks like ms
            return int(ts_val)
        return int(ts_val * 1000)

    # string number
    try:
        num = float(ts_val)
        if num > 10_000_000_000:
            return int(num)
        return int(num * 1000)
    except Exception:
        return None


# -------------------------
# Compute portfolio / P&L stats
# -------------------------
def compute_stats(fills, settlements):
    """
    Calculate:
    - total_invested: total cost of all BUY fills
    - reinvested: portion of buys funded by previous sells
    - cash_invested: net new cash
    - realized_pnl: sum of settlement cash_change
    - cash_in / cash_out: from settlements
    - cumulative_series: [{ts, cumulative}] for realized P&L
    - portfolio_value: cash_invested + reinvested + realized_pnl (approx)
    - return_rate: realized_pnl / total_invested
    """
    # ---- From fills: total invested vs cash generated from sells ----
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

    # ---- From settlements: realized P&L, cash in/out, cumulative series ----
    realized_pnl = 0.0
    cash_in = 0.0
    cash_out = 0.0
    cumulative_series = []

    # sort settlements by time
    sorted_settlements = sorted(
        settlements,
        key=lambda s: get_ts_ms(s) or 0,
    )

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
            cumulative_series.append(
                {"ts": ts, "cumulative": running}
            )

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


# -------------------------
# JSON cleaning helpers
# -------------------------
def _clean_for_json(obj):
    """
    Recursively convert Kalshi SDK objects (and nested stuff)
    into JSON-serializable types.
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
def generate_summary_json(days=1):
    client = load_kalshi_client()

    fills = fetch_fills_last_n_days(client, days=days)
    settlements = fetch_settlements_last_n_days(client, days=days)

    # Compute aggregate stats BEFORE cleaning to dict
    stats = compute_stats(fills, settlements)

    fills_dict = [to_dict(f) for f in fills]
    settlements_dict = [to_dict(s) for s in settlements]

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "lookback_days": days,
        "fills_last_1_day": fills_dict,
        "settlements_last_1_day": settlements_dict,
        "summary": stats,
    }

    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "kalshi_summary.json")

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=4)

    print(f"✓ Summary JSON generated at {output_path}")


if __name__ == "__main__":
    # Change this if you want a longer lookback (e.g., 7, 30, etc.)
    generate_summary_json(days=1)

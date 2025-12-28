import os
import json
import requests
from datetime import datetime
from scipy.stats import norm

from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# =====================
# STRATEGY SETTINGS
# =====================
DRY_RUN = False                  # TRUE = no real trades
BET_AMOUNT_CENTS = 500           # $5 per trade
PROFIT_TARGET = 1.20             # +20% take profit
MIN_EDGE = 0.05                  # 5% minimum edge
SIGMA = 2.5

SERIES_TICKER = "KXHIGHLAX"

DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"


# =====================
# WEATHER FORECAST
# =====================
def get_forecast():
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    headers = {"User-Agent": "KalshiBot/1.0 (contact@example.com)"}
    res = requests.get(url, headers=headers, timeout=10).json()

    for p in res["properties"]["periods"]:
        if p["isDaytime"]:
            return float(p["temperature"]), SIGMA

    return None, None


# =====================
# POSITION STORAGE
# =====================
def load_positions():
    if not os.path.exists(POS_FILE):
        return {}
    with open(POS_FILE, "r") as f:
        return json.load(f)


def save_positions(positions):
    with open(POS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


# =====================
# MAIN TRADER
# =====================
def main():
    # ---- API SETUP ----
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")

    if not config.api_key_id or not config.private_key_pem:
        raise RuntimeError("Missing Kalshi API credentials")

    client = KalshiClient(config)

    # ---- FORECAST ----
    mu, sigma = get_forecast()
    if mu is None:
        print("❌ No forecast available")
        return

    # ---- LOAD MARKETS ----
    markets = client.get_markets(
        series_ticker=SERIES_TICKER,
        status="open"
    ).markets

    positions = load_positions()

    # =====================
    # SELL LOGIC (TAKE PROFIT)
    # =====================
    for ticker, pos in list(positions.items()):
        market = client.get_market(ticker).market
        bid_price = market.yes_bid / 100

        if bid_price >= pos["entry_price"] * PROFIT_TARGET:
            print(f"💰 SELLING {ticker} @ {bid_price:.2f}")

            if not DRY_RUN:
                order = CreateOrderRequest(
                    ticker=ticker,
                    action="sell",
                    side="yes",
                    type="limit",
                    count=pos["count"],
                    price=market.yes_bid
                )
                client.user_order_create(order)

            del positions[ticker]

    # =====================
    # BUY LOGIC
    # =====================
    best = None
    best_edge = -1

    for m in markets:
        try:
            parts = m.subtitle.replace("°", "").split("-")
            low = float(parts[0])
            high = float(parts[1]) if len(parts) > 1 else low + 1
        except:
            continue

        prob = norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)
        ask = m.yes_ask / 100
        edge = prob - ask

        if edge > best_edge:
            best_edge = edge
            best = m

    if best and best_edge >= MIN_EDGE and best.ticker not in positions:
        entry_price = best.yes_ask / 100
        count = int(BET_AMOUNT_CENTS / (entry_price * 100))

        if count > 0:
            print(
                f"🎯 BUY {count}x {best.ticker} "
                f"@ {entry_price:.2f} | edge={best_edge:.2%}"
            )

            if not DRY_RUN:
                order = CreateOrderRequest(
                    ticker=best.ticker,
                    action="buy",
                    side="yes",
                    type="limit",
                    count=count,
                    price=best.yes_ask
                )
                client.user_order_create(order)

            positions[best.ticker] = {
                "entry_price": entry_price,
                "count": count,
                "time": str(datetime.utcnow())
            }

    save_positions(positions)

    # =====================
    # SUMMARY OUTPUT
    # =====================
    summary = {
        "timestamp": str(datetime.utcnow()),
        "forecast": {"mu": mu, "sigma": sigma},
        "best_market": best.ticker if best else None,
        "best_edge": best_edge,
        "dry_run": DRY_RUN
    }

    with open(DATA_FILE, "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

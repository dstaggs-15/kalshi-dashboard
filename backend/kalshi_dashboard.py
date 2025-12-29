import os
import json
import uuid
import requests
from datetime import datetime, timedelta
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# --- SETTINGS ---
DRY_RUN = False  # Set to False to trade real money
BET_AMOUNT_USD = 5.00
PROFIT_TARGET = 1.25 # 25% Profit Goal
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"

def get_noaa_tomorrow_high():
    """Gets specific high temp for KLAX tomorrow."""
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    res = requests.get(url, headers={'User-Agent': 'Bot'}).json()
    for p in res['properties']['periods']:
        if p['isDaytime'] and "tomorrow" in p['name'].lower():
            return float(p['temperature'])
    return None

def main():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    client = KalshiClient(config)

    target_temp = get_noaa_tomorrow_high()
    if not target_temp: return

    # Load positions to manage 25% profit sell
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # 1. AUTO-SELL LOGIC
    for ticker, entry_price in list(my_bets.items()):
        m_data = client.get_market(ticker).market
        current_bid = m_data.yes_bid / 100
        if current_bid >= (entry_price * PROFIT_TARGET):
            print(f"💰 TARGET HIT: Selling {ticker} for 25% profit")
            if not DRY_RUN:
                client.user_order_create(ticker=ticker, action="sell", side="yes", count=1, type="market", client_order_id=str(uuid.uuid4()))
            del my_bets[ticker]

    # 2. AUTO-BUY (SNIPE)
    markets = client.get_markets(series_ticker="KXHIGHLAX", status="open").markets
    best_m = None
    for m in markets:
        parts = m.subtitle.replace('°','').split('-')
        low = float(parts[0])
        high = float(parts[1]) if len(parts) > 1 else low + 1
        if low <= target_temp <= high:
            best_m = m
            break

    if best_m and best_m.ticker not in my_bets:
        price = best_m.yes_ask / 100
        count = int(BET_AMOUNT_USD / price)
        print(f"🎯 SNIPING: NOAA says {target_temp}F. Buying {best_m.ticker} at {price}")
        if not DRY_RUN:
            client.user_order_create(CreateOrderRequest(ticker=best_m.ticker, action="buy", side="yes", count=count, type="limit", yes_price=best_m.yes_ask, client_order_id=str(uuid.uuid4())))
            my_bets[best_m.ticker] = price

    # Save tracking and dashboard summary
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    with open(DATA_FILE, 'w') as f:
        json.dump({"last_updated": str(datetime.now()), "target_temp": target_temp, "active_bet": best_m.ticker if best_m else None}, f)

if __name__ == "__main__": main()

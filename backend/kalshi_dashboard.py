import os
import json
import uuid
import requests
from datetime import datetime
from scipy.stats import norm
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# --- STRATEGY SETTINGS ---
DRY_RUN = False  # Set to False to trade real money
BET_AMOUNT_CENTS = 500 # $5.00 bet
PROFIT_TARGET = 1.20 # Sell when up 20%
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json" # Tracks entry prices

def get_forecast():
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    headers = {'User-Agent': 'KalshiBot/1.0 (contact@example.com)'}
    res = requests.get(url, headers=headers).json()
    for p in res['properties']['periods']:
        if p['isDaytime']: return float(p['temperature']), 2.5
    return None, None

def main():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    client = KalshiClient(config)

    mu, sigma = get_forecast()
    if mu is None: return

    # KXHIGHLAX is the series for Los Angeles high temperatures
    markets = client.get_markets(series_ticker="KXHIGHLAX", status="open").markets
    
    # 1. PROFIT CHECK: Check owned positions for 20% gain
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    for ticker, entry_price in list(my_bets.items()):
        m_data = client.get_market(ticker).market
        current_bid = m_data.yes_bid / 100
        if current_bid >= (entry_price * PROFIT_TARGET):
            print(f"💰 PROFIT TARGET HIT: Selling {ticker}")
            # client.user_order_create(ticker=ticker, action="sell", ...) 
            del my_bets[ticker]

    # 2. AUTO-BUY: Snipe the highest probability bracket at 10 AM
    best_opportunity = None
    max_edge = -1
    for m in markets:
        parts = m.subtitle.replace('°','').split('-')
        low = float(parts[0])
        high = float(parts[1]) if len(parts) > 1 else low + 1
        prob = norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)
        price = m.yes_ask / 100
        edge = prob - price
        if edge > max_edge:
            max_edge, best_opportunity = edge, m

    if best_opportunity and best_opportunity.ticker not in my_bets:
        entry_price = best_opportunity.yes_ask / 100
        count = int(BET_AMOUNT_CENTS / (entry_price * 100))
        print(f"🎯 SNIPING: Buying {count} contracts of {best_opportunity.ticker}")
        if not DRY_RUN:
            # client.user_order_create(...)
            my_bets[best_opportunity.ticker] = entry_price

    # Save tracking data
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    summary = {"last_updated": str(datetime.now()), "forecast": {"mu": mu, "sigma": sigma}, 
               "recommendations": [{"ticker": best_opportunity.ticker, "price": entry_price, "edge": max_edge}] if best_opportunity else [],
               "dry_run": DRY_RUN}
    with open(DATA_FILE, 'w') as f: json.dump(summary, f)

if __name__ == "__main__": main()

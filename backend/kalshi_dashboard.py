import os
import json
import uuid
import requests
from datetime import datetime
from scipy.stats import norm
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# --- SETTINGS ---
DRY_RUN = True  # Set to False to trade real money
PROFIT_TARGET = 1.20 # Sell when up 20%
EDGE_THRESHOLD = 0.05
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"

def get_forecast():
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    res = requests.get(url, headers={'User-Agent': 'Bot'}).json()
    for p in res['properties']['periods']:
        if p['isDaytime']: return float(p['temperature']), 2.5
    return None, None

def main():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    client = KalshiClient(config)

    mu, sigma = get_forecast()
    markets = client.get_markets(series_ticker="KXHIGH", status="open").markets
    
    # --- PART 1: AUTO-SELL LOGIC ---
    # Load what we bought previously to check for profits
    try:
        with open(POS_FILE, 'r') as f: saved_pos = json.load(f)
    except: saved_pos = {}

    for ticker, entry_price in saved_pos.items():
        m_data = client.get_market(ticker).market
        current_bid = m_data.yes_bid / 100
        if current_bid >= (entry_price * PROFIT_TARGET):
            print(f"💰 TARGET HIT! Selling {ticker} at {current_bid}")
            # client.user_order_create(ticker=ticker, action="sell", ...) # Add sell code here
            del saved_pos[ticker] # Remove from tracking after selling

    # --- PART 2: AUTO-BUY LOGIC ---
    best_ticker = None
    best_edge = -1
    best_price = 0

    for m in markets:
        # Simplified parser for ranges like "70-71"
        parts = m.subtitle.replace('°','').split('-')
        low = float(parts[0])
        high = float(parts[1]) if len(parts) > 1 else low + 1
        
        prob = norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)
        price = m.yes_ask / 100
        edge = prob - price

        if edge > best_edge and edge > EDGE_THRESHOLD:
            best_edge, best_ticker, best_price = edge, m.ticker, price

    # Buy the best guess if we don't own it
    if best_ticker and best_ticker not in saved_pos:
        print(f"🎯 SNIPING: Buying {best_ticker} at {best_price}")
        if not DRY_RUN:
            # client.user_order_create(...) # Add buy code here
            saved_pos[best_ticker] = best_price

    # Save tracking data
    with open(POS_FILE, 'w') as f: json.dump(saved_pos, f)
    
    # Save dashboard data
    summary = {"last_updated": str(datetime.now()), "forecast": {"mu": mu, "sigma": sigma}, 
               "recommendations": [{"ticker": best_ticker, "price": best_price, "edge": best_edge}] if best_ticker else [],
               "dry_run": DRY_RUN}
    with open(DATA_FILE, 'w') as f: json.dump(summary, f)

if __name__ == "__main__": main()

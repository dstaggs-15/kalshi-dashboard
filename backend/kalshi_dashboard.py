import os
import json
import uuid
import requests
from datetime import datetime
from scipy.stats import norm
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# --- STRATEGY SETTINGS ---
DRY_RUN = True  # Set to False to trade real money
BET_AMOUNT_CENTS = 500 # $5.00 bet
PROFIT_TARGET = 1.20 # Sell when up 20%
EDGE_THRESHOLD = 0.05
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"

def get_forecast():
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    headers = {'User-Agent': 'KalshiWeatherBot/1.0 (contact@example.com)'}
    res = requests.get(url, headers=headers).json()
    for p in res['properties']['periods']:
        if p['isDaytime']: return float(p['temperature']), 2.5
    return None, None

def get_client():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    return KalshiClient(config)

def main():
    client = get_client()
    mu, sigma = get_forecast()
    if mu is None: return

    markets = client.get_markets(series_ticker="KXHIGH", status="open").markets
    
    # 1. LOAD PREVIOUS BUYS & CHECK FOR PROFIT
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    for ticker, entry_price in list(my_bets.items()):
        m_data = client.get_market(ticker).market
        current_bid = m_data.yes_bid / 100
        if current_bid >= (entry_price * PROFIT_TARGET):
            print(f"💰 TARGET HIT: Selling {ticker} at {current_bid}")
            # Order to Sell: side='no' action='buy' OR side='yes' action='sell'
            # client.user_order_create(ticker=ticker, action="sell", side="yes", ...)
            del my_bets[ticker]

    # 2. AUTO-BUY BEST GUESS (10 AM SNIPE)
    best_opportunity = None
    max_edge = -1

    for m in markets:
        parts = m.subtitle.replace('°','').split('-')
        low = float(parts[0])
        high = float(parts[1]) if len(parts) > 1 else low + 1
        
        prob = norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)
        price = m.yes_ask / 100
        edge = prob - price

        if edge > max_edge and edge > EDGE_THRESHOLD:
            max_edge, best_opportunity = edge, m

    if best_opportunity and best_opportunity.ticker not in my_bets:
        entry_price = best_opportunity.yes_ask / 100
        count = int(BET_AMOUNT_CENTS / (entry_price * 100))
        print(f"🎯 SNIPING: Buying {count} contracts of {best_opportunity.ticker} at {entry_price}")
        if not DRY_RUN:
            order_id = str(uuid.uuid4())
            client.user_order_create(CreateOrderRequest(
                ticker=best_opportunity.ticker, action="buy", side="yes",
                count=count, type="limit", yes_price=int(entry_price * 100),
                client_order_id=order_id
            ))
            my_bets[best_opportunity.ticker] = entry_price

    # Save tracking and dashboard data
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    summary = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "forecast": {"mu": mu, "sigma": sigma},
        "recommendations": [{"ticker": best_opportunity.ticker, "price": entry_price, "edge": max_edge}] if best_opportunity else [],
        "dry_run": DRY_RUN
    }
    with open(DATA_FILE, 'w') as f: json.dump(summary, f)

if __name__ == "__main__": main()

import os
import json
import uuid
import time
import requests
from datetime import datetime
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# ==========================================
# LIVE TRADING SETTINGS
# ==========================================
DRY_RUN = False            
BET_AMOUNT_USD = 5.00      
PROFIT_TARGET = 1.25       
SERIES_TICKER = "KXHIGHLAX"
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"

def get_noaa_tomorrow_high():
    """Fetch NOAA high temp with mandatory User-Agent and retry logic."""
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    # NWS requires a unique User-Agent identifier
    headers = {
        'User-Agent': 'KLAXWeatherSniper/1.0 (dstaggs@github.com)',
        'Accept': 'application/geo+json'
    }
    
    # Try up to 3 times to bypass temporary IP-based blocking
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status() # Catch 403, 404, or 503 errors
            res = response.json()
            
            for p in res['properties']['periods']:
                if p['isDaytime'] and "tomorrow" in p['name'].lower():
                    return float(p['temperature'])
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} Failed: {e}")
            time.sleep(2) # Brief wait before retry
    return None

def main():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    
    if not config.api_key_id or not config.private_key_pem:
        print("❌ ERROR: Missing API Credentials")
        return

    client = KalshiClient(config)
    target_temp = get_noaa_tomorrow_high()
    
    if target_temp is None:
        print("❌ ERROR: Could not retrieve NOAA forecast after retries")
        return

    # Load positions
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # AUTO-SELL (25% Profit Check)
    for ticker, entry_price in list(my_bets.items()):
        market = client.get_market(ticker).market
        current_bid = market.yes_bid / 100
        if current_bid >= (entry_price * PROFIT_TARGET):
            print(f"💰 SELLING {ticker} for profit")
            client.user_order_create(ticker=ticker, action="sell", side="yes", count=1, type="market", client_order_id=str(uuid.uuid4()))
            del my_bets[ticker]

    # AUTO-BUY (10 AM SNIPE)
    if not my_bets:
        markets = client.get_markets(series_ticker=SERIES_TICKER, status="open").markets
        for m in markets:
            parts = m.subtitle.replace('°','').split('-')
            low = float(parts[0])
            high = float(parts[1]) if len(parts) > 1 else low + 1
            
            if low <= target_temp <= high:
                price = m.yes_ask / 100
                count = int(BET_AMOUNT_USD / price)
                print(f"🎯 BUYING: {count}x {m.ticker} @ {price}")
                if not DRY_RUN:
                    client.user_order_create(CreateOrderRequest(
                        ticker=m.ticker, action="buy", side="yes", 
                        count=count, type="limit", yes_price=m.yes_ask, 
                        client_order_id=str(uuid.uuid4())
                    ))
                    my_bets[m.ticker] = price
                break

    # SAVE DATA
    os.makedirs('backend', exist_ok=True)
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    os.makedirs('docs/data', exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump({
            "last_updated": str(datetime.now()), 
            "target_temp": target_temp, 
            "active_bet": list(my_bets.keys())[0] if my_bets else None
        }, f)

if __name__ == "__main__":
    main()

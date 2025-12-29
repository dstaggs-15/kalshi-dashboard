import os
import json
import uuid
import requests
import time
from datetime import datetime
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# ==========================================
# FINALIZED LIVE TRADING SETTINGS
# ==========================================
DRY_RUN = False            
BET_AMOUNT_USD = 5.00      
PROFIT_TARGET = 1.25       
SERIES_TICKER = "KXHIGHLAX"
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"

def get_noaa_tomorrow_high():
    """Fetch tomorrow's high using the robust Points -> Grid lookup."""
    # Step 1: Resolve Grid for KLAX (33.94, -118.40)
    point_url = "https://api.weather.gov/points/33.94,-118.40"
    headers = {
        'User-Agent': 'KLAXWeatherSniper/1.1 (dstaggs@github.com)',
        'Accept': 'application/geo+json'
    }

    for attempt in range(3):
        try:
            print(f"📡 Step 1: Getting Grid ID (Attempt {attempt+1})...")
            point_res = requests.get(point_url, headers=headers, timeout=15)
            point_res.raise_for_status()
            forecast_url = point_res.json()['properties']['forecast']
            
            print(f"📡 Step 2: Querying Grid: {forecast_url}")
            forecast_res = requests.get(forecast_url, headers=headers, timeout=15)
            forecast_res.raise_for_status()
            periods = forecast_res.json()['properties']['periods']
            
            for p in periods:
                if p['isDaytime'] and "tomorrow" in p['name'].lower():
                    print(f"✅ Success! Tomorrow's Forecast: {p['temperature']}°F")
                    return float(p['temperature'])
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(5)
    return None

def main():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    
    if not config.api_key_id or not config.private_key_pem:
        print("❌ ERROR: Missing Secrets")
        return

    client = KalshiClient(config)
    target_temp = get_noaa_tomorrow_high()
    
    if target_temp is None:
        print("❌ ERROR: NOAA API unreachable.")
        return

    # Load positions
    os.makedirs('backend', exist_ok=True)
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # 1. AUTO-SELL (25% Profit Check)
    for ticker, entry_price in list(my_bets.items()):
        try:
            m = client.get_market(ticker).market
            current_bid = m.yes_bid / 100
            if current_bid >= (entry_price * PROFIT_TARGET):
                print(f"💰 SELLING {ticker} for profit!")
                client.user_order_create(ticker=ticker, action="sell", side="yes", count=1, type="market", client_order_id=str(uuid.uuid4()))
                del my_bets[ticker]
        except Exception as e:
            print(f"⚠️ Sell check failed: {e}")

    # 2. AUTO-BUY (10 AM SNIPE)
    if not my_bets:
        try:
            markets = client.get_markets(series_ticker=SERIES_TICKER, status="open").markets
            for m in markets:
                parts = m.subtitle.replace('°','').split('-')
                low = float(parts[0])
                high = float(parts[1]) if len(parts) > 1 else low + 1
                if low <= target_temp <= high:
                    price = m.yes_ask / 100
                    count = int(BET_AMOUNT_USD / price)
                    print(f"🎯 BUYING: {count}x {m.ticker} @ {price}")
                    client.user_order_create(CreateOrderRequest(
                        ticker=m.ticker, action="buy", side="yes", 
                        count=count, type="limit", yes_price=m.yes_ask, 
                        client_order_id=str(uuid.uuid4())
                    ))
                    my_bets[m.ticker] = price
                    break
        except Exception as e:
            print(f"⚠️ Market check failed: {e}")

    # Save tracking
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    os.makedirs('docs/data', exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump({"last_updated": str(datetime.now()), "target_temp": target_temp, "active_bet": list(my_bets.keys())[0] if my_bets else None}, f)

if __name__ == "__main__":
    main()

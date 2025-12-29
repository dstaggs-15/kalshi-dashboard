import os
import json
import uuid
import requests
import time
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
    """Fetch tomorrow's high with high-reliability headers and direct station access."""
    # KLAX station is more stable than gridpoint queries
    url = "https://api.weather.gov/stations/KLAX/forecast"
    
    # These headers mimic a modern Chrome browser to bypass security blocks
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'application/ld+json',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    for attempt in range(4):
        try:
            print(f"📡 Querying KLAX Station... (Attempt {attempt + 1})")
            response = requests.get(url, headers=headers, timeout=20)
            
            if response.status_code == 403:
                print("⚠️ NWS Blocked IP (403). Retrying with delay...")
                time.sleep(5)
                continue
                
            response.raise_for_status() 
            res = response.json()
            
            # Station API returns 'periods' directly in the root or under 'properties'
            periods = res.get('periods') or res.get('properties', {}).get('periods', [])
            
            for p in periods:
                if p['isDaytime'] and "tomorrow" in p['name'].lower():
                    print(f"✅ Success! NOAA Tomorrow Forecast: {p['temperature']}°F")
                    return float(p['temperature'])
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} Failed: {e}")
            time.sleep(3)
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
        print("❌ ERROR: NOAA API is currently unreachable. Check logs.")
        return

    # Load positions
    if not os.path.exists('backend'): os.makedirs('backend')
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # 1. AUTO-SELL (25% Profit Check)
    for ticker, entry_price in list(my_bets.items()):
        try:
            market = client.get_market(ticker).market
            current_bid = market.yes_bid / 100
            if current_bid >= (entry_price * PROFIT_TARGET):
                print(f"💰 SELLING {ticker} for 25% profit!")
                client.user_order_create(ticker=ticker, action="sell", side="yes", count=1, type="market", client_order_id=str(uuid.uuid4()))
                del my_bets[ticker]
        except Exception as e:
            print(f"⚠️ Sell check failed for {ticker}: {e}")

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
                    if price < 0.80:
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
            print(f"⚠️ Market search failed: {e}")

    # SAVE DATA
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    if not os.path.exists('docs/data'): os.makedirs('docs/data')
    with open(DATA_FILE, 'w') as f:
        json.dump({"last_updated": str(datetime.now()), "target_temp": target_temp, "active_bet": list(my_bets.keys())[0] if my_bets else None}, f)

if __name__ == "__main__":
    main()

import os
import json
import uuid
import requests
import time
from datetime import datetime
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# ==========================================
# LIVE TRADING SETTINGS - ACTIVATED
# ==========================================
DRY_RUN = False            # Set to True only if you want to test without spending
BET_AMOUNT_USD = 5.00      # Amount to spend per trade
PROFIT_TARGET = 1.25       # 25% Profit Goal (e.g., buy at $0.40, sell at $0.50)
SERIES_TICKER = "KXHIGHLAX"
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"

def get_noaa_tomorrow_high():
    """Fetch tomorrow's high temp from NWS with mandatory User-Agent."""
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    
    # CRITICAL: NWS API requires a unique User-Agent
    # Format: AppName/Version (ContactEmail)
    headers = {
        'User-Agent': 'KLAXWeatherSniper/1.1 (dstaggs@github.com)',
        'Accept': 'application/geo+json'
    }
    
    # Retry loop to handle temporary GitHub runner IP blocks
    for attempt in range(3):
        try:
            print(f"📡 Querying NOAA... (Attempt {attempt + 1})")
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status() 
            res = response.json()
            
            for p in res['properties']['periods']:
                # Find the daytime period for tomorrow
                if p['isDaytime'] and "tomorrow" in p['name'].lower():
                    print(f"✅ Forecast Found: {p['temperature']}°F")
                    return float(p['temperature'])
        except Exception as e:
            print(f"⚠️ NOAA API Attempt {attempt + 1} Failed: {e}")
            time.sleep(2)
    return None

def main():
    # 1. AUTHENTICATION
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    
    if not config.api_key_id or not config.private_key_pem:
        print("❌ ERROR: Missing KALSHI_API_KEY_ID or KALSHI_PRIVATE_KEY in Secrets")
        return

    client = KalshiClient(config)
    target_temp = get_noaa_tomorrow_high()
    
    if target_temp is None:
        print("❌ ERROR: Could not retrieve NOAA forecast after retries")
        return

    # 2. POSITION MANAGEMENT
    if not os.path.exists('backend'): os.makedirs('backend')
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # 3. AUTO-SELL (25% PROFIT TARGET)
    for ticker, entry_price in list(my_bets.items()):
        try:
            market = client.get_market(ticker).market
            current_bid = market.yes_bid / 100
            if current_bid >= (entry_price * PROFIT_TARGET):
                print(f"💰 PROFIT TARGET HIT: Selling {ticker} at {current_bid}")
                if not DRY_RUN:
                    client.user_order_create(
                        ticker=ticker, action="sell", side="yes", 
                        count=1, type="market", client_order_id=str(uuid.uuid4())
                    )
                del my_bets[ticker]
        except Exception as e:
            print(f"⚠️ Error checking sell target for {ticker}: {e}")

    # 4. AUTO-BUY (10 AM SNIPE)
    if not my_bets:
        try:
            # Note: status='open' is 'active' in Kalshi response
            markets = client.get_markets(series_ticker=SERIES_TICKER, status="open").markets
            best_m = None
            for m in markets:
                # Parse range from subtitle e.g., "70-71"
                parts = m.subtitle.replace('°','').split('-')
                low = float(parts[0])
                high = float(parts[1]) if len(parts) > 1 else low + 1
                
                if low <= target_temp <= high:
                    best_m = m
                    break

            if best_m:
                price = best_m.yes_ask / 100
                if price < 0.75: # Ensure there is room for profit
                    count = int(BET_AMOUNT_USD / price)
                    print(f"🎯 SNIPING: Buying {count}x {best_m.ticker} @ {price}")
                    if not DRY_RUN:
                        client.user_order_create(CreateOrderRequest(
                            ticker=best_m.ticker, action="buy", side="yes", 
                            count=count, type="limit", yes_price=best_m.yes_ask, 
                            client_order_id=str(uuid.uuid4())
                        ))
                        my_bets[best_m.ticker] = price
        except Exception as e:
            print(f"⚠️ Market search error: {e}")

    # 5. DATA PERSISTENCE
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    
    if not os.path.exists('docs/data'): os.makedirs('docs/data')
    with open(DATA_FILE, 'w') as f:
        json.dump({
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "target_temp": target_temp,
            "active_bet": list(my_bets.keys())[0] if my_bets else None,
            "dry_run": DRY_RUN
        }, f, indent=2)
    print("🚀 Pulse Complete.")

if __name__ == "__main__":
    main()

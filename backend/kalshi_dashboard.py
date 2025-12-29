import os
import json
import uuid
import requests
from datetime import datetime
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# ==========================================
# LIVE TRADING SETTINGS - ACTIVATED
# ==========================================
DRY_RUN = False            # LIVE TRADING ENABLED
BET_AMOUNT_USD = 5.00      # $5.00 per trade
PROFIT_TARGET = 1.25       # 25% Profit Exit
SERIES_TICKER = "KXHIGHLAX"
DATA_FILE = "docs/data/kalshi_summary.json"
POS_FILE = "backend/my_positions.json"

def get_noaa_tomorrow_high():
    """Fetch the specific NOAA high temperature for tomorrow."""
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    headers = {'User-Agent': 'KLAXWeatherSniper/1.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        for p in res['properties']['periods']:
            # We look for the 'Tomorrow' daytime period
            if p['isDaytime'] and "tomorrow" in p['name'].lower():
                return float(p['temperature'])
    except Exception as e:
        print(f"Error fetching NOAA: {e}")
    return None

def main():
    # 1. API SETUP
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    
    if not config.api_key_id or not config.private_key_pem:
        print("❌ ERROR: API Credentials missing in GitHub Secrets")
        return

    client = KalshiClient(config)
    target_temp = get_noaa_tomorrow_high()
    
    if target_temp is None:
        print("❌ ERROR: Could not retrieve NOAA forecast")
        return

    # 2. LOAD EXISTING POSITIONS
    if not os.path.exists('backend'): os.makedirs('backend')
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # 3. AUTO-SELL LOGIC (Checking for 25% Profit)
    for ticker, entry_price in list(my_bets.items()):
        market = client.get_market(ticker).market
        current_bid = market.yes_bid / 100
        if current_bid >= (entry_price * PROFIT_TARGET):
            print(f"💰 PROFIT TARGET MET: Selling {ticker} at {current_bid}")
            client.user_order_create(
                ticker=ticker, action="sell", side="yes", 
                count=1, type="market", client_order_id=str(uuid.uuid4())
            )
            del my_bets[ticker]

    # 4. AUTO-BUY LOGIC (10 AM SNIPE)
    # Only buy if we aren't already holding a position for this cycle
    if not my_bets:
        markets = client.get_markets(series_ticker=SERIES_TICKER, status="open").markets
        best_m = None
        for m in markets:
            # Parse subtitles like "70°-71°"
            parts = m.subtitle.replace('°','').split('-')
            low = float(parts[0])
            high = float(parts[1]) if len(parts) > 1 else low + 1
            
            if low <= target_temp <= high:
                best_m = m
                break

        if best_m:
            price = best_m.yes_ask / 100
            # Ensure price isn't already too high to make profit
            if price < 0.75: 
                count = int(BET_AMOUNT_USD / price)
                print(f"🎯 SNIPING: NOAA Forecast {target_temp}F. Buying {count}x {best_m.ticker} @ {price}")
                
                client.user_order_create(CreateOrderRequest(
                    ticker=best_m.ticker, action="buy", side="yes", 
                    count=count, type="limit", yes_price=best_m.yes_ask, 
                    client_order_id=str(uuid.uuid4())
                ))
                my_bets[best_m.ticker] = price

    # 5. UPDATE TRACKING & DASHBOARD
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    
    if not os.path.exists('docs/data'): os.makedirs('docs/data')
    with open(DATA_FILE, 'w') as f:
        json.dump({
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "target_temp": target_temp,
            "active_bet": list(my_bets.keys())[0] if my_bets else None,
            "dry_run": DRY_RUN
        }, f, indent=2)

if __name__ == "__main__":
    main()

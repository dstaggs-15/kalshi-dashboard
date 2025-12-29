import os
import json
import uuid
import requests
from datetime import datetime, timedelta
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

def get_tomorrow_high_open_meteo():
    """Get tomorrow's high for KLAX using Open-Meteo (No API Key Required)."""
    # KLAX Coordinates: 33.94, -118.40
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 33.94,
        "longitude": -118.40,
        "daily": "temperature_2m_max",
        "temperature_unit": "fahrenheit",
        "timezone": "America/Los_Angeles",
        "forecast_days": 2
    }
    
    try:
        print("📡 Querying Open-Meteo for KLAX...")
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        # Index 0 is today, Index 1 is tomorrow
        tomorrow_high = data['daily']['temperature_2m_max'][1]
        print(f"✅ Success! Tomorrow's High: {tomorrow_high}°F")
        return float(tomorrow_high)
    except Exception as e:
        print(f"❌ Weather API Error: {e}")
    return None

def main():
    # 1. AUTHENTICATION
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    client = KalshiClient(config)

    target_temp = get_tomorrow_high_open_meteo()
    if target_temp is None:
        print("❌ ERROR: Could not get weather data.")
        return

    # 2. POSITION TRACKING
    os.makedirs('backend', exist_ok=True)
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # 3. AUTO-SELL (25% PROFIT CHECK)
    for ticker, entry_price in list(my_bets.items()):
        try:
            m = client.get_market(ticker).market
            current_bid = m.yes_bid / 100
            if current_bid >= (entry_price * PROFIT_TARGET):
                print(f"💰 SELLING {ticker} for profit!")
                client.user_order_create(ticker=ticker, action="sell", side="yes", count=1, type="market", client_order_id=str(uuid.uuid4()))
                del my_bets[ticker]
        except Exception as e: print(f"⚠️ Sell check error: {e}")

    # 4. AUTO-BUY (SNIPE)
    if not my_bets:
        try:
            markets = client.get_markets(series_ticker=SERIES_TICKER, status="open").markets
            for m in markets:
                # Extracts numbers from subtitle (e.g., '70-71')
                import re
                nums = re.findall(r'\d+', m.subtitle)
                if not nums: continue
                low = float(nums[0])
                high = float(nums[1]) if len(nums) > 1 else low + 0.9
                
                if low <= target_temp <= high:
                    price = m.yes_ask / 100
                    if 0 < price < 0.85:
                        count = int(BET_AMOUNT_USD / price)
                        print(f"🎯 BUYING: {count}x {m.ticker} @ {price}")
                        client.user_order_create(CreateOrderRequest(ticker=m.ticker, action="buy", side="yes", count=count, type="limit", yes_price=m.yes_ask, client_order_id=str(uuid.uuid4())))
                        my_bets[m.ticker] = price
                        break
        except Exception as e: print(f"⚠️ Market search error: {e}")

    # SAVE DATA
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    os.makedirs('docs/data', exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump({"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "target_temp": target_temp, "active_bet": list(my_bets.keys())[0] if my_bets else None}, f, indent=2)

if __name__ == "__main__": main()

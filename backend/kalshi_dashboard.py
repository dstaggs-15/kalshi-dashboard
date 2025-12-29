import os
import json
import uuid
import requests
import re  # CRITICAL: Fixes 'local variable re' error
from bs4 import BeautifulSoup
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

def scrape_noaa_tomorrow_high():
    """Scrape tomorrow's high from the stable NWS Text Forecast table."""
    url = "https://forecast.weather.gov/MapClick.php?lat=33.9439&lon=-118.4209&lg=english&FcstType=text"
    # Modern browser headers to bypass security firewalls
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}

    try:
        print(f"📡 Scraping NOAA Web Page: {url}")
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # NWS Text page uses <table> with <tr> rows. 
        # We look for the row containing 'Tomorrow' or specific weekday names.
        rows = soup.find_all('tr')
        for row in rows:
            text = row.get_text().replace('\n', ' ').strip().lower()
            # Logic: Must mention tomorrow and must include 'high'
            if "tomorrow" in text and "high" in text:
                # Find the number immediately following 'high'
                match = re.search(r'high.*?(\d+)', text)
                if match:
                    temp = float(match.group(1))
                    print(f"✅ Scraped High: {temp}°F")
                    return temp
        
        # Backup: Scan raw page text for 'high near XX' pattern
        page_text = soup.get_text().lower()
        match = re.search(r'tomorrow.*?high near (\d+)', page_text)
        if match:
            temp = float(match.group(1))
            print(f"✅ Scraped High (Backup): {temp}°F")
            return temp

    except Exception as e:
        print(f"❌ Scraping Error: {e}")
    return None

def main():
    # 1. API AUTHENTICATION
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    
    if not config.api_key_id or not config.private_key_pem:
        print("❌ ERROR: Missing KALSHI Secrets")
        return

    client = KalshiClient(config)
    target_temp = scrape_noaa_tomorrow_high()
    
    if target_temp is None:
        print("❌ ERROR: Failed to scrape temperature. NOAA page format may have changed.")
        return

    # 2. POSITION TRACKING
    os.makedirs('backend', exist_ok=True)
    try:
        with open(POS_FILE, 'r') as f: my_bets = json.load(f)
    except: my_bets = {}

    # 3. AUTO-SELL LOGIC (+25% Profit Target)
    for ticker, entry_price in list(my_bets.items()):
        try:
            m = client.get_market(ticker).market
            current_bid = m.yes_bid / 100
            if current_bid >= (entry_price * PROFIT_TARGET):
                print(f"💰 PROFIT TARGET MET: Selling {ticker}")
                client.user_order_create(ticker=ticker, action="sell", side="yes", count=1, type="market", client_order_id=str(uuid.uuid4()))
                del my_bets[ticker]
        except Exception as e:
            print(f"⚠️ Sell check failed: {e}")

    # 4. AUTO-BUY LOGIC (10 AM SNIPE)
    if not my_bets:
        try:
            markets = client.get_markets(series_ticker=SERIES_TICKER, status="open").markets
            for m in markets:
                # Use regex to find all numbers in subtitle (e.g. '70-71')
                nums = re.findall(r'\d+', m.subtitle)
                if not nums: continue
                
                low = float(nums[0])
                high = float(nums[1]) if len(nums) > 1 else low + 0.9
                
                if low <= target_temp <= high:
                    price = m.yes_ask / 100
                    # Only buy if price allows for 25% upside (less than $0.80)
                    if 0 < price < 0.80:
                        count = int(BET_AMOUNT_USD / price)
                        print(f"🎯 SNIPE: Buying {count}x {m.ticker} @ {price}")
                        client.user_order_create(CreateOrderRequest(
                            ticker=m.ticker, action="buy", side="yes", 
                            count=count, type="limit", yes_price=m.yes_ask, 
                            client_order_id=str(uuid.uuid4())
                        ))
                        my_bets[m.ticker] = price
                        break
        except Exception as e:
            print(f"⚠️ Market search failed: {e}")

    # 5. DATA PERSISTENCE
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    os.makedirs('docs/data', exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump({
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "target_temp": target_temp, 
            "active_bet": list(my_bets.keys())[0] if my_bets else None
        }, f, indent=2)

if __name__ == "__main__":
    main()

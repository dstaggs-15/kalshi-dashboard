import os
import json
import uuid
import requests
import re  # Fixed: Added import at the top
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
    """Scrape tomorrow's high temp directly from the NWS forecast page."""
    url = "https://forecast.weather.gov/MapClick.php?lat=33.9439&lon=-118.4209&lg=english&FcstType=text"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}

    try:
        print(f"📡 Scraping NOAA Web Page: {url}")
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # The text-only NWS page uses a table structure
        # We look for rows containing 'Tomorrow' and 'High'
        rows = soup.find_all('tr')
        for row in rows:
            text = row.get_text().replace('\n', ' ').strip()
            # Look for the row that has tomorrow's date or the word 'Tomorrow'
            if ("tomorrow" in text.lower() or "monday" in text.lower()) and "high" in text.lower():
                # Extract the first number found after the word "high"
                match = re.search(r'high.*?(\d+)', text.lower())
                if match:
                    temp = float(match.group(1))
                    print(f"✅ Scraped High: {temp}°F")
                    return temp
                    
        # Fallback: Search the entire body text for 'High near X'
        body_text = soup.get_text().lower()
        match = re.search(r'tomorrow.*?high near (\d+)', body_text)
        if match:
            temp = float(match.group(1))
            print(f"✅ Scraped High (Fallback): {temp}°F")
            return temp

    except Exception as e:
        print(f"❌ Scraping Error: {e}")
    return None

def main():
    # 1. AUTHENTICATION
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    
    if not config.api_key_id or not config.private_key_pem:
        print("❌ ERROR: Missing Secrets")
        return

    client = KalshiClient(config)
    target_temp = scrape_noaa_tomorrow_high()
    
    if target_temp is None:
        print("❌ ERROR: Failed to scrape temperature. Check NWS page format.")
        return

    # 2. POSITION MANAGEMENT
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
        except Exception as e:
            print(f"⚠️ Sell check failed: {e}")

    # 4. AUTO-BUY (SNIPE)
    if not my_bets:
        try:
            markets = client.get_markets(series_ticker=SERIES_TICKER, status="open").markets
            for m in markets:
                # Subtitle looks like "70°-71°" or "71°"
                nums = re.findall(r'\d+', m.subtitle)
                if not nums: continue
                
                low = float(nums[0])
                high = float(nums[1]) if len(nums) > 1 else low + 0.9
                
                if low <= target_temp <= high:
                    price = m.yes_ask / 100
                    if price > 0 and price < 0.85:
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

    # 5. SAVE DATA
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

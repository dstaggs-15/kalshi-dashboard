import os
import json
import uuid
import requests
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
    # This URL points to the KLAX specific forecast
    url = "https://forecast.weather.gov/MapClick.php?lat=33.9439&lon=-118.4209&lg=english&FcstType=text"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}

    try:
        print(f"📡 Scraping NOAA Web Page: {url}")
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # Find the row that says 'Tomorrow' or 'Monday' (if today is Sunday)
        # The text forecast is usually in <b> tags inside <td> tags
        rows = soup.find_all('tr')
        for i, row in enumerate(rows):
            text = row.get_text().lower()
            if "tomorrow" in text and "high" in text:
                # Extract the number from strings like "High: 68"
                import re
                temp = re.findall(r'\d+', text)
                if temp:
                    print(f"✅ Scraped High: {temp[0]}°F")
                    return float(temp[0])
                    
        # Fallback: check next day's text specifically
        forecast_text = soup.get_text().lower()
        match = re.search(r'tomorrow.*?high near (\d+)', forecast_text)
        if match:
            print(f"✅ Scraped High (Regex): {match.group(1)}°F")
            return float(match.group(1))

    except Exception as e:
        print(f"❌ Scraping Error: {e}")
    return None

def main():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    client = KalshiClient(config)

    target_temp = scrape_noaa_tomorrow_high()
    if target_temp is None:
        print("❌ ERROR: Failed to scrape temperature.")
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
        except Exception as e: print(f"⚠️ Sell check error: {e}")

    # 2. AUTO-BUY (SNIPE)
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
                    client.user_order_create(CreateOrderRequest(ticker=m.ticker, action="buy", side="yes", count=count, type="limit", yes_price=m.yes_ask, client_order_id=str(uuid.uuid4())))
                    my_bets[m.ticker] = price
                    break
        except Exception as e: print(f"⚠️ Market search error: {e}")

    # Save tracking
    with open(POS_FILE, 'w') as f: json.dump(my_bets, f)
    os.makedirs('docs/data', exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump({"last_updated": str(datetime.now()), "target_temp": target_temp, "active_bet": list(my_bets.keys())[0] if my_bets else None}, f)

if __name__ == "__main__": main()

import os
import uuid
import json
import requests
import numpy as np
from datetime import datetime
from scipy.stats import norm
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# --- SETTINGS ---
DRY_RUN = True  # Set to False to trade real money
EDGE_THRESHOLD = 0.05
STATION_ID = "KLAX" # Los Angeles International Airport
WEATHER_URL = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"

def get_forecast():
    """Gets NWS temperature forecast for KLAX."""
    headers = {'User-Agent': '(myweatherbot.com, contact@email.com)'}
    res = requests.get(WEATHER_URL, headers=headers).json()
    # Grab the first daytime high
    for period in res['properties']['periods']:
        if period['isDaytime']:
            return float(period['temperature']), 2.5 # Mean, StdDev
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

    # Fetch relevant weather markets
    # Kalshi often uses 'KXHIGH' for daily high temperature series
    markets = client.get_markets(series_ticker="KXHIGH", status="open").markets
    
    trade_log = []
    
    for m in markets:
        ticker = m.ticker
        yes_price = m.yes_ask / 100
        
        # Determine bucket range from title (e.g., "75° to 76°")
        # Note: This parser is simplified for the example
        try:
            parts = m.subtitle.replace('°', '').split('-')
            low = float(parts[0])
            high = float(parts[1]) if len(parts) > 1 else low + 1
        except: continue

        # Calculate Edge
        prob = norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)
        edge = prob - yes_price

        if edge > EDGE_THRESHOLD:
            print(f"Edge found for {ticker}: {edge:.2f}")
            if not DRY_RUN:
                order = CreateOrderRequest(
                    ticker=ticker, action="buy", side="yes", count=1,
                    type="limit", yes_price=m.yes_ask, client_order_id=str(uuid.uuid4())
                )
                client.user_order_create(order)
            
            trade_log.append({"ticker": ticker, "edge": round(edge, 3), "price": yes_price})

    # Prepare data for Frontend
    summary_data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "forecast": {"mu": mu, "sigma": sigma},
        "recommendations": trade_log,
        "dry_run": DRY_RUN
    }

    # Save to the directory GitHub Pages reads
    output_path = "frontend/data/kalshi_summary.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary_data, f, indent=4)

if __name__ == "__main__":
    main()

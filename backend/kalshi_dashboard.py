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
STATION_ID = "KLAX"
WEATHER_URL = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"

def get_forecast():
    """Gets NWS temperature forecast for KLAX."""
    headers = {'User-Agent': 'KalshiBot/1.0 (contact@example.com)'}
    try:
        res = requests.get(WEATHER_URL, headers=headers).json()
        for period in res['properties']['periods']:
            if period['isDaytime']:
                return float(period['temperature']), 2.5
    except Exception as e:
        print(f"Weather Error: {e}")
    return None, None

def get_client():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    return KalshiClient(config)

def parse_temp(subtitle):
    """Turns market titles into numbers for the math."""
    text = subtitle.replace('°', '').lower()
    if '-' in text:
        low, high = text.split('-')
        return float(low), float(high)
    elif 'above' in text:
        val = ''.join(filter(lambda x: x.isdigit() or x=='.', text))
        return float(val), None
    elif 'below' in text:
        val = ''.join(filter(lambda x: x.isdigit() or x=='.', text))
        return None, float(val)
    return None, None

def main():
    client = get_client()
    mu, sigma = get_forecast()
    if mu is None: return

    markets = client.get_markets(series_ticker="KXHIGH", status="open").markets
    recommendations = []
    
    for m in markets:
        low, high = parse_temp(m.subtitle)
        if low is None and high is None: continue
        
        price = m.yes_ask / 100
        if high is None: prob = 1 - norm.cdf(low, mu, sigma)
        elif low is None: prob = norm.cdf(high, mu, sigma)
        else: prob = norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)

        edge = prob - price
        if edge > EDGE_THRESHOLD:
            recommendations.append({"ticker": m.ticker, "price": price, "edge": round(edge, 3)})
            if not DRY_RUN:
                order = CreateOrderRequest(
                    ticker=m.ticker, action="buy", side="yes", count=1,
                    type="limit", yes_price=m.yes_ask, client_order_id=str(uuid.uuid4())
                )
                client.user_order_create(order)

    summary = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "forecast": {"mu": mu, "sigma": sigma},
        "recommendations": sorted(recommendations, key=lambda x: x['edge'], reverse=True),
        "dry_run": DRY_RUN
    }

    # CRITICAL: Save directly to the docs/data folder
    output_path = "docs/data/kalshi_summary.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=4)
    print("Strategy execution complete.")

if __name__ == "__main__":
    main()

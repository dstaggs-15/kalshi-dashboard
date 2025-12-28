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
    headers = {'User-Agent': 'KalshiWeatherBot/1.0 (contact@yourdomain.com)'}
    try:
        res = requests.get(WEATHER_URL, headers=headers).json()
        for period in res['properties']['periods']:
            if period['isDaytime']:
                return float(period['temperature']), 2.5 # Mean, StdDev
    except Exception as e:
        print(f"Weather API Error: {e}")
    return None, None

def get_client():
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    return KalshiClient(config)

def parse_temp_range(subtitle):
    """Simple parser to turn '75° or above' or '70°-71°' into numbers."""
    clean = subtitle.replace('°', '').replace(' or above', '').replace(' or below', '')
    if '-' in clean:
        parts = clean.split('-')
        return float(parts[0]), float(parts[1])
    elif 'above' in subtitle:
        return float(clean), None
    elif 'below' in subtitle:
        return None, float(clean)
    return float(clean), float(clean) + 1.0

def main():
    client = get_client()
    mu, sigma = get_forecast()
    
    if mu is None:
        print("Could not retrieve forecast. Exiting.")
        return

    # Fetch active daily high markets
    markets = client.get_markets(series_ticker="KXHIGH", status="open").markets
    recommendations = []
    
    for m in markets:
        ticker = m.ticker
        yes_price = m.yes_ask / 100
        
        low, high = parse_temp_range(m.subtitle)
        
        # Calculate statistical probability
        if high is None: # "Above X"
            prob = 1 - norm.cdf(low, mu, sigma)
        elif low is None: # "Below X"
            prob = norm.cdf(high, mu, sigma)
        else: # Range
            prob = norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)

        edge = prob - yes_price

        # If edge is good, log it and trade if not in dry run
        if edge > EDGE_THRESHOLD:
            recommendations.append({
                "ticker": ticker,
                "price": yes_price,
                "edge": round(edge, 3)
            })
            
            if not DRY_RUN:
                print(f"Placing Order for {ticker} | Edge: {edge:.2%}")
                order = CreateOrderRequest(
                    ticker=ticker, action="buy", side="yes", count=1,
                    type="limit", yes_price=m.yes_ask, client_order_id=str(uuid.uuid4())
                )
                client.user_order_create(order)

    # Sort recommendations by highest edge
    recommendations = sorted(recommendations, key=lambda x: x['edge'], reverse=True)

    # Final Data Object
    summary_data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "forecast": {"mu": mu, "sigma": sigma},
        "recommendations": recommendations,
        "dry_run": DRY_RUN
    }

    # IMPORTANT: Save to the /docs/data folder for the website
    output_path = "docs/data/kalshi_summary.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary_data, f, indent=4)
    
    print(f"Successfully ran. Found {len(recommendations)} high-edge markets.")

if __name__ == "__main__":
    main()

import os
import uuid
import requests
import numpy as np
from scipy.stats import norm
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# --- CONFIGURATION ---
KLAX_FORECAST_URL = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
DRY_RUN = True  # CHANGE TO False ONLY WHEN READY TO SPEND REAL MONEY
EDGE_THRESHOLD = 0.05  # 5% edge required to place a trade
STOP_LOSS = 0.20       # Exit if price drops 20%
TAKE_PROFIT = 0.15     # Exit if price rises 15%

def get_nws_forecast():
    """Fetches the official high temperature forecast for KLAX."""
    headers = {'User-Agent': 'KalshiWeatherBot/1.0 (contact@example.com)'}
    try:
        res = requests.get(KLAX_FORECAST_URL, headers=headers).json()
        # Look for the first 'daytime' period which contains the High Temp
        for period in res['properties']['periods']:
            if period['isDaytime']:
                return float(period['temperature']), 2.5  # Returns (Mean, Sigma)
    except Exception as e:
        print(f"Error fetching weather: {e}")
    return None, None

def calculate_probability(low, high, mu, sigma):
    """The Math: Calculates probability of temp falling in a bucket range."""
    if high is None: # For 'Above X' buckets
        return 1 - norm.cdf(low, mu, sigma)
    if low is None: # For 'Below X' buckets
        return norm.cdf(high, mu, sigma)
    return norm.cdf(high, mu, sigma) - norm.cdf(low, mu, sigma)

def main():
    # 1. Setup Kalshi Connection using your existing secret names
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    client = KalshiClient(config)

    # 2. Get the "Brain" data (Forecast)
    mu, sigma = get_nws_forecast()
    if not mu: return
    print(f"--- KLAX Forecast: {mu}°F (Uncertainty: {sigma}) ---")

    # 3. Find relevant markets (Filtering for Today's High Temp)
    # Note: We filter for 'KXHIGH' which is the typical Kalshi ticker prefix for LAX High
    markets = client.get_markets(limit=10, series_ticker="KXHIGH").markets
    
    for m in markets:
        # Example: 'KXHIGH-25DEC-T75' means High Temp 75-76
        # We extract the 'T75' part to define our math boundaries
        ticker = m.ticker
        price = m.yes_ask / 100
        
        # Simplified parser: extract temperature from title/subtitle
        # For a real bot, you'd want a robust 'if/else' based on title strings
        # Here we assume a 1-degree bucket for the demo
        floor = float(m.subtitle.replace('° or above', '').replace('°', '').split('-')[0])
        cap = floor + 1 

        our_prob = calculate_probability(floor, cap, mu, sigma)
        edge = our_prob - price

        print(f"Market: {ticker} | Price: {price:.2f} | Our Prob: {our_prob:.2f} | Edge: {edge:.2f}")

        # 4. Automate Investing
        if edge > EDGE_THRESHOLD:
            print(f"!!! EDGE DETECTED ({edge:.2f}) !!!")
            if not DRY_RUN:
                order = CreateOrderRequest(
                    ticker=ticker, action="buy", side="yes", count=1,
                    type="limit", yes_price=m.yes_ask, client_order_id=str(uuid.uuid4())
                )
                client.user_order_create(order)
                print(f"Order placed for {ticker}")

        # 5. Automate Early Exit
        # Logic: Check positions you already own and sell if profit target hit
        # (This section requires fetching user positions from client)

if __name__ == "__main__":
    main()

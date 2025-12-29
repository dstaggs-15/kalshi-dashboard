import os
import json
import requests
from datetime import datetime, timedelta
from meteostat import Point, Daily
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import CreateOrderRequest

# --- SETTINGS ---
STATION_ID = "72295" # WMO ID for KLAX
DRY_RUN = False 
BET_AMOUNT = 5.00
PROFIT_TARGET = 1.25 # 25% Profit

def get_noaa_forecast():
    """Gets the specific high temp for tomorrow from NWS."""
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    res = requests.get(url, headers={'User-Agent': 'Bot'}).json()
    # Find the first 'Daytime' period that isn't 'Today'
    for p in res['properties']['periods']:
        if p['isDaytime'] and "tomorrow" in p['name'].lower():
            return float(p['temperature'])
    return None

def get_historic_normal():
    """Gets the historical average high for tomorrow's date."""
    tomorrow = datetime.now() + timedelta(days=1)
    location = Point(33.94, -118.40) # KLAX Coordinates
    # Fetch last 10 years of data for this specific day
    data = Daily(location, tomorrow - timedelta(days=3650), tomorrow)
    df = data.fetch()
    # Filter for the same month and day across years
    df['month'] = df.index.month
    df['day'] = df.index.day
    normal = df[(df.month == tomorrow.month) & (df.day == tomorrow.day)]['tmax'].mean()
    return (normal * 9/5) + 32 # Convert C to F

def main():
    # Setup Kalshi
    config = Configuration(host="https://api.elections.kalshi.com/trade-api/v2")
    config.api_key_id = os.getenv("KALSHI_API_KEY_ID")
    config.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY")
    client = KalshiClient(config)

    forecast_temp = get_noaa_forecast()
    historic_temp = get_historic_normal()
    
    # We prioritize the live NOAA forecast
    target_temp = forecast_temp if forecast_temp else historic_temp
    print(f"Targeting: {target_temp}°F (Forecast: {forecast_temp}, Normal: {historic_temp})")

    markets = client.get_markets(series_ticker="KXHIGHLAX", status="open").markets
    
    for m in markets:
        # Check if our target_temp falls inside this bracket (e.g., '70-71')
        parts = m.subtitle.replace('°','').split('-')
        low = float(parts[0])
        high = float(parts[1]) if len(parts) > 1 else low + 1
        
        if low <= target_temp <= high:
            price = m.yes_ask / 100
            if price < 0.80: # Only buy if payout is decent (at least 20% upside)
                print(f"🎯 MATCH FOUND: Buying {m.ticker} at {price}")
                # Place $5 Buy Order
                # ... [client.user_order_create logic]

import os
import requests
# ... (other imports)

def get_noaa_tomorrow_high():
    """Fetch NOAA forecast with mandatory unique User-Agent identifier."""
    url = "https://api.weather.gov/gridpoints/LOX/154,44/forecast"
    
    # NOAA REQUIRES a unique User-Agent. Without this, you get a 403 error.
    # Format: ApplicationName/Version (YourContactEmail)
    headers = {
        'User-Agent': 'KLAXWeatherSniper/1.1 (dstaggs@github.com)',
        'Accept': 'application/geo+json'
    }
    
    try:
        # Increased timeout to handle GitHub runner latency
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status() 
        res = response.json()
        
        # ... (rest of your logic to find 'tomorrow' high)
        return target_temp
    except Exception as e:
        # This will now print the EXACT error (403, 404, etc.) in your logs
        print(f"❌ NOAA API Error: {e}")
    return None

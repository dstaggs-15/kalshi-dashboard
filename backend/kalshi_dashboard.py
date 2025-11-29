import os
import json
import datetime
from kalshi_python import KalshiClient, Configuration

# Note: In GitHub Actions, we don't need load_dotenv() because 
# secrets are injected directly into the environment by the workflow YAML.

def serialize_dates(obj):
    """Helper to fix date objects for JSON dumping"""
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)

def main():
    print("--- Starting Kalshi Dashboard Update (GitHub Actions) ---")

    # 1. AUTHENTICATION
    # Get secrets from Environment Variables
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")

    if not api_key_id or not private_key:
        print("CRITICAL ERROR: Secrets missing.")
        print("Ensure KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY are set in GitHub Secrets.")
        exit(1)

    # FIX: GitHub Secrets sometimes mash newlines into literals. 
    # We must ensure the PEM key has real newlines.
    if "\\n" in private_key:
        private_key = private_key.replace("\\n", "\n")

    try:
        # Configure the Client
        config = Configuration()
        config.host = "https://api.elections.kalshi.com/trade-api/v2"
        config.api_key_id = api_key_id
        config.private_key = private_key # Pass the string directly
        
        kalshi = KalshiClient(config)
        print("Authenticated successfully.")
        
    except Exception as e:
        print(f"Error logging in: {e}")
        exit(1)

    # ---------------------------------------------------------
    # 2. FETCH DATA
    # ---------------------------------------------------------
    
    # A. BALANCE & VALUE
    try:
        balance_resp = kalshi.get_balance()
        
        # API returns values in CENTS
        raw_balance_cents = getattr(balance_resp, 'balance', 0)
        raw_portfolio_cents = getattr(balance_resp, 'portfolio_value', 0)

        # Fallback if portfolio_value is missing
        if raw_portfolio_cents == 0 and raw_balance_cents > 0:
            raw_collateral = getattr(balance_resp, 'collateral', 0)
            raw_portfolio_cents = raw_balance_cents + raw_collateral

        # CONVERT TO DOLLARS
        cash_balance = raw_balance_cents / 100.0
        total_account_value = raw_portfolio_cents / 100.0
        
        money_in_bets = total_account_value - cash_balance
        if money_in_bets < 0: money_in_bets = 0.0
        
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return

    # B. FILLS
    clean_fills = []
    try:
        # Get last 100 fills
        fills_resp = kalshi.get_fills(limit=100)
        fills_data = getattr(fills_resp, 'fills', [])
        
        for f in fills_data:
            clean_fills.append({
                "ticker": getattr(f, 'ticker', 'Unknown'),
                "side": getattr(f, 'side', 'Unknown'),
                "count": getattr(f, 'count', 0),
                "price_cents": getattr(f, 'price', 0),
                "created_time": getattr(f, 'created_time', '')
            })
    except Exception as e:
        print(f"Error fetching fills: {e}")

    # C. SETTLEMENTS
    clean_settlements = []
    try:
        settlements_resp = kalshi.get_settlements(limit=100)
        settlements_data = getattr(settlements_resp, 'settlements', [])
        
        for s in settlements_data:
            clean_settlements.append({
                "ticker": getattr(s, 'ticker', ''),
                "settled_time": getattr(s, 'settled_time', ''),
                "outcome": getattr(s, 'outcome', ''),
                "received_cents": getattr(s, 'settlement_total', 0)
            })
    except Exception as e:
        print(f"Error fetching settlements: {e}")

    # ---------------------------------------------------------
    # 3. SUMMARY CALCULATIONS
    # ---------------------------------------------------------
    
    total_deposits = 40.00 
    net_profit = total_account_value - total_deposits
    
    if total_deposits > 0:
        roi_percent = (net_profit / total_deposits) * 100.0
    else:
        roi_percent = 0.0

    if total_account_value > 0:
        house_money_share = (max(net_profit, 0) / total_account_value) * 100.0
    else:
        house_money_share = 0.0

    # ---------------------------------------------------------
    # 4. SAVE JSON
    # ---------------------------------------------------------
    dashboard_data = {
        "meta": {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "account": {
            "cash_balance": round(cash_balance, 2),
            "total_account_value": round(total_account_value, 2),
            "money_in_bets": round(money_in_bets, 2),
        },
        "summary": {
            "total_deposits": round(total_deposits, 2),
            "net_profit": round(net_profit, 2),
            "roi_percent": round(roi_percent, 1),
            "house_money_share": round(house_money_share, 1)
        },
        "fills": clean_fills,
        "settlements": clean_settlements
    }

    # Output path - ensure this matches where your HTML expects it
    # In GitHub actions, we usually commit this back to the repo
    output_path = "frontend/data/kalshi_summary.json"
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(dashboard_data, f, indent=4, default=serialize_dates)
        
    print(f"Success. Data written to {output_path}")
    print(f"Stats -> Value: ${total_account_value}, Cash: ${cash_balance}")

if __name__ == "__main__":
    main()

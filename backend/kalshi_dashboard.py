import os
import json
import datetime
from dotenv import load_dotenv
from kalshi_python import KalshiAPI

# 1. Setup and Auth
load_dotenv()

email = os.getenv("KALSHI_EMAIL")
password = os.getenv("KALSHI_PASSWORD")
# If using API keys instead of email/pass, adapt accordingly:
# api_key_id = os.getenv("KALSHI_API_KEY_ID")
# private_key = os.getenv("KALSHI_PRIVATE_KEY")

def serialize_dates(obj):
    """Helper to fix date objects for JSON dumping"""
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)

def main():
    print("--- Starting Kalshi Dashboard Update ---")
    
    # Initialize API
    # Note: Adjust authentication method based on your specific .env setup
    try:
        kalshi = KalshiAPI()
        kalshi.login(email=email, password=password)
        print("Logged in successfully.")
    except Exception as e:
        print(f"Error logging in: {e}")
        return

    # ---------------------------------------------------------
    # 2. Fetch Core Data
    # ---------------------------------------------------------
    
    # A. BALANCE & VALUE
    # We get the raw balance. Usually returns values in CENTS.
    balance_resp = kalshi.get_balance()
    
    # Extract cents (default to 0 if missing to prevent crashes)
    raw_balance_cents = getattr(balance_resp, 'balance', 0)
    
    # Try to find portfolio value. API naming varies. 
    # We look for 'portfolio_value' first, then try to calculate it if missing.
    # Some endpoints return 'collateral' which is money in bets.
    raw_collateral_cents = getattr(balance_resp, 'collateral', 0)
    
    # If the API provides a total value, use it. Otherwise: Cash + Collateral
    if hasattr(balance_resp, 'portfolio_value'):
        raw_portfolio_cents = balance_resp.portfolio_value
    else:
        raw_portfolio_cents = raw_balance_cents + raw_collateral_cents

    # CONVERT TO DOLLARS
    cash_balance = raw_balance_cents / 100.0
    total_account_value = raw_portfolio_cents / 100.0
    
    # Logic: Money in bets is the difference
    money_in_bets = total_account_value - cash_balance
    if money_in_bets < 0: money_in_bets = 0.0

    # B. FILLS (Trades)
    # Get last 100 fills (or strict limit)
    fills_resp = kalshi.get_fills(limit=100)
    fills_data = getattr(fills_resp, 'fills', [])
    
    # Clean up fills for frontend
    clean_fills = []
    for f in fills_data:
        # Convert trade price to dollars if in cents
        # Kalshi 'price' is usually 1-99 (cents) for a Yes/No contract
        price_cents = getattr(f, 'price', 0)
        cost_cents = price_cents * getattr(f, 'count', 0) # rough estimate
        
        clean_fills.append({
            "ticker": getattr(f, 'ticker', 'Unknown'),
            "market_ticker": getattr(f, 'market_ticker', ''),
            "side": getattr(f, 'side', 'Unknown'),
            "count": getattr(f, 'count', 0),
            "price_cents": price_cents,
            "created_time": getattr(f, 'created_time', ''),
            "action": getattr(f, 'action', 'trade')
        })

    # C. SETTLEMENTS (Realized P/L)
    # Pagination might be needed, but let's grab the default batch
    settlements_resp = kalshi.get_settlements(limit=100)
    settlements_data = getattr(settlements_resp, 'settlements', [])
    
    clean_settlements = []
    realized_pnl_cents = 0
    
    for s in settlements_data:
        # 'revenue' or 'profit' fields might vary. 
        # Usually looking for the net change in balance for that event.
        # Use simple attributes for now.
        amt_cents = getattr(s, 'settlement_total', 0) 
        # Note: Depending on SDK, you might need to calculate cost basis to get PnL here.
        # For this version, we will trust the dashboard math below for global PnL.
        
        clean_settlements.append({
            "ticker": getattr(s, 'ticker', ''),
            "market_ticker": getattr(s, 'market_ticker', ''),
            "settled_time": getattr(s, 'settled_time', ''),
            "outcome": getattr(s, 'outcome', ''),
            "received_cents": amt_cents
        })

    # ---------------------------------------------------------
    # 3. Calculate Summary Metrics
    # ---------------------------------------------------------
    
    # HARDCODED INPUTS
    total_deposits = 40.00  # As requested
    
    # PROFIT MATH
    net_profit = total_account_value - total_deposits
    
    if total_deposits > 0:
        roi_percent = (net_profit / total_deposits) * 100.0
    else:
        roi_percent = 0.0

    # House Money Share: (Profit / Total Value)
    if total_account_value > 0 and net_profit > 0:
        house_money_share = (net_profit / total_account_value) * 100.0
    else:
        house_money_share = 0.0

    # ---------------------------------------------------------
    # 4. Construct JSON Payload
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
            "house_money_share": round(house_money_share, 1),
            # Since we rely on Portfolio - Deposit for Net Profit,
            # We can leave split of Open/Closed as placeholders or simplified logic
            "open_bets_pnl": 0.00, # Difficult to calc without deep market data
            "closed_bets_pnl": round(net_profit, 2) # Simplifying assumption: most PnL is realized or marked to market in portfolio val
        },
        "fills": clean_fills,
        "settlements": clean_settlements
    }

    # ---------------------------------------------------------
    # 5. Save to File
    # ---------------------------------------------------------
    # Ensure directory exists
    output_path = "../frontend/data/kalshi_summary.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(dashboard_data, f, indent=4, default=serialize_dates)
        
    print(f"Success. Data written to {output_path}")
    print(f"Summary -> Value: ${total_account_value}, Cash: ${cash_balance}")

if __name__ == "__main__":
    main()

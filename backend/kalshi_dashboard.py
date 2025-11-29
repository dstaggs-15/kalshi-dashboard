import os
import json
import datetime
from kalshi_python import KalshiClient, Configuration

def serialize_dates(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)

def main():
    print("--- Starting Kalshi Dashboard Update ---")

    # 1. AUTHENTICATION
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")

    if not api_key_id or not private_key:
        print("CRITICAL ERROR: Secrets missing.")
        exit(1)

    # Fix newlines in private key if they were flattened
    if "\\n" in private_key:
        private_key = private_key.replace("\\n", "\n")

    # Default values in case API fails
    cash_balance = 0.0
    total_account_value = 0.0
    money_in_bets = 0.0
    clean_fills = []
    clean_settlements = []

    try:
        config = Configuration()
        config.host = "https://api.elections.kalshi.com/trade-api/v2"
        config.api_key_id = api_key_id
        config.private_key = private_key
        
        kalshi = KalshiClient(config)
        print("Authenticated successfully.")
        
        # 2. FETCH DATA
        balance_resp = kalshi.get_balance()
        # Ensure we handle cents correctly
        raw_balance = getattr(balance_resp, 'balance', 0)
        raw_portfolio = getattr(balance_resp, 'portfolio_value', 0)

        # Fallback if portfolio_value is missing
        if raw_portfolio == 0 and raw_balance > 0:
            raw_collateral = getattr(balance_resp, 'collateral', 0)
            raw_portfolio = raw_balance + raw_collateral

        cash_balance = raw_balance / 100.0
        total_account_value = raw_portfolio / 100.0
        money_in_bets = max(total_account_value - cash_balance, 0.0)

        # Fills
        try:
            fills_resp = kalshi.get_fills(limit=50)
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
            print(f"Warning fetching fills: {e}")

        # Settlements
        try:
            settlements_resp = kalshi.get_settlements(limit=50)
            settlements_data = getattr(settlements_resp, 'settlements', [])
            for s in settlements_data:
                clean_settlements.append({
                    "ticker": getattr(s, 'ticker', ''),
                    "settled_time": getattr(s, 'settled_time', ''),
                    "outcome": getattr(s, 'outcome', ''),
                    "received_cents": getattr(s, 'settlement_total', 0)
                })
        except Exception as e:
            print(f"Warning fetching settlements: {e}")

    except Exception as e:
        print(f"API Error: {e}")

    # 3. CALCULATE SUMMARY
    total_deposits = 40.00
    net_profit = total_account_value - total_deposits
    roi_percent = (net_profit / total_deposits * 100.0) if total_deposits > 0 else 0.0
    house_money_share = (max(net_profit, 0) / total_account_value * 100.0) if total_account_value > 0 else 0.0

    dashboard_data = {
        "meta": { "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") },
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

    # 4. SAVE TO FILE (ABSOLUTE PATH FIX)
    # This finds the directory of the script, goes up one level, then into frontend/data
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(base_dir, "frontend", "data", "kalshi_summary.json")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(dashboard_data, f, indent=4, default=serialize_dates)
        
    print(f"SUCCESS: Data written to {output_path}")
    print(f"Stats check -> Cash: ${cash_balance}, Total: ${total_account_value}")

if __name__ == "__main__":
    main()

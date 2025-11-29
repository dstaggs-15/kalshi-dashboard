import os
import json
import datetime
from kalshi_python import KalshiClient, Configuration

# Helper for dates
def serialize_dates(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)

def main():
    print("--- 1. STARTING SCRIPT ---")
    
    # --- AUTHENTICATION ---
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")

    if not api_key_id or not private_key:
        print("CRITICAL ERROR: Secrets are missing from environment variables!")
        # We exit with success code just to let the file generation finish with 0s
        # but in real usage you might want to exit(1)
        print("Continuing with empty data...")
    
    # Fix formatting of private key
    if private_key and "\\n" in private_key:
        private_key = private_key.replace("\\n", "\n")

    # Data placeholders
    cash_balance = 0.0
    total_account_value = 0.0
    money_in_bets = 0.0
    clean_fills = []
    clean_settlements = []

    # --- API CALLS ---
    if api_key_id and private_key:
        try:
            config = Configuration()
            config.host = "https://api.elections.kalshi.com/trade-api/v2"
            config.api_key_id = api_key_id
            config.private_key = private_key
            
            client = KalshiClient(config)
            print("Authenticated with Kalshi.")

            # Get Balance
            balance = client.get_balance()
            raw_bal = getattr(balance, 'balance', 0)
            raw_port = getattr(balance, 'portfolio_value', 0)
            
            # Fallback for portfolio value
            if raw_port == 0 and raw_bal > 0:
                raw_port = raw_bal + getattr(balance, 'collateral', 0)

            cash_balance = raw_bal / 100.0
            total_account_value = raw_port / 100.0
            money_in_bets = max(total_account_value - cash_balance, 0.0)
            print(f"Data Fetched: Cash=${cash_balance}, Total=${total_account_value}")

            # Get Fills (limit 50)
            try:
                fills = client.get_fills(limit=50)
                for f in getattr(fills, 'fills', []):
                    clean_fills.append({
                        "ticker": getattr(f, 'ticker', 'Unk'),
                        "side": getattr(f, 'side', 'Unk'),
                        "count": getattr(f, 'count', 0),
                        "price_cents": getattr(f, 'price', 0),
                        "created_time": getattr(f, 'created_time', '')
                    })
            except Exception as e:
                print(f"Warning (Fills): {e}")

            # Get Settlements (limit 50)
            try:
                setts = client.get_settlements(limit=50)
                for s in getattr(setts, 'settlements', []):
                    clean_settlements.append({
                        "ticker": getattr(s, 'ticker', ''),
                        "outcome": getattr(s, 'outcome', ''),
                        "received_cents": getattr(s, 'settlement_total', 0),
                        "settled_time": getattr(s, 'settled_time', '')
                    })
            except Exception as e:
                print(f"Warning (Settlements): {e}")

        except Exception as e:
            print(f"CRITICAL API ERROR: {e}")
            print("Using default 0 values.")

    # --- CALCULATIONS ---
    total_deposits = 40.00
    net_profit = total_account_value - total_deposits
    roi = (net_profit / total_deposits * 100) if total_deposits else 0
    
    data = {
        "meta": {"updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        "account": {
            "cash_balance": round(cash_balance, 2),
            "total_account_value": round(total_account_value, 2),
            "money_in_bets": round(money_in_bets, 2),
        },
        "summary": {
            "total_deposits": total_deposits,
            "net_profit": round(net_profit, 2),
            "roi_percent": round(roi, 1)
        },
        "fills": clean_fills,
        "settlements": clean_settlements
    }

    # --- SAVE FILE (ABSOLUTE PATH) ---
    # backend/kalshi_dashboard.py -> backend/ -> root/ -> frontend/data/
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(root_dir, "frontend", "data")
    output_file = os.path.join(output_dir, "kalshi_summary.json")

    os.makedirs(output_dir, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(data, f, indent=4, default=serialize_dates)
    
    print(f"--- SUCCESS: File saved to {output_file} ---")

if __name__ == "__main__":
    main()

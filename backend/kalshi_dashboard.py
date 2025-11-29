import os
import json
import datetime
import traceback
import sys

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
# Path logic: Go up two levels from 'backend/script.py' to get to root
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(ROOT_DIR, "frontend", "data", "kalshi_summary.json")

def serialize_dates(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)

def save_json(data):
    """Guaranteed save function"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=4, default=serialize_dates)
        print(f"SUCCESS: Wrote data to {OUTPUT_FILE}")
    except Exception as e:
        print(f"CRITICAL FILE SYSTEM ERROR: {e}")
        traceback.print_exc()

def main():
    print("--- STARTING FAIL-SAFE SCRIPT ---")
    
    # Placeholder data structure
    final_data = {
        "meta": {"updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        "account": {"cash_balance": 0.0, "total_account_value": 0.0, "money_in_bets": 0.0},
        "summary": {"total_deposits": 40.0, "net_profit": 0.0, "roi_percent": 0.0},
        "fills": [],
        "settlements": [],
        "debug_log": []
    }

    try:
        # 1. IMPORT CHECK
        try:
            from kalshi_python import KalshiClient, Configuration
            print("Import successful.")
        except ImportError as e:
            final_data["debug_log"].append(f"Import Error: {str(e)}")
            raise e

        # 2. AUTH CHECK
        api_key_id = os.getenv("KALSHI_API_KEY_ID")
        private_key = os.getenv("KALSHI_PRIVATE_KEY")
        
        if not api_key_id or not private_key:
            raise ValueError("Missing Environment Variables (KALSHI_API_KEY_ID or KALSHI_PRIVATE_KEY)")

        # Fix Key Newlines
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")

        # 3. API CONNECTION
        config = Configuration()
        config.host = "https://api.elections.kalshi.com/trade-api/v2"
        config.api_key_id = api_key_id
        config.private_key = private_key
        
        client = KalshiClient(config)
        
        # 4. FETCH DATA
        print("Fetching Balance...")
        balance = client.get_balance()
        
        # Parse Balance (Handle Cents)
        raw_bal = getattr(balance, 'balance', 0)
        raw_port = getattr(balance, 'portfolio_value', 0)
        
        # Fallback if portfolio value is missing
        if raw_port == 0 and raw_bal > 0:
            raw_port = raw_bal + getattr(balance, 'collateral', 0)

        # 5. FETCH HISTORY (Safe Mode)
        clean_fills = []
        try:
            print("Fetching Fills...")
            fills_resp = client.get_fills(limit=50)
            for f in getattr(fills_resp, 'fills', []):
                clean_fills.append({
                    "ticker": getattr(f, 'ticker', 'Unk'),
                    "side": getattr(f, 'side', 'Unk'),
                    "count": getattr(f, 'count', 0),
                    "price_cents": getattr(f, 'price', 0),
                    "created_time": getattr(f, 'created_time', '')
                })
        except Exception as e:
            final_data["debug_log"].append(f"Fills Error: {str(e)}")

        clean_settlements = []
        try:
            print("Fetching Settlements...")
            sett_resp = client.get_settlements(limit=50)
            for s in getattr(sett_resp, 'settlements', []):
                clean_settlements.append({
                    "ticker": getattr(s, 'ticker', ''),
                    "outcome": getattr(s, 'outcome', ''),
                    "received_cents": getattr(s, 'settlement_total', 0),
                    "settled_time": getattr(s, 'settled_time', '')
                })
        except Exception as e:
            final_data["debug_log"].append(f"Settlements Error: {str(e)}")

        # 6. CALCULATE & POPULATE
        cash = raw_bal / 100.0
        total = raw_port / 100.0
        bets = max(total - cash, 0.0)
        
        final_data["account"] = {
            "cash_balance": cash,
            "total_account_value": total,
            "money_in_bets": bets
        }
        final_data["summary"]["net_profit"] = total - 40.0
        final_data["summary"]["roi_percent"] = ((total - 40.0)/40.0)*100
        final_data["fills"] = clean_fills
        final_data["settlements"] = clean_settlements
        final_data["debug_log"].append("Success")
        
        print(f"Data process complete. Cash: {cash}, Total: {total}")

    except Exception as e:
        print("!!! SCRIPT CRASHED - WRITING ERROR LOG TO JSON !!!")
        traceback.print_exc()
        final_data["debug_log"].append(f"CRASH: {str(e)}")
        # We DO NOT exit(1) here because we want the file to be saved/committed
        # so you can see the error in the repo.

    # 7. ALWAYS SAVE THE FILE
    save_json(final_data)

if __name__ == "__main__":
    main()

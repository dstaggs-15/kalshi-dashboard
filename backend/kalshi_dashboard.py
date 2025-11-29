import os
import json
import datetime
import traceback

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(ROOT_DIR, "frontend", "data", "kalshi_summary.json")
TOTAL_DEPOSITS = 40.0  # adjust later when you add more money

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def serialize_dates(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)


def save_json(data):
    try:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=4, default=serialize_dates)
        print(f"SUCCESS: Wrote data to {OUTPUT_FILE}")
    except Exception as e:
        print(f"CRITICAL FILE SYSTEM ERROR: {e}")
        traceback.print_exc()


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    print("--- STARTING KALSHI PORTFOLIO SNAPSHOT ---")

    final_data = {
        "meta": {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "account": {
            "cash_balance": 0.0,
            "total_account_value": 0.0,        # our best estimate: cash + exposure
            "money_in_bets": 0.0,              # our best estimate: exposure
            "total_account_value_api": 0.0,    # raw from get_balance().portfolio_value
            "cash_balance_cents": 0,
            "portfolio_value_cents_api": 0,
            "positions_exposure_cents": 0,
        },
        "summary": {
            "total_deposits": TOTAL_DEPOSITS,
            "net_profit": 0.0,
            "roi_percent": 0.0,
        },
        "fills": [],
        "settlements": [],
        "positions": {
            "market_positions": [],
            "event_positions": [],
        },
        "raw": {
            "balance": {},
            "positions": {},
        },
        "debug_log": [],
    }

    try:
        from kalshi_python import KalshiClient, Configuration
    except Exception as e:
        print("Failed to import kalshi_python:", e)
        final_data["debug_log"].append(f"CRASH: kalshi_python import error: {e}")
        save_json(final_data)
        return

    try:
        # --------------------------------------------------------------
        # 1. LOAD SECRETS
        # --------------------------------------------------------------
        api_key_id = os.getenv("KALSHI_API_KEY_ID")
        private_key = os.getenv("KALSHI_PRIVATE_KEY")

        if not api_key_id:
            raise ValueError("Missing KALSHI_API_KEY_ID")
        if not private_key:
            raise ValueError("Missing KALSHI_PRIVATE_KEY")

        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")

        # --------------------------------------------------------------
        # 2. CONFIGURE SDK
        # --------------------------------------------------------------
        config = Configuration()
        config.host = "https://api.elections.kalshi.com/trade-api/v2"
        config.api_key_id = api_key_id
        config.private_key_pem = private_key

        client = KalshiClient(config)

        # --------------------------------------------------------------
        # 3. BALANCE
        # --------------------------------------------------------------
        print(f"Connecting to {config.host}...")
        balance = client.get_balance()
        final_data["debug_log"].append("SUCCESS: Authentication Passed")

        # Try to capture raw balance dict for later inspection
        try:
            if hasattr(balance, "to_dict"):
                final_data["raw"]["balance"] = balance.to_dict()
        except Exception as e:
            final_data["debug_log"].append(f"Balance raw serialization warning: {e}")

        raw_bal_cents = getattr(balance, "balance", 0) or 0
        raw_port_cents = getattr(balance, "portfolio_value", 0) or 0

        # Fallback: if portfolio_value is 0 but we have balance + collateral, approximate
        if raw_port_cents == 0 and raw_bal_cents > 0:
            raw_port_cents = raw_bal_cents + (getattr(balance, "collateral", 0) or 0)
            final_data["debug_log"].append(
                "portfolio_value was 0; used balance + collateral as fallback."
            )

        cash = raw_bal_cents / 100.0
        portfolio_api = raw_port_cents / 100.0

        # --------------------------------------------------------------
        # 4. POSITIONS
        # --------------------------------------------------------------
        positions_exposure_cents = 0
        market_positions_clean = []
        event_positions_clean = []
        positions_raw_dict = {}

        try:
            print("Fetching Positions...")
            positions_resp = client.get_positions(limit=200)

            # Raw positions dump for power-user debugging
            try:
                if hasattr(positions_resp, "to_dict"):
                    positions_raw_dict = positions_resp.to_dict()
            except Exception as e:
                final_data["debug_log"].append(
                    f"Positions raw serialization warning: {e}"
                )

            # Market-level positions
            for p in getattr(positions_resp, "market_positions", []) or []:
                ticker = getattr(p, "ticker", "")
                position = getattr(p, "position", 0) or 0
                exposure_cents = getattr(p, "market_exposure", 0) or 0
                total_traded = getattr(p, "total_traded", 0) or 0
                realized_pnl_cents = getattr(p, "realized_pnl", 0) or 0
                fees_paid_cents = getattr(p, "fees_paid", 0) or 0

                # Sum exposure across markets (this is "money at risk", not mark-to-market)
                if exposure_cents:
                    positions_exposure_cents += max(exposure_cents, 0)

                market_positions_clean.append(
                    {
                        "ticker": ticker,
                        "position": position,
                        "market_exposure_cents": exposure_cents,
                        "market_exposure_dollars": getattr(
                            p, "market_exposure_dollars", "0.00"
                        ),
                        "total_traded": total_traded,
                        "total_traded_dollars": getattr(
                            p, "total_traded_dollars", "0.00"
                        ),
                        "realized_pnl_cents": realized_pnl_cents,
                        "realized_pnl_dollars": getattr(
                            p, "realized_pnl_dollars", "0.00"
                        ),
                        "fees_paid_cents": fees_paid_cents,
                        "fees_paid_dollars": getattr(
                            p, "fees_paid_dollars", "0.00"
                        ),
                        "last_updated_ts": getattr(p, "last_updated_ts", None),
                    }
                )

            # Event-level positions (more aggregated view)
            for ep in getattr(positions_resp, "event_positions", []) or []:
                event_positions_clean.append(
                    {
                        "event_ticker": getattr(ep, "event_ticker", ""),
                        "total_traded": getattr(ep, "total_traded", 0) or 0,
                        "total_traded_dollars": getattr(
                            ep, "total_traded_dollars", "0.00"
                        ),
                        "realized_pnl_cents": getattr(ep, "realized_pnl", 0) or 0,
                        "realized_pnl_dollars": getattr(
                            ep, "realized_pnl_dollars", "0.00"
                        ),
                        "fees_paid_cents": getattr(ep, "fees_paid", 0) or 0,
                        "fees_paid_dollars": getattr(
                            ep, "fees_paid_dollars", "0.00"
                        ),
                        "last_updated_ts": getattr(ep, "last_updated_ts", None),
                    }
                )

        except Exception as e:
            final_data["debug_log"].append(f"Positions Warning: {e}")

        positions_exposure = positions_exposure_cents / 100.0

        # Our best estimate of "real" portfolio = cash + exposure
        # (this is not perfect mark-to-market, but closer to what you see in the app)
        estimated_total = cash + positions_exposure

        # --------------------------------------------------------------
        # 5. FILLS
        # --------------------------------------------------------------
        clean_fills = []
        try:
            print("Fetching Fills...")
            fills_resp = client.get_fills(limit=50)
            for f in getattr(fills_resp, "fills", []) or []:
                clean_fills.append(
                    {
                        "ticker": getattr(f, "ticker", "Unk"),
                        "side": getattr(f, "side", "Unk"),
                        "count": getattr(f, "count", 0),
                        "price_cents": getattr(f, "price", 0),
                        "price_dollars": f"{getattr(f, 'price', 0) / 100.0:.4f}",
                        "created_time": getattr(f, "created_time", ""),
                    }
                )
        except Exception as e:
            final_data["debug_log"].append(f"Fills Warning: {e}")

        # --------------------------------------------------------------
        # 6. SETTLEMENTS
        # --------------------------------------------------------------
        clean_settlements = []
        try:
            print("Fetching Settlements...")
            sett_resp = client.get_settlements(limit=50)
            for s in getattr(sett_resp, "settlements", []) or []:
                received_cents = getattr(s, "settlement_total", 0) or 0
                clean_settlements.append(
                    {
                        "ticker": getattr(s, "ticker", ""),
                        "outcome": getattr(s, "outcome", ""),
                        "received_cents": received_cents,
                        "received_dollars": f"{received_cents / 100.0:.2f}",
                        "settled_time": getattr(s, "settled_time", ""),
                    }
                )
        except Exception as e:
            final_data["debug_log"].append(f"Settlements Warning: {e}")

        # --------------------------------------------------------------
        # 7. POPULATE ACCOUNT + SUMMARY
        # --------------------------------------------------------------
        final_data["account"] = {
            # human-friendly
            "cash_balance": cash,
            "total_account_value": estimated_total,  # cash + exposure
            "money_in_bets": positions_exposure,

            # raw API numbers
            "cash_balance_cents": raw_bal_cents,
            "portfolio_value_cents_api": raw_port_cents,
            "total_account_value_api": portfolio_api,
            "positions_exposure_cents": positions_exposure_cents,
        }

        # Use our estimated total for P/L + ROI
        net_profit = estimated_total - TOTAL_DEPOSITS
        roi_percent = (net_profit / TOTAL_DEPOSITS * 100.0) if TOTAL_DEPOSITS > 0 else 0.0

        final_data["summary"] = {
            "total_deposits": TOTAL_DEPOSITS,
            "net_profit": net_profit,
            "roi_percent": roi_percent,
        }

        final_data["fills"] = clean_fills
        final_data["settlements"] = clean_settlements
        final_data["positions"]["market_positions"] = market_positions_clean
        final_data["positions"]["event_positions"] = event_positions_clean
        final_data["raw"]["positions"] = positions_raw_dict

        final_data["debug_log"].append(
            f"Completed snapshot. Cash=${cash:.2f}, "
            f"API_portfolio=${portfolio_api:.2f}, "
            f"Exposure≈${positions_exposure:.2f}, "
            f"Estimated_total≈${estimated_total:.2f}"
        )

        print(
            f"DONE. Cash: ${cash:.2f}, API_portfolio: ${portfolio_api:.2f}, "
            f"Exposure≈${positions_exposure:.2f}, Estimated_total≈${estimated_total:.2f}"
        )

    except Exception as e:
        print("!!! SCRIPT CRASHED - WRITING ERROR LOG !!!")
        traceback.print_exc()
        final_data["debug_log"].append(f"CRASH: {str(e)}")

    save_json(final_data)


if __name__ == "__main__":
    main()

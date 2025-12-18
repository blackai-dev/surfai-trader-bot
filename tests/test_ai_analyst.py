from ai_analyst import AIAnalyst
from market_data import MarketData
import json

def test_ai_analyst():
    # 1. Fetch real data first to make it realistic
    md = MarketData()
    print("Fetching market data...")
    candles = md.get_ohlcv("PERP_ETH_USDC", limit=20)
    
    if not candles:
        print("Failed to fetch candles, cannot test AI.")
        return

    # 2. Initialize AI
    ai = AIAnalyst()
    print("Sending data to Surf AI...")
    
    # 3. Analyze
    signal = ai.analyze_market(candles)
    
    print("\n--- AI Signal ---")
    print(json.dumps(signal, indent=2))

if __name__ == "__main__":
    test_ai_analyst()

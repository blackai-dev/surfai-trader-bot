
from market_data import MarketData
import time

def test_sol_data():
    md = MarketData()
    print("Testing get_orderbook for PERP_SOL_USDC...")
    try:
        ob = md.get_orderbook("PERP_SOL_USDC")
        if ob and 'asks' in ob:
            print(f"✅ Orderbook Success: Asks={len(ob['asks'])}, Bids={len(ob['bids'])}")
            print(f"   Best Ask: {ob['asks'][0]['price']}")
        else:
            print(f"❌ Orderbook Empty or Invalid: {ob}")
    except Exception as e:
        print(f"❌ Orderbook Error: {e}")

    print("\nTesting Fallback (get_ohlcv last close)...")
    try:
        candles = md.get_ohlcv("PERP_SOL_USDC", "1m", limit=1)
        if candles:
            close = candles[-1]['close']
            print(f"✅ Fallback Success: Last Close = {close}")
        else:
            print("❌ Fallback Empty")
    except Exception as e:
        print(f"❌ Fallback Error: {e}")

if __name__ == "__main__":
    test_sol_data()

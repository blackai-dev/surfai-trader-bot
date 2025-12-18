from market_data import MarketData
import json

def test_market_data():
    md = MarketData()
    
    print("Testing get_ohlcv...")
    try:
        candles = md.get_ohlcv("PERP_ETH_USDC")
        print(f"Candles type: {type(candles)}")
        with open("debug_candles.txt", "w") as f:
            f.write(str(candles))
        print("Written to debug_candles.txt")
    except Exception as e:
        print(f"get_ohlcv failed: {e}")

    print("\nTesting get_orderbook...")
    try:
        ob = md.get_orderbook("PERP_ETH_USDC")
        print(f"Orderbook received: {'Yes' if ob else 'No'}")
    except Exception as e:
        print(f"get_orderbook failed: {e}")

if __name__ == "__main__":
    test_market_data()

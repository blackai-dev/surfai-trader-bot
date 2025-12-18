from market_data import MarketData
import datetime

md = MarketData()
symbol = "PERP_ETH_USDC"

print(f"🔍 Fetching last 10 15m candles for {symbol}...")
try:
    candles = md.get_ohlcv(symbol, "15m", 10)
    print(f"{'Time (Local)':<25} | {'Open':<10} | {'High':<10} | {'Low':<10} | {'Close':<10}")
    print("-" * 75)
    for c in candles:
        # Timestamp is usually unix ms
        ts_ms = c.get('start_timestamp', 0)
        dt = datetime.datetime.fromtimestamp(ts_ms / 1000)
        print(f"{str(dt):<25} | {c['open']:<10} | {c['high']:<10} | {c['low']:<10} | {c['close']:<10}")
except Exception as e:
    print(f"❌ Error: {e}")

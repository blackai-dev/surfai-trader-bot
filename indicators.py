
def calculate_sma(prices, period):
    """
    Calculates Simple Moving Average (SMA) for a list of prices.
    Returns None if not enough data.
    """
    if len(prices) < period:
        return None
    
    # We only need the latest SMA for the prompt context
    # Usually strategy needs the lateset value
    selection = prices[-period:]
    return sum(selection) / period

def calculate_indicators(candles):
    """
    Takes raw candle data and calculates MA30, MA45, MA60.
    """
    closes = [float(c['close']) for c in candles]
    
    import config
    
    ma_short = calculate_sma(closes, config.MA_SHORT)
    ma_medium = calculate_sma(closes, config.MA_MEDIUM)
    ma_long = calculate_sma(closes, config.MA_LONG)
    
    return {
        "MA_SHORT": ma_short,
        "MA_MEDIUM": ma_medium,
        "MA_LONG": ma_long,
        "current_price": closes[-1] if closes else 0
    }

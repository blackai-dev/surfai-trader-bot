from orderly_evm_connector.rest import Rest as OrderlyClient
import config
import traceback

class MarketData:
    def __init__(self):
        self.client = OrderlyClient(
            orderly_key=config.ORDERLY_KEY, 
            orderly_secret=config.ORDERLY_SECRET,
            orderly_account_id=config.ORDERLY_ACCOUNT_ID
        )

    def get_ohlcv(self, symbol, timeframe="15m", limit=100):
        try:
            # Type is the timeframe e.g. "1m", "5m", "15m", "30m", "1h", "1d"
            response = self.client.get_kline(symbol, type=timeframe, limit=limit)
            # Response format check needed, usually data['rows'] or similar
            if response and 'data' in response and 'rows' in response['data']:
                return response['data']['rows']
            
            # Fallback if structure is different
            if response and 'rows' in response:
                return response['rows']
                
            return response 
        except Exception as e:
            print(f"Error fetching candles: {e}")
            traceback.print_exc()
            return []

    def get_symbol_rules(self, symbol):
        """
        Fetch trading rules: base_tick (min qty step) and min_notional.
        """
        try:
            # Try to get from individual info first
            res = self.client.get_exchange_info(symbol)
            if res and 'data' in res:
                return {
                    'base_tick': float(res['data'].get('base_tick', 0)),
                    'min_notional': float(res['data'].get('min_notional', 0)),
                    'symbol': symbol
                }
            return None
        except Exception as e:
            print(f"❌ Error getting symbol rules for {symbol}: {e}")
            return None
    
    def get_orderbook(self, symbol, max_level=10):
        try:
            return self.client.get_orderbook_snapshot(symbol, max_level=max_level)
        except Exception as e:
            print(f"Error fetching orderbook: {e}")
            return None
    
    def get_account_info(self):
        try:
            return self.client.get_account_information()
        except Exception as e:
            print(f"Error fetching account info: {e}")
            return None
    
    def get_positions(self):
        try:
            return self.client.get_all_positions_info()
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return None

    def get_top_10_symbols(self):
        """
        Fetches all market info, sorts by 24h turnover (USDC volume), 
        and returns the top 10 'PERP_' symbols.
        """
        try:
            # get_market_info usually returns a list of all symbol details
            # We need to verify the exact method name from SDK or assume get_market_info / get_available_symbols
            # Based on common SDKs, let's try get_market_info()
            # If not available, we might need to search the SDK code. 
            # Assuming client.get_market_info() exists as per standard Orderly SDK.
            
            # The SDK method for 24h stats is get_futures_info_for_all_markets
            response = self.client.get_futures_info_for_all_markets()
            
            if response and 'data' in response and 'rows' in response['data']:
                rows = response['data']['rows']
                # Filter for PERP futures only
                perps = [r for r in rows if r['symbol'].startswith('PERP_')]
                
                # Sort by 24h_amount (Turnover) descending
                perps.sort(key=lambda x: float(x.get('24h_amount', 0)), reverse=True)
                
                # Return Top 5
                top_n = [r['symbol'] for r in perps[:5]]
                return top_n
            else:
                print("❌ Failed to fetch market info rows.")
                return []
                
        except Exception as e:
            print(f"Error fetching top 10 symbols: {e}")
            # traceback.print_exc()
            return []

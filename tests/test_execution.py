
import unittest
from unittest.mock import MagicMock
import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution import Execution
import config

class TestExecution(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_db = MagicMock()
        self.execution = Execution(self.mock_client, self.mock_db)
        
        # Mock exchange info response
        self.mock_client.get_exchange_info.return_value = {
            "success": True,
            "data": {
                "base_tick": 0.01,
                "min_notional": 10.0
            }
        }

    def test_calculate_quantity_and_order(self):
        # Setup specific test case
        # Config: 10 USDC per trade
        # Price: 125.0
        # Expected Qty: 10 / 125 = 0.08
        config.POSITION_SIZE_USDC = 10.0
        
        signal = {
            "action": "SELL",
            "confidence": 0.8,
            "entry_price": 125.0, # Ensures clean division
            "log_id": "test_log_123"
        }
        
        symbol = "PERP_SOL_USDC"
        
        # Execute
        self.execution.execute_trade(signal, symbol)
        
        # Verify order call arguments
        self.mock_client.create_order.assert_called_once()
        call_args = self.mock_client.create_order.call_args[1]
        
        self.assertEqual(call_args['symbol'], symbol)
        self.assertEqual(call_args['side'], "SELL")
        self.assertEqual(call_args['order_type'], "MARKET")
        self.assertEqual(call_args['order_quantity'], 0.08) # Verify variable name & value logic
        
        print("\n✅ Test Passed: execute_trade calls client.order with correct 'order_quantity'")

    def test_monitor_risks(self):
        # Override config to match test expectation (TP=4%)
        
        # Override config.TP_PERCENT to match test expectation (TP=4%)
        # Current config might be 30% which won't trigger close in this test.
        old_tp = config.TP_PERCENT
        config.TP_PERCENT = 0.04
        self.addCleanup(lambda: setattr(config, 'TP_PERCENT', old_tp))

        # Setup
        mock_md = MagicMock()
        
        # Ensure db returns default state (no history) for this test
        # We need to set this on self.mock_db which is passed to Execution
        self.mock_db.get_open_trade_state.return_value = (None, 0, 0, None)
        
        # Scenario: 
        # 1. ETH Long Entry 3000. Current 3300 (+10% > 4% TP). Should Trigger TP.
        # ...
        positions = [
            {'symbol': 'PERP_ETH_USDC', 'position_qty': 0.1, 'average_open_price': 3000.0},
            {'symbol': 'PERP_SOL_USDC', 'position_qty': 10.0, 'average_open_price': 100.0},
            {'symbol': 'PERP_DOGE_USDC', 'position_qty': 1000.0, 'average_open_price': 0.10} 
        ]
        
        # Mock get_orderbook to return dynamic prices (Real API Structure)
        def side_effect(symbol, max_level=10):
            if symbol == 'PERP_ETH_USDC':
                return {'data': {'asks': [{'price': 3300}], 'bids': [{'price': 3300}]}} 
            elif symbol == 'PERP_SOL_USDC':
                return {'data': {'asks': [{'price': 101}], 'bids': [{'price': 101}]}} 
            elif symbol == 'PERP_DOGE_USDC':
                return {'data': {'asks': [{'price': 0.09}], 'bids': [{'price': 0.09}]}} 
            return None
        mock_md.get_orderbook.side_effect = side_effect
        
        # Mock close_position
        self.execution.close_position = MagicMock()
        self.execution.close_position.return_value = ({'success': True}, 3000.0) # Mock return (response, price)
        
        # Execute
        self.execution.monitor_risks(positions, mock_md)
        
        # Verify
        self.execution.close_position.assert_any_call('PERP_ETH_USDC', 0.1, 'SELL')
        self.execution.close_position.assert_any_call('PERP_DOGE_USDC', 1000.0, 'SELL')
        self.assertEqual(self.execution.close_position.call_count, 2)
        print("\n✅ Test Passed: monitor_risks triggers TP for ETH, SL for DOGE, holds SOL")
        
        print("\n✅ Test Passed: monitor_risks triggers TP for ETH, SL for DOGE, holds SOL")

    def test_monitor_risks_retry_fallback(self):
        # Override config for this test too if needed, or ensure price movt is huge
        # Scenario: Entry 100, Price 105. Gain 5%. If TP is 30%, no close.
        # Override config for this test too if needed, or ensure price movt is huge
        # Scenario: Entry 100, Price 105. Gain 5%. If TP is 30%, no close.
        old_tp = config.TP_PERCENT
        config.TP_PERCENT = 0.04
        self.addCleanup(lambda: setattr(config, 'TP_PERCENT', old_tp))

        # Scenario: Orderbook fails (network error), Fallback succeeds
        mock_md = MagicMock()
        self.mock_db.get_open_trade_state.return_value = (None, 0, 0, None) # Default
        
        mock_md.get_orderbook.side_effect = Exception("Network Timeout")
        mock_md.get_ohlcv.return_value = [{'close': 105.0}]
        
        positions = [{'symbol': 'PERP_SOL_USDC', 'position_qty': 10.0, 'average_open_price': 100.0}]
        
        self.execution.close_position = MagicMock()
        self.execution.close_position.return_value = ({'success': True}, 100.0)
        
        # Execute
        self.execution.monitor_risks(positions, mock_md)
        
        # Verify
        self.assertEqual(mock_md.get_orderbook.call_count, 3)
        mock_md.get_ohlcv.assert_called_once_with('PERP_SOL_USDC', timeframe='1m', limit=1)
        self.execution.close_position.assert_called_once()
        print("\n✅ Test Passed: monitor_risks successfully falls back to OHLCV on error")
        
    def test_trailing_stop_ratchet(self):
        # Verify Stateful Logic for both LONG and SHORT
        mock_md = MagicMock()
        
        # Scenario 1: LONG RATCHET
        # Entry 100. Historic High (HWM) 103 (+3%). 
        # Triggered Tier 2 (Lock 1.5% Profit) -> SL = 101.5.
        # Current Price drops to 101.0.
        # 101.0 < 101.5 -> MUST CLOSE. (If stateless, 101 is +1% profit -> Hold).
        
        # Scenario 2: SHORT RATCHET
        # Entry 100. Historic Low (HWM) 97 (+3% profit).
        # Triggered Tier 2 (Lock 1.5% Profit) -> SL = 98.5.
        # Current Price rises to 99.0.
        # 99.0 > 98.5 -> MUST CLOSE. (If stateless, 99 is +1% profit -> Hold).
        
        positions = [
            {'symbol': 'PERP_LONG_TEST', 'position_qty': 10.0, 'average_open_price': 100.0},
            {'symbol': 'PERP_SHORT_TEST', 'position_qty': -10.0, 'average_open_price': 100.0}
        ]
        
        # Mock Prices: Long=101, Short=99
        def price_side_effect(symbol, max_level=10):
            if symbol == 'PERP_LONG_TEST':
                return {'data': {'asks': [{'price': 101.0}], 'bids': [{'price': 101.0}]}}
            elif symbol == 'PERP_SHORT_TEST':
                return {'data': {'asks': [{'price': 99.0}], 'bids': [{'price': 99.0}]}}
            return None
        mock_md.get_orderbook.side_effect = price_side_effect
        
        # Mock DB HWM: Long=103, Short=97
        def db_side_effect(symbol):
            if symbol == 'PERP_LONG_TEST':
                # log_id, highest_price, entry, time
                return ('log_1', 103.0, 100.0, None) 
            elif symbol == 'PERP_SHORT_TEST':
                # log_id, highest_price (lowest), entry
                return ('log_2', 97.0, 100.0, None)
            return (None, 0, 0, None)
        self.mock_db.get_open_trade_state.side_effect = db_side_effect
        
        # Explicitly mock close_position again
        self.execution.close_position = MagicMock()
        self.execution.close_position.return_value = ({'success': True}, 100.0)
        
        # Execute
        self.execution.monitor_risks(positions, mock_md)
        
        # Verify
        self.execution.close_position.assert_any_call('PERP_LONG_TEST', 10.0, 'SELL')
        self.execution.close_position.assert_any_call('PERP_SHORT_TEST', 10.0, 'BUY')
        self.assertEqual(self.execution.close_position.call_count, 2)
        print("\n✅ Test Passed: Stateful Ratchet works for BOTH Long and Short")

if __name__ == '__main__':
    unittest.main()


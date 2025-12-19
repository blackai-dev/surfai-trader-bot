import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent dir to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from execution import Execution

class TestExecution(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_client = MagicMock()
        self.mock_db = MagicMock()
        self.mock_md = MagicMock()
        
        # Initialize Execution module with mocks
        self.exec_mod = Execution(self.mock_client, self.mock_db)
        
        # Setup config constants for testing to ensure deterministic behavior
        self.original_config_vals = {
            'TP_PERCENT': config.TP_PERCENT,
            'TS_ACTIVATION_2': config.TS_ACTIVATION_2,
            'TS_DYNAMIC_CALLBACK': config.TS_DYNAMIC_CALLBACK,
            'TS_ACTIVATION_1': config.TS_ACTIVATION_1,
            'TS_LOCK_1': config.TS_LOCK_1
        }
        
        # Enforce the config values we want to test
        config.TP_PERCENT = 0.30
        config.TS_ACTIVATION_2 = 0.025 # 2.5% Target
        config.TS_DYNAMIC_CALLBACK = 0.015
        
    def tearDown(self):
        # Restore config
        for k, v in self.original_config_vals.items():
            setattr(config, k, v)

    def test_trailing_stop_tier_2_trigger_long(self):
        """
        Verify that hitting 2.5% profit triggers Tier 2 TS logic, 
        and a subsequent drop triggers a close.
        """
        symbol = "PERP_BTC_USDC"
        entry_price = 1000.0
        qty = 0.1
        
        # Scene 1: Position is OPEN, Current Price = Entry
        # PnL = 0%
        pos = {
            'symbol': symbol,
            'position_qty': qty, # LONG
            'average_open_price': entry_price
        }
        
        # Mock DB to return clean state (no previous HWM)
        # return (log_id, hwm_price, db_entry, entry_time)
        self.mock_db.get_open_trade_state.return_value = ("log_123", 1000.0, 1000.0, None)
        
        # Update HWM call
        self.mock_db.update_highest_price = MagicMock()
        
        # Close Position call
        self.exec_mod.close_position = MagicMock(return_value=({'success': True}, 1010.0))
        
        # --- Step 1: Market moves to 1025 (2.5% Profit) ---
        # This should UPDATE HWM to 1025.
        
        # Mock Market Data to return 1025
        # Structure: {'data': {'asks': [{'price': 1025}], 'bids': [{'price': 1025}]}}
        self.mock_md.get_orderbook.return_value = {
            'data': {
                'asks': [{'price': 1025}],
                'bids': [{'price': 1025}]
            }
        }
        
        # Run Monitor
        with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
            self.exec_mod.monitor_risks([pos], self.mock_md)
            
            # Verify DB HWM Update was called with 1025
            self.mock_db.update_highest_price.assert_called()
            # Check args: (log_id, new_hwm)
            args, _ = self.mock_db.update_highest_price.call_args
            self.assertEqual(args[1], 1025.0)
            
            # Verify NO close happened yet (Stop shouldn't be hit at peak)
            self.exec_mod.close_position.assert_not_called()

        # --- Step 2: Market drops to 1009 (Below Ratchet) ---
        # Calculation:
        # HWM = 1025
        # Callback = 1.5% (0.015)
        # Activation Threshold = 1025 * (1 - 0.015) = 1025 * 0.985 = 1009.625
        # Current Price 1009 < 1009.625 -> SHOULD CLOSE
        
        # Update DB Mock to reflect the new HWM recorded in Step 1
        self.mock_db.get_open_trade_state.return_value = ("log_123", 1025.0, 1000.0, None)
        
        # Mock Market Data to return 1009
        self.mock_md.get_orderbook.return_value = {
            'data': {
                'asks': [{'price': 1009}],
                'bids': [{'price': 1009}]
            }
        }
        
        # Run Monitor
        with patch('sys.stdout', new_callable=MagicMock) as mock_stdout:
            self.exec_mod.monitor_risks([pos], self.mock_md)
            
            # Verify Close Position CALLED
            self.exec_mod.close_position.assert_called_with(symbol, qty, "SELL")
            
            # Verify Log Message (Optional, good for debugging)
            # We can inspect print output if needed, but assertion is stronger
            
    def test_trailing_stop_tier_2_trigger_short(self):
        """
        Verify TS Tier 2 for SHORT position.
        """
        symbol = "PERP_BTC_USDC"
        entry_price = 1000.0
        qty = -0.1 # SHORT
        
        pos = {
            'symbol': symbol,
            'position_qty': qty,
            'average_open_price': entry_price
        }
        
        # Initial State: HWM = Entry (Low price for short)
        self.mock_db.get_open_trade_state.return_value = ("log_123", 1000.0, 1000.0, None)
        self.mock_db.update_highest_price = MagicMock()
        self.exec_mod.close_position = MagicMock(return_value=({'success': True}, 990.0))
        
        # --- Step 1: Market moves to 975 (2.5% Profit for Short) ---
        # (1000 - 975) / 1000 = 25 / 1000 = 2.5%
        
        self.mock_md.get_orderbook.return_value = {
            'data': {'asks': [{'price': 975}], 'bids': [{'price': 975}]}
        }
        
        self.exec_mod.monitor_risks([pos], self.mock_md)
        
        # Verify HWM Update (Lowest Price)
        args, _ = self.mock_db.update_highest_price.call_args
        self.assertEqual(args[1], 975.0)
        self.exec_mod.close_position.assert_not_called()
        
        # --- Step 2: Market bounces to 990 (Callback) ---
        # HWM = 975
        # Callback = 1.5%
        # Trigger = 975 * (1 + 0.015) = 975 * 1.015 = 989.625
        # Price 990 > 989.625 -> SHOULD CLOSE
        
        self.mock_db.get_open_trade_state.return_value = ("log_123", 975.0, 1000.0, None)
        self.mock_md.get_orderbook.return_value = {
            'data': {'asks': [{'price': 990}], 'bids': [{'price': 990}]}
        }
        
        self.exec_mod.monitor_risks([pos], self.mock_md)
        
        self.exec_mod.close_position.assert_called_with(symbol, 0.1, "BUY")

if __name__ == '__main__':
    unittest.main()

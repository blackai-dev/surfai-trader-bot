import unittest
from unittest.mock import MagicMock
import datetime
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from execution import Execution

class TestDualTrackStrategy(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_db = MagicMock()
        self.mock_ai = MagicMock()
        self.mock_md = MagicMock()
        self.exec_engine = Execution(self.mock_client, self.mock_db)
        
        # Default Logic: Tier 2 starts at 3.0%, Ratchet distance 1.5%
        # So if HWM = 100, PnL% = (100-Entry)/Entry
    
    def test_dynamic_ratchet_long_tier2(self):
        """Test LONG Dynamic Ratchet when PnL > 3.0%"""
        symbol = "PERP_ETH_USDC"
        entry_price = 100.0
        # HWM = 105.0 (+5% profit), clearly > 3% Tier 2
        hwm_price = 105.0 
        current_price = 104.0
        
        # effective_sl should be HWM * (1 - 0.015) = 105 * 0.985 = 103.425
        expected_sl = hwm_price * (1 - config.TS_DYNAMIC_CALLBACK)
        
        # We can't easily test internal variables of a massive function like monitor_risks without refactoring.
        # But we can verify the LOGIC if we extract it, or we rely on 'monitor_risks' behavior (calling close_position if price hits SL).
        # Let's test boundary: Set current_price BELOW expected_sl and see if it closes.
        
        # Setup DB State
        # get_open_trade_state returns: log_id, hwm, db_entry, entry_time
        self.mock_db.get_open_trade_state.return_value = ("log_123", hwm_price, entry_price, datetime.datetime.now())
        
        # Position Data
        positions = [{
            'symbol': symbol,
            'position_qty': 1.0, # LONG
            'average_open_price': entry_price,
            'mark_price': 103.0 # Below expected SL (103.425)
        }]
        
        # Mock fetch price (fallback)
        self.mock_md.get_ohlcv.return_value = [{'close': 103.0}]

        # Capture print output? Or mock close_position
        self.exec_engine.close_position = MagicMock()
        self.exec_engine.close_position.return_value = ({'success': True}, 103.0)
        
        # Run
        # We manually trigger logic by mocking current_price inside monitor_risks via get_ohlcv? 
        # Actually monitor_risks uses 'mark_price' from position if not, falls back.
        # Wait, monitor_risks calls md.get_ohlcv(1m) to get current_price.
        
        self.exec_engine.monitor_risks(positions, self.mock_md)
        
        # Assert
        # Should initiate close because 103.0 < 103.425
        self.exec_engine.close_position.assert_called_with(symbol, 1.0, "SELL")
        print("\n✅ Test Dynamic Ratchet LONG: Triggered correctly.")

    def test_stale_position_check_trigger(self):
        """Test Stale Check triggers AI when > 12h and Low PnL"""
        symbol = "PERP_BTC_USDC"
        entry_price = 50000.0
        current_price = 50500.0 # +1% (Tier 1, not Tier 2)
        
        # 13 hours ago (UTC naive)
        entry_time = datetime.datetime.now() - datetime.timedelta(hours=13)
        self.mock_db.get_open_trade_state.return_value = ("log_abc", 50500.0, entry_price, entry_time)
        
        positions = [{
            'symbol': symbol,
            'position_qty': 0.5,
            'average_open_price': entry_price,
            'mark_price': current_price
        }]
        
        # Mock AI to say "CLOSE"
        self.mock_ai.evaluate_stale_position.return_value = "CLOSE"
        # Mock AI to say "CLOSE"
        self.mock_ai.evaluate_stale_position.return_value = "CLOSE"
        self.exec_engine.close_position = MagicMock()
        self.exec_engine.close_position.return_value = ({'success': True}, current_price)

        # Run
        self.exec_engine.check_stale_positions(positions, self.mock_md, self.mock_ai)
        
        # Assert
        self.mock_ai.evaluate_stale_position.assert_called()
        self.exec_engine.close_position.assert_called_with(symbol, 0.5, "SELL")
        print("\n✅ Test Stale Check: Detected >12h and triggered AI Close.")

    def test_stale_position_ignore_winner(self):
        """Test Stale Check IGNORES > 12h trade if it is a BIG WINNER (>3%)"""
        symbol = "PERP_SOL_USDC"
        entry_price = 100.0
        current_price = 110.0 # +10% (Tier 2!!)
        
        entry_time = datetime.datetime.now() - datetime.timedelta(hours=20) # Very old
        self.mock_db.get_open_trade_state.return_value = ("log_xyz", 110.0, entry_price, entry_time)
        
        positions = [{
            'symbol': symbol,
            'position_qty': 10.0,
            'average_open_price': entry_price,
            'mark_price': current_price
        }]
        
        self.exec_engine.check_stale_positions(positions, self.mock_md, self.mock_ai)
        
        # Assert
        self.mock_ai.evaluate_stale_position.assert_not_called()
        print("\n✅ Test Stale Check: Ignored Winner (Let it Run).")

if __name__ == '__main__':
    unittest.main()

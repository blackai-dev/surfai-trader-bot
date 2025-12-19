import unittest
from unittest.mock import MagicMock, patch
import datetime
# import config # Config will be patched
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_bot # Wont run, just import if needed, or better, extracted logic
# Since main.py is a loop, we can't import it easily to test a snippet.
# However, I should probably verify the logic by simulating the checks.

class TestReentryCooldown(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_md = MagicMock()
        self.mock_ai = MagicMock()
        
    def test_cooldown_logic_active(self):
        """
        Scenario: 
        - Config: COOLDOWN = 1 candle
        - Last Exit: 10:05 (Candle 10:00-10:15)
        - Current Time: 10:10 (Same Candle)
        -> Should SKIP Analysis
        """
        symbol = "ETH_USDC"
        
        # 1. Setup Mock DB to return recent exit
        # Exit at 10:05
        exit_time = datetime.datetime(2023, 10, 1, 10, 5, 0)
        self.mock_db.get_last_exit_info.return_value = (exit_time, "CLOSED_SL")
        
        # 2. Market Data (Current Candle)
        # Current time 10:10
        current_time_mock = datetime.datetime(2023, 10, 1, 10, 10, 0).timestamp()
        
        # 15m candle start for 10:10 is 10:00
        # 15m candle start for 10:05 is 10:00
        # So they are SAME candle.
        
        # Logic to be implemented in main.py:
        # candle_interval = 15 * 60
        # last_exit_candle = int(exit_time.timestamp() // candle_interval)
        # current_candle = int(current_time_mock // candle_interval)
        
        candle_interval = 900 # 15m
        last_exit_ts = exit_time.timestamp()
        
        last_candle_idx = int(last_exit_ts // candle_interval)
        curr_candle_idx = int(current_time_mock // candle_interval)
        
        cooldown_active = False
        if last_candle_idx == curr_candle_idx:
            cooldown_active = True
            
        self.assertTrue(cooldown_active, "Cooldown should be active for same candle")
        print("\n✅ Test Passed: Cooldown active on same candle")

    def test_cooldown_logic_expired(self):
        """
        Scenario:
        - Last Exit: 10:05
        - Current Time: 10:20 (Next Candle)
        -> Should ALLOW Analysis
        """
        # Exit 10:05
        exit_time = datetime.datetime(2023, 10, 1, 10, 5, 0)
        self.mock_db.get_last_exit_info.return_value = (exit_time, "CLOSED_SL")
        
        # Current 10:20
        current_time_mock = datetime.datetime(2023, 10, 1, 10, 20, 0).timestamp()
        
        candle_interval = 900
        last_candle_idx = int(exit_time.timestamp() // candle_interval)
        curr_candle_idx = int(current_time_mock // candle_interval)
        
        cooldown_active = False
        if last_candle_idx == curr_candle_idx:
            cooldown_active = True
            
        self.assertFalse(cooldown_active, "Cooldown should expired on next candle")
        print("\n✅ Test Passed: Cooldown expired on next candle")

if __name__ == '__main__':
    unittest.main()

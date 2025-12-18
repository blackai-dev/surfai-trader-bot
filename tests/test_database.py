import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import datetime

# Add parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseHandler

class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Mock psycopg2 connection
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        
        # Instantiate DB with mocked connection hook
        # Since DatabaseHandler connects in __init__, we need to patch connect
        with patch('psycopg2.connect', return_value=self.mock_conn):
             self.db = DatabaseHandler()
             self.db.conn = self.mock_conn # Ensure it's set

    def test_get_open_trade_state_success(self):
        # Setup Mock Return
        # log_id, highest_price, entry_price, timestamp
        now = datetime.datetime.now()
        self.mock_cursor.fetchone.return_value = ('log_123', 3000.0, 2900.0, now)
        
        # Execute
        log_id, hwm, entry, time = self.db.get_open_trade_state('PERP_ETH_USDC')
        
        # Verify
        self.assertEqual(log_id, 'log_123')
        self.assertEqual(hwm, 3000.0)
        self.assertEqual(entry, 2900.0)
        self.assertEqual(time, now)
        
        self.assertEqual(time, now)
        
        # We can't use assert_called_once because init calls execute too
        # Verify the SELECT query was one of the calls
        found_select = False
        for call in self.mock_cursor.execute.call_args_list:
             if "SELECT log_id" in call[0][0]:
                 found_select = True
                 break
        self.assertTrue(found_select, "SELECT query not found in cursor calls")
        print("\n✅ Test Passed: get_open_trade_state returns 4 values correctly")

    def test_get_open_trade_state_empty(self):
        self.mock_cursor.fetchone.return_value = None
        
        log_id, hwm, entry, time = self.db.get_open_trade_state('PERP_sol_USDC')
        
        self.assertIsNone(log_id)
        self.assertEqual(hwm, 0)
        self.assertEqual(time, None)
        print("\n✅ Test Passed: get_open_trade_state returns default Tuple on empty")

    def test_update_entry_price(self):
        log_id = 'log_999'
        new_price = 3019.0
        
        self.db.update_entry_price(log_id, new_price)
        
        # Verify SQL
        self.mock_cursor.execute.assert_called()
        call_args = self.mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        self.assertIn("UPDATE trade_logs", sql)
        self.assertIn("entry_price = %s", sql)
        self.assertIn("highest_price = %s", sql) # Should verify sync
        self.assertEqual(params, (new_price, new_price, log_id))
        print("\n✅ Test Passed: update_entry_price updates both entry and HWM")

if __name__ == '__main__':
    unittest.main()

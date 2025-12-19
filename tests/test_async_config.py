import pytest
import psycopg2
from database import DatabaseHandler
import config

class TestAsyncConfig:
    @pytest.fixture
    def db(self):
        """Setup independent DB connection for testing"""
        handler = DatabaseHandler()
        # Ensure table exists
        handler.init_db()
        return handler

    def test_config_roundtrip(self, db):
        """
        Test Protocol:
        1. TG Bot sets a value (set_config)
        2. Main Loop reads value (get_config)
        3. Verify integrity
        """
        # 1. Simulate TG Bot setting size to 50
        key = "test_position_size"
        val = "50.0"
        
        # Write
        assert db.set_config(key, val) == True
        
        # 2. Simulate Main Loop reading
        read_val = db.get_config(key, default="30.0")
        
        # 3. Verify
        assert read_val == val
        assert float(read_val) == 50.0

    def test_config_update(self, db):
        """
        Test Protocol:
        1. Set initial value
        2. Set NEW value (Update)
        3. Verify Main Loop gets the NEW value (Not old cached one)
        """
        key = "test_is_paused"
        
        # Initial: Start
        db.set_config(key, "false")
        assert db.get_config(key) == "false"
        
        # Action: Stop
        db.set_config(key, "true")
        
        # Verify
        assert db.get_config(key) == "true"

    def test_main_loop_logic_simulation(self, db):
        """
        Simulate the exact try-except block in main.py logic
        to ensure it handles data types correctly.
        """
        # Test Case 1: Valid Float
        db.set_config("position_size", "100.5")
        size_str = db.get_config("position_size", "30.0")
        
        # Simulation of main.py lines 68-70
        try:
            main_loop_val = float(size_str)
        except:
            main_loop_val = 30.0 # Default
            
        assert main_loop_val == 100.5
        
        # Test Case 2: Invalid Data (Garbage from DB)
        db.set_config("position_size", "JunkData")
        size_str = db.get_config("position_size", "30.0")
        
        try:
            main_loop_val = float(size_str)
        except:
            main_loop_val = 30.0 # Default fallback
            
        # Should fallback to default (or stay previous value in real app), here we assert fail-safe
        assert main_loop_val == 30.0 # Verify fallback works


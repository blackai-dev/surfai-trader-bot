import os
from dotenv import load_dotenv

load_dotenv()

# Trading Config
SYMBOL = "PERP_ETH_USDC" # Default Symbol
ENABLE_TOP_10 = True     # Disable by default for safety, Enable scan multi tokens
MAX_OPEN_POSITIONS = 3 

# Position Sizing
POSITION_SIZE_USDC = 30.0 # Trade size in USDC
# MAX_POSITION_SIZE = 0.01 # Deprecated

INTERVAL = 300 # 5 minutes (Check 3 times per 15m candle) in seconds

# API Keys (Loaded from env for security)
ORDERLY_KEY = os.getenv("ORDERLY_KEY")
ORDERLY_SECRET = os.getenv("ORDERLY_SECRET")
if ORDERLY_SECRET and not ORDERLY_SECRET.startswith("ed25519:"):
    ORDERLY_SECRET = f"ed25519:{ORDERLY_SECRET}"

ORDERLY_ACCOUNT_ID = os.getenv("ORDERLY_ACCOUNT_ID")
ASKSURF_API_KEY = os.getenv("ASKSURF_API_KEY")

# Telegram Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# DB Config
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "mydb")
DB_USER = os.getenv("DB_USER", "myuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "mypassword")

# Risk Config


# Risk Management
TP_PERCENT = 0.30  # 30%
SL_PERCENT = 0.02  # 2% or 10% (adjust based on leverage)

# Advanced Strategy Settings
MA_SHORT = 30
MA_MEDIUM = 45
MA_LONG = 60

# Stepped Trailing Stop Settings
TS_ACTIVATION_1 = 0.015 # 1.5% profit triggers Tier 1
TS_LOCK_1 = 0.002       # Lock 0.2% profit (Cover Fees) - Was 0.0 (Breakeven)

TS_ACTIVATION_2 = 0.025 # 2.5% profit triggers Tier 2 
TS_LOCK_2 = 0.015       # Lock 1.5% profit

# Dynamic Ratchet (Tier 2 Upgrade)
TS_DYNAMIC_CALLBACK = 0.015 # 1.5% trailing distance once Tier 2 is hit

# Stale Position Re-evaluation
MAX_HOLD_HOURS = 12     # Hours before AI re-evaluates a stagnant trade

# Re-entry Cooldown (Discipline)
# Prevents entering on the same candle after a loss (Timeframe Mismatch Fix)
REENTRY_COOLDOWN_CANDLES = 3


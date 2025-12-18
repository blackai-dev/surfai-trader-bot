
import psycopg2
from psycopg2.extras import Json
import config
import datetime

class DatabaseHandler:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=config.DB_HOST,
                port=config.DB_PORT,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD
            )
            self.conn.autocommit = True
            print("✅ Connected to PostgreSQL database.")
            self.init_db()
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            self.conn = None

    def init_db(self):
        if not self.conn: return
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trade_logs (
                        id SERIAL PRIMARY KEY,
                        log_id TEXT UNIQUE,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        symbol TEXT,
                        ai_action TEXT,
                        ai_confidence FLOAT,
                        ai_reasoning TEXT,
                        ma_state JSONB,
                        entry_price FLOAT,
                        exit_price FLOAT,
                        pnl FLOAT,
                        status TEXT
                    );
                """)
                try:
                    cur.execute("ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS log_id TEXT UNIQUE;")
                    cur.execute("ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS highest_price FLOAT DEFAULT 0;")
                except Exception as e:
                    print(f"Migration note: {e}")
            print("Verified trade_logs table.")
        except Exception as e:
            print(f"❌ Failed to init DB schema: {e}")

    def log_signal(self, symbol, signal, indicators):
        # ... (Same as before) ...
        # Ensure we set highest_price = entry_price initially? 
        # Update INSERT to include highest_price if explicit, or default 0.
        if not self.conn: return None
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trade_logs (log_id, symbol, ai_action, ai_confidence, ai_reasoning, ma_state, status, highest_price)
                    VALUES (%s, %s, %s, %s, %s, %s, 'SIGNAL_GENERATED', 0)
                    RETURNING id;
                """, (
                    signal.get('log_id'), 
                    symbol,
                    signal.get('action'),
                    signal.get('confidence'),
                    signal.get('reasoning'),
                    Json(indicators)
                ))
                db_id = cur.fetchone()[0]
                return db_id
        except Exception as e:
            print(f"❌ Failed to log signal: {e}")
            return None

    def log_trade(self, log_id, entry_price, status="OPEN"):
        if not self.conn or not log_id: return
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE trade_logs 
                    SET entry_price = %s, highest_price = %s, status = %s
                    WHERE log_id = %s;
                """, (entry_price, entry_price, status, log_id))
        except Exception as e:
            print(f"❌ Failed to log trade execution: {e}")

    def register_orphan_trade(self, symbol, entry_price, side):
        """Registers an existing position found on exchange that wasn't tracked by Bot."""
        if not self.conn: return None
        try:
            log_id = f"ORPHAN_{symbol}_{int(datetime.datetime.now().timestamp())}"
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trade_logs (log_id, symbol, ai_action, entry_price, highest_price, status)
                    VALUES (%s, %s, %s, %s, %s, 'OPEN')
                    RETURNING id;
                """, (log_id, symbol, side, entry_price, entry_price))
            print(f"📦 Registered orphan position {symbol} with ID {log_id}")
            return log_id
        except Exception as e:
            print(f"❌ Failed to register orphan: {e}")
            return None

    def get_open_trade_state(self, symbol):
        """Fetches log_id, highest_price, entry_price, and timestamp for active open trade"""
        if not self.conn: return None, 0, 0, None
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT log_id, highest_price, entry_price, timestamp FROM trade_logs 
                    WHERE symbol = %s AND status = 'OPEN'
                    ORDER BY id DESC LIMIT 1;
                """, (symbol,))
                row = cur.fetchone()
                if row:
                    return row[0], float(row[1] or 0), float(row[2] or 0), row[3]
                return None, 0, 0, None
        except Exception as e:
            print(f"❌ DB Read Error: {e}")
            return None, 0, 0, None

    def update_highest_price(self, log_id, price):
        if not self.conn: return
        try:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE trade_logs SET highest_price = %s WHERE log_id = %s", (price, log_id))
        except Exception as e:
            print(f"❌ Failed to update HWM: {e}")

    def update_entry_price(self, log_id, new_price):
        """Updates the entry price and resets HWM to new entry price to sync with Exchange."""
        if not self.conn: return
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE trade_logs 
                    SET entry_price = %s, highest_price = %s 
                    WHERE log_id = %s
                """, (new_price, new_price, log_id)) # Reset HWM to Entry on sync
            print(f"🔄 Synced DB Entry Price to {new_price} (ID: {log_id})")
        except Exception as e:
            print(f"❌ Failed to sync entry price: {e}")
            
    def log_pnl(self, symbol, exit_price, pnl, status="CLOSED"):
        # ... existing log_pnl ...
        """
        Updates the latest OPEN trade for the symbol with PnL.
        Note: Simple approach, assumes only one open trade per symbol.
        """
        if not self.conn: return
        try:
            with self.conn.cursor() as cur:
                # Find the latest open trade for this symbol
                cur.execute("""
                    SELECT id FROM trade_logs 
                    WHERE symbol = %s AND status = 'OPEN' 
                    ORDER BY id DESC LIMIT 1;
                """, (symbol,))
                row = cur.fetchone()
                if row:
                    log_id = row[0]
                    cur.execute("""
                        UPDATE trade_logs 
                        SET exit_price = %s, pnl = %s, status = %s
                        WHERE id = %s;
                    """, (exit_price, pnl, status, log_id))
                    print(f"📝 PnL Logged to DB for ID {log_id}: {pnl:.4f}")
                else:
                    print(f"⚠️ No open DB record found for {symbol} to log PnL.")
        except Exception as e:
            print(f"❌ Failed to log PnL: {e}")

    def get_all_open_symbols(self):
        """Returns a list of symbols that are currently 'OPEN' in the DB."""
        if not self.conn: return []
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT DISTINCT symbol FROM trade_logs WHERE status = 'OPEN';")
                rows = cur.fetchall()
                return [r[0] for r in rows]
        except Exception as e:
            print(f"❌ Failed to fetch open symbols: {e}")
            return []

    def close_zombie_trade(self, symbol, estimated_price=None):
        """
        Marks a trade as CLOSED_MANUAL. 
        If estimated_price is provided, calculates per-unit PnL.
        """
        if not self.conn: return
        try:
            with self.conn.cursor() as cur:
                # 1. Fetch Entry details
                cur.execute("""
                    SELECT id, entry_price, ai_action FROM trade_logs 
                    WHERE symbol = %s AND status = 'OPEN'
                    ORDER BY id DESC LIMIT 1;
                """, (symbol,))
                row = cur.fetchone()
                
                if not row:
                    print(f"⚠️ No open trade found for {symbol} to close.")
                    return

                log_id, entry_price, ai_action = row
                pnl = 0
                exit_price = 0
                
                if estimated_price and entry_price:
                    exit_price = estimated_price
                    # If Action=BUY (Long), PnL = Exit - Entry
                    # If Action=SELL (Short), PnL = Entry - Exit
                    if ai_action == 'BUY':
                        pnl = exit_price - entry_price
                    else:
                        pnl = entry_price - exit_price
                
                # 2. Update
                cur.execute("""
                    UPDATE trade_logs 
                    SET status = 'CLOSED_MANUAL', exit_price = %s, pnl = %s
                    WHERE id = %s;
                """, (exit_price, pnl, log_id))
                
                note = f"(Est. PnL: {pnl:.4f})" if estimated_price else "(No Price Info)"
                print(f"🧹 Zombie Trade Cleaned: {symbol} marked as CLOSED_MANUAL {note}")
                
        except Exception as e:
            print(f"❌ Failed to close zombie trade: {e}")

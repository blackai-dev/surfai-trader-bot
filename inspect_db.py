from database import DatabaseHandler
import datetime

db = DatabaseHandler()
if not db.conn:
    print("❌ Could not connect to DB")
    exit()

symbol = 'PERP_ETH_USDC'
print(f"🔍 Fetching last 10 logs for {symbol}...\n")

with db.conn.cursor() as cur:
    cur.execute("""
        SELECT id, timestamp, ai_action, entry_price, exit_price, pnl, status, log_id 
        FROM trade_logs 
        WHERE symbol = %s 
        ORDER BY id DESC 
        LIMIT 10;
    """, (symbol,))
    rows = cur.fetchall()

print(f"{'ID':<4} | {'Time':<20} | {'Action':<6} | {'Entry':<10} | {'Exit':<10} | {'PnL':<10} | {'Status':<15}")
print("-" * 90)

for r in rows:
    # r[1] is timestamp. format it if it's datetime
    ts = r[1].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r[1], datetime.datetime) else str(r[1])
    pnl_str = f"{r[5]:.4f}" if r[5] is not None else "0.0000"
    entry = f"{r[3]:.2f}" if r[3] else "0.00"
    exit_px = f"{r[4]:.2f}" if r[4] else "0.00"
    
    print(f"{r[0]:<4} | {ts:<20} | {r[2]:<6} | {entry:<10} | {exit_px:<10} | {pnl_str:<10} | {r[6]:<15}")

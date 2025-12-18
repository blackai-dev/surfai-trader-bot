import time
print("DEBUG: Starting main.py...")
import os
from dotenv import load_dotenv
import config

# Load environment variables
load_dotenv()

from market_data import MarketData
from ai_analyst import AIAnalyst
from execution import Execution

# Load environment variables
load_dotenv()

def run_bot():
    print("🤖 Orderly Trading Bot Started")
    print(f"Interval: {config.INTERVAL} seconds")
    
    # Initialize DB (Optional: wrap in try-except if we want to run even without DB)
    from database import DatabaseHandler
    db = DatabaseHandler()

    # Initialize Modules
    md = MarketData()
    ai = AIAnalyst()
    exec_mod = Execution(md.client, db_handler=db)
    

    # --- Startup Checks ---
    print("\n🔎 Doing Startup Checks...")
    
    # 1. Check Balance
    usdc_balance = 0.0
    wallet = md.client.get_current_holdings() # Using verified method name
    if wallet and 'data' in wallet and 'holding' in wallet['data']:
         for asset in wallet['data']['holding']:
            if asset['token'] == 'USDC':
                usdc_balance = float(asset['holding'])
    
    # 2. Check Existing Positions & Equity
    has_position = False
    startup_pos = md.get_positions()
    total_unrealized_pnl = 0.0 # Initialize for fallback or display

    if startup_pos and 'data' in startup_pos and 'rows' in startup_pos['data']:
        rows = startup_pos['data']['rows']
        
        # Calculate PnL for Equity display
        # Official 'total_collateral_value' includes Settled + Unsettled PnL
        if 'total_collateral_value' in startup_pos['data']:
            net_equity = float(startup_pos['data']['total_collateral_value'])
            # If using total_collateral_value, we don't have a separate total_unrealized_pnl from this source
            # We can try to calculate it for display if needed, but for now, it's 0 if not explicitly provided.
            # For display purposes, we might still want to calculate it from active_rows if total_collateral_value is used.
            # Let's keep the original PnL calculation for display consistency if total_collateral_value is present.
            active_rows = [r for r in rows if float(r.get('position_qty', 0)) != 0]
            for r in active_rows:
                 pnl = float(r.get('unrealized_pnl', 0))
                 if pnl == 0 and float(r.get('position_qty', 0)) != 0:
                     mark = float(r.get('mark_price', 0))
                     avg = float(r.get('average_open_price', 0))
                     qty = float(r.get('position_qty', 0))
                     if mark and avg:
                         pnl = (mark - avg) * qty if qty > 0 else (avg - mark) * abs(qty)
                 total_unrealized_pnl += pnl
        else:
            # Fallback (Manual Sum - flawed if ignoring unsettled)
            net_equity = usdc_balance 
            active_rows = [r for r in rows if float(r.get('position_qty', 0)) != 0]
            for r in active_rows:
                 pnl = float(r.get('unrealized_pnl', 0))
                 if pnl == 0 and float(r.get('position_qty', 0)) != 0:
                     mark = float(r.get('mark_price', 0))
                     avg = float(r.get('average_open_price', 0))
                     qty = float(r.get('position_qty', 0))
                     if mark and avg:
                         if qty > 0: pnl = (mark - avg) * qty
                         else: pnl = (avg - mark) * abs(qty)
                 total_unrealized_pnl += pnl
            net_equity += total_unrealized_pnl

        print(f"💰 Balance: {usdc_balance:.2f} USDC | Net Equity: {net_equity:.2f} USDC (Unreal PnL: {total_unrealized_pnl:+.2f})")

        # Check for active positions (re-evaluate active_rows if not already done in the 'if' block)
        if 'active_rows' not in locals(): # Ensure active_rows is defined for the following block
            active_rows = [r for r in rows if float(r.get('position_qty', 0)) != 0]

        if active_rows:
            print(f"⚠️ Found {len(active_rows)} existing positions. Running immediate risk check...")
            exec_mod.monitor_risks(active_rows, md)
            has_position = True

    if has_position:
        print("➡️ Risk check complete. Entering main loop...")

    # State for Multi-Token Analysis
    top_10_list = []
    last_scan_time = 0
    SCAN_INTERVAL = 3600 # Rescan top 10 every hour
    last_stale_check_time = 0 
    STALE_CHECK_INTERVAL = 3600 # Check for stale positions every hour
    
    # Timers for each symbol analysis: { "SYMBOL": timestamp }
    analysis_timers = {} 
    
    # Polling interval for loop (fast tick)
    POLL_INTERVAL = 10 
    
    while True:
        try:
            current_time = time.time()
            print(f"\n⏰ Tick: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))}")
            
            # --- 0. Update Top 10 List (Periodically) ---
            if config.ENABLE_TOP_10:
                if current_time - last_scan_time > SCAN_INTERVAL or not top_10_list:
                    print("🔍 Scanning market for Top 5 Volume Tokens...")
                    new_top_10 = md.get_top_10_symbols()
                    if new_top_10:
                        top_10_list = new_top_10
                        print(f"✅ Top 5 Updated: {top_10_list}")
                        last_scan_time = current_time
                    else:
                        print("⚠️ Failed to update Top 10. Using fallback/previous list.")
                        if not top_10_list: top_10_list = [config.SYMBOL]
            else:
                top_10_list = [config.SYMBOL]

            # --- 1. Fetch All Open Positions ---
            positions_resp = md.get_positions()
            current_positions = []
            if positions_resp and isinstance(positions_resp, dict) and 'data' in positions_resp and 'rows' in positions_resp['data']:
                current_positions = positions_resp['data']['rows']
            
            # Count active positions (non-zero qty)
            active_symbols = {p['symbol'] for p in current_positions if float(p.get('position_qty', 0)) != 0}
            active_count = len(active_symbols)
            
            # --- DB Reconciliation (Clean Manual Closes) ---
            # If a trade is OPEN in DB but has 0 qty on exchange, mark it as CLOSED_MANUAL
            db_open_symbols = db.get_all_open_symbols()
            for sym in db_open_symbols:
                if sym not in active_symbols:
                    # Fetch current price to estimate PnL
                    est_price = 0
                    try:
                        candles = md.get_ohlcv(sym, "1m", 1)
                        if candles: est_price = float(candles[-1]['close'])
                    except Exception as e:
                        print(f"⚠️ Failed to fetch price for zombie {sym}: {e}")
                    
                    db.close_zombie_trade(sym, est_price)
            
            # --- RISK MONITOR (Multi-Token) ---
            # --- RISK MONITOR (Multi-Token) ---
            # Check risks for ALL active positions at once
            exec_mod.monitor_risks(current_positions, md)
            
            # --- STALE POSITION CHECK (Cognitive Layer) ---
            # Periodically ask AI to review old trades
            if current_time - last_stale_check_time >= STALE_CHECK_INTERVAL:
                print("🧠 Running Stale Position AI Check...")
                exec_mod.check_stale_positions(current_positions, md, ai)
                last_stale_check_time = current_time
            
            # --- 2. Iterate Through Target Symbols ---
            for rank, symbol in enumerate(top_10_list, start=1):
                # --- Fast Loop: Risk Management & Price for this symbol ---
                # Check if we currently have a position in this symbol (for analysis gating only)
                my_position = next((p for p in current_positions if p.get('symbol') == symbol and float(p.get('position_qty', 0)) != 0), None)
                has_position = (my_position is not None)
                
                # --- Slow Loop: AI Analysis & Trading ---
                # Rule: Only analyze if (No Position) AND (Interval Passed) AND (Max Positions Not Reached)
                last_time = analysis_timers.get(symbol, 0)
                
                if not has_position:
                    if active_count >= config.MAX_OPEN_POSITIONS:
                        # Skip analysis if we are full
                        continue
                        
                    if current_time - last_time >= config.INTERVAL:
                        print(f"👉 Analyzing {symbol} (Rank #{rank})...")
                        
                        # Fetch 100 candles
                        candles_15m = md.get_ohlcv(symbol, timeframe="15m", limit=100)
                        
                        if candles_15m:
                            # Calculate Indicators
                            import indicators
                            inds = indicators.calculate_indicators(candles_15m)
                            # Inject Rank for DB Logging
                            inds['market_rank'] = rank
                            
                            print(f"📊 {symbol} Indicators: Price={inds['current_price']}, MA60={inds['MA_LONG']}")
                            
                            print(f"🧠 Asking AI for {symbol}...")
                            signal = ai.analyze_market(candles_15m, indicators=inds)
                            
                            if signal:
                                # Inject Entry Price for Execution Logic
                                signal['entry_price'] = inds['current_price']
                                signal['log_id'] = f"{symbol}_{int(current_time)}" 
                                
                                # Log signal to DB
                                db.log_signal(symbol, signal, inds)
                                
                                print(f"💡 {symbol} Signal: {signal.get('action')} (Conf: {signal.get('confidence')})")
                                if exec_mod.validate_signal(signal):
                                    exec_mod.execute_trade(signal, symbol)
                                    # Update active count locally to prevent over-trading in same tick
                                    if signal.get('action') in ["BUY", "SELL"]:
                                        active_count += 1 
                                else:
                                    print(f"⏸️ {symbol} Signal skipped")
                            else:
                                print(f"⚠️ {symbol} AI analysis failed/empty.")
                        else:
                            print(f"⚠️ {symbol} Data incomplete.")
                        
                        last_time = current_time
                        
                        # Update Last Analysis Time for this symbol
                        analysis_timers[symbol] = current_time
                        
                        # Space out API calls to prevent 502/429 errors
                        time.sleep(2) # 2 seconds spacing between symbols
                        
                        # Sleep briefly between symbols to avoid Rate Limit (e.g. 2s)
                        time.sleep(2)
            
            print(f"💤 Sleeping {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            time.sleep(10) # Prevent tight loop on error

if __name__ == "__main__":
    run_bot()

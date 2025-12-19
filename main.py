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
    # Initialize Modules
    md = MarketData()
    ai = AIAnalyst()
    exec_mod = Execution(md.client, db_handler=db)
    
    # NEW: Initialize Notifier
    from notifier import TelegramNotifier
    notifier = TelegramNotifier()
    notifier.send_message("🤖 **Orderly Bot Started**\nWaiting for ticks...")

    # --- Startup Checks ---
    print("\n🔎 Doing Startup Checks...")
    
    # 1. Check Balance & Equity
    usdc_balance = 0.0
    wallet = md.client.get_current_holdings()
    if wallet and 'data' in wallet and 'holding' in wallet['data']:
         for asset in wallet['data']['holding']:
            if asset['token'] == 'USDC':
                usdc_balance = float(asset['holding'])

    startup_pos = md.get_positions()
    net_equity = usdc_balance
    total_unrealized_pnl = 0.0
    
    if startup_pos and 'data' in startup_pos:
        # Official 'total_collateral_value' includes Settled + Unsettled PnL
        if 'total_collateral_value' in startup_pos['data']:
            net_equity = float(startup_pos['data']['total_collateral_value'])
        
        # Calculate PnL for display context
        if 'rows' in startup_pos['data']:
            rows = startup_pos['data']['rows']
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

    print(f"💰 Balance: {usdc_balance:.2f} USDC | Net Equity: {net_equity:.2f} USDC (Unreal PnL: {total_unrealized_pnl:+.2f})")


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
            
            # --- -1. Check Remote Commands (DB) ---
            # Protocol: DB is the source of truth for controls
            is_paused_str = db.get_config("is_paused", "false")
            if is_paused_str == "true":
                print("⏸️ Bot is PAUSED by remote command.")
                # We still run Risk Monitor (monitor_risks) below, but skip Analysis
                pass 
            
            # Sync Position Size
            size_str = db.get_config("position_size", "30.0")
            try:
                config.POSITION_SIZE_USDC = float(size_str)
            except:
                pass

            # --- -2. Process Remote Command Queue (Phase 2) ---
            pending_cmds = db.get_pending_commands()
            for cmd in pending_cmds:
                cmd_id, command, params = cmd
                print(f"📥 Processing Remote Command: {command} {params}")
                
                if command == "CLOSE_POSITION":
                    target_symbol = params.get('symbol')
                    # Find quantity from active positions
                    # Only if we have current_positions populated (might need to fetch if not yet done)
                    # To be safe, fetch specific position
                    try:
                        pos_info = md.client.get_one_position_info(target_symbol)
                        if pos_info and 'data' in pos_info:
                            qty = float(pos_info['data'].get('position_qty', 0))
                            if qty != 0:
                                side = "SELL" if qty > 0 else "BUY"
                                exec_mod.close_position(target_symbol, abs(qty), side)
                                notifier.send_message(f"✅ **Remote Close Executed**: {target_symbol}")
                            else:
                                notifier.send_message(f"⚠️ **Remote Close Failed**: No open position for {target_symbol}")
                    except Exception as e:
                        print(f"❌ Failed to execute remote close: {e}")
                
                elif command == "FORCE_ANALYZE":
                    print("🧠 Processing Force Audit Command...")
                    try:
                        # Fetch fresh positions
                        p_resp = md.get_positions()
                        if p_resp and 'data' in p_resp and 'rows' in p_resp['data']:
                            p_rows = p_resp['data']['rows']
                            active_p = [p for p in p_rows if float(p.get('position_qty', 0)) != 0]
                            if active_p:
                                notifier.send_message(f"🧠 **Auditing {len(active_p)} Positions...**")
                                exec_mod.audit_positions(active_p, md, ai, force=True)
                            else:
                                notifier.send_message("⚠️ No active positions to audit.")
                    except Exception as e:
                        print(f"❌ Force Audit Error: {e}")
                
                elif command == "CLOSE_ALL":
                    print("🚨 Processing PANIC CLOSE ALL...")
                    # 1. Pause Bot
                    db.set_config("is_paused", "true")
                    is_paused_str = "true" # Update local state immediately
                    notifier.send_message("⏸️ **Bot PAUSED by Panic Protocol**")
                    
                    # 2. Close All
                    try:
                        p_resp = md.get_positions()
                        if p_resp and 'data' in p_resp and 'rows' in p_resp['data']:
                            p_rows = p_resp['data']['rows']
                            active_p = [p for p in p_rows if float(p.get('position_qty', 0)) != 0]
                            
                            if not active_p:
                                notifier.send_message("✅ No active positions to close.")
                            else:
                                count = 0
                                for p in active_p:
                                    sym = p['symbol']
                                    qty = float(p['position_qty'])
                                    side = "SELL" if qty > 0 else "BUY"
                                    
                                    print(f"🚨 Panic Closing {sym} ({qty})...")
                                    exec_mod.close_position(sym, abs(qty), side)
                                    count += 1
                                    
                                notifier.send_message(f"✅ **Panic Complete**: Closed {count} positions.")
                    except Exception as e:
                        print(f"❌ Panic Close Failed: {e}")
                        notifier.send_message(f"❌ **Panic Failed**: {e}")

                # Mark Complete
                db.mark_command_completed(cmd_id)

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
                    # Notify
                    notifier.send_message(f"🧹 **Zombie Trade Closed**: {sym}\nPrice: {est_price}")
            
            # --- RISK MONITOR (Multi-Token) ---
            # Check risks for ALL active positions at once
            exec_mod.monitor_risks(current_positions, md)
            
            # --- IF PAUSED, SKIP ANALYSIS ---
            if is_paused_str == "true":
                print("💤 Paused... skipping analysis.")
                time.sleep(POLL_INTERVAL)
                continue

            # --- STALE POSITION CHECK (Cognitive Layer) ---
            # Periodically ask AI to review old trades
            if current_time - last_stale_check_time >= STALE_CHECK_INTERVAL:
                print("🧠 Running Stale Position AI Check...")
                exec_mod.audit_positions(current_positions, md, ai, force=False)
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
                        # --- Cooldown Check (Mechanical Layer) ---
                        last_exit_ts, last_exit_reason = db.get_last_exit_info(symbol)
                        current_exit_context = None
                        
                        if last_exit_ts:
                            # Convert to timestamp
                            ts_val = last_exit_ts.timestamp()
                            CANDLE_SECONDS = 900 # 15m
                            
                            last_candle_idx = int(ts_val // CANDLE_SECONDS)
                            curr_candle_idx = int(current_time // CANDLE_SECONDS)
                            
                            diff = curr_candle_idx - last_candle_idx
                            if diff < config.REENTRY_COOLDOWN_CANDLES:
                                print(f"🧊 Cooldown Active for {symbol} (Last Exit: {last_exit_ts.strftime('%H:%M')}). Skipping analysis.")
                                # Still update timer to avoid tight loop checks? No, let it check next interval.
                                # Actually, if we skip, we don't update last_time, so it checks every POLL? 
                                # Better to sleep or just update last_time?
                                # Ideally we shouldn't spam DB. Let's update last_time so we check again in 5 mins.
                                analysis_timers[symbol] = current_time
                                time.sleep(1)
                                continue
                            
                            # Prepare context for AI if recent (e.g. < 4 hours)
                            if diff < 16: # 4 hours = 16 candles
                                current_exit_context = {'time': last_exit_ts, 'reason': last_exit_reason, 'candles_ago': diff}

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
                            signal = ai.analyze_market(symbol, candles_15m, indicators=inds, last_exit=current_exit_context)
                            
                            if signal:
                                # Inject Entry Price for Execution Logic
                                signal['entry_price'] = inds['current_price']
                                signal['log_id'] = f"{symbol}_{int(current_time)}" 
                                
                                # Log signal to DB
                                db.log_signal(symbol, signal, inds)
                                
                                print(f"💡 {symbol} Signal: {signal.get('action')} (Conf: {signal.get('confidence')})")
                                
                                # Notify Signal
                                notifier.send_message(
                                    f"🧠 **AI Signal Generated**\n"
                                    f"Symbol: `{symbol}`\n"
                                    f"Action: **{signal.get('action')}**\n"
                                    f"Confidence: {signal.get('confidence')}\n"
                                    f"Reason: _{signal.get('reasoning')}_"
                                )
                                
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

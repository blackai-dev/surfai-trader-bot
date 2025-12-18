import config
import decimal
import time
import math
import datetime

class Execution:
    def __init__(self, client, db_handler=None):
        self.client = client
        self.db = db_handler

    def validate_signal(self, signal):
        if not signal:
            return False
            
        action = signal.get("action", "HOLD").upper()
        if action == "HOLD":
            return False
            
        confidence = signal.get("confidence", 0.0)
        if confidence < 0.6: # Configurable threshold
            print(f"Skipping trade: Low confidence {confidence}")
            return False
            
        # TODO: Check if we already have a position in this symbol to avoid stacking
        # positions = self.client.get_all_positions_info()
        # ...
        
        return True


    def execute_trade(self, signal, symbol):
        try:
            action = signal.get('action')
            entry_price = float(signal.get('entry_price', 0))
            
            
            # 1. Get Price
            # We need entry price to calculate quantity
            # Approximate with last close or mid price
            # Assuming we can get it from signal, otherwise fetch
            current_price = signal.get('entry_price')
            if not current_price:
                 print("⚠️ Signal missing entry price, skipping trade.")
                 return None

            # 2. Get Trading Rules (Filters)
            rules = self.client.get_exchange_info(symbol)
            base_tick = 0.01 # Default fallback
            min_notional = 10.0 # Default
            
            if rules and 'data' in rules:
                base_tick = float(rules['data'].get('base_tick', 0.01))
                min_notional = float(rules['data'].get('min_notional', 10.0))

            # 3. Calculate Quantity
            # qty = Target Value / Price
            raw_qty = config.POSITION_SIZE_USDC / current_price
            
            # Round to base_tick
            # e.g. 0.079 / 0.01 = 7.9 -> 8 -> 0.08
            steps = round(raw_qty / base_tick)
            order_quantity = steps * base_tick
            
            # Formatting to remove floating point errors (e.g. 0.3000000004)
            # Use decimals from base_tick count
            d = decimal.Decimal(str(base_tick))
            decimals = abs(d.as_tuple().exponent)
            order_quantity = round(order_quantity, decimals)

            # 4. Check Min Notional
            notional_value = order_quantity * current_price
            if notional_value < min_notional:
                print(f"⚠️ Calculated value {notional_value:.2f} < Min Notional {min_notional}. Adjusting...")
                # Try to add 1 tick
                order_quantity += base_tick
                order_quantity = round(order_quantity, decimals)
                print(f"   Adjusted Qty: {order_quantity} (Val: {order_quantity*current_price:.2f})")
            
            # Double check
            if order_quantity * current_price < min_notional:
                 print("❌ Still below min notional after adjustment. Skipping.")
                 return None

            print(f"🚀 Executing {action} on {symbol} | Size: {order_quantity} ({order_quantity*current_price:.2f} USDC)")

            start_t = time.time()
            side = "BUY" if action == "BUY" else "SELL"
            
            # Place Order (Using verified client method)
            # Assuming 'market' order for entry to ensure fill on momentum
            response = self.client.create_order(
                symbol=symbol,
                order_type="MARKET",
                side=side,
                order_quantity=order_quantity
            )
            # Note: For Market Order, price is ignored but SDK might need it passed as None or just omitted.
            # Assuming standard create_order(symbol, type, side, quantity) signature.
            if response and response.get('success'):
                # Extract executed price roughly
                executed_price = float(response.get('data', {}).get('average_executed_price', 0))
                
                # Robust Fallback: Verify with Position Data
                # If API didn't return fill price (async), check actual position
                if executed_price == 0:
                    print("⏳ Waiting for fill confirmation...")
                    time.sleep(1) # Give exchange a moment to process
                    # We need access to market data headers to fetch position
                    # Since execution class doesn't have 'md' in init, we rely on passed arguments or fetching
                    # Strategy: Use existing client to get position info directly
                    try:
                        pos_info = self.client.get_one_position_info(symbol)
                        if pos_info and 'data' in pos_info:
                             executed_price = float(pos_info['data'].get('average_open_price', 0))
                             print(f"🔄 Fetched actual Entry Price from Position: {executed_price}")
                    except Exception as e:
                        print(f"⚠️ Failed to fetch position info: {e}")

                if executed_price == 0:
                     executed_price = float(signal.get('entry_price', 0)) # Final Fallback

                print(f"✅ Trade executed: {action} {order_quantity} {symbol} @ {executed_price}")
                
                # DB Logging
                if self.db and signal.get('log_id'):
                    self.db.log_trade(signal.get('log_id'), executed_price, "OPEN")
                
                print(f"✅ Order placed: {response}")
                return response
            else:
                print(f"❌ Order failed or not successful: {response}")
                return None
            
        except Exception as e:
            print(f"❌ Order failed: {e}")
            return None

    def close_position(self, symbol, quantity, side):
        """
        Closes a position by placing an opposing market order.
        """
        print(f"🚨 Closing Position: {side} {quantity} {symbol}")
        try:
            # Orderly usually supports reducing positions via REDUCE_ONLY or just opposing orders.
            # Here we place a MARKET order to close immediately.
            response = self.client.create_order(
                symbol=symbol,
                order_type="MARKET",
                side=side,
                order_quantity=quantity,
                reduce_only=True # Important to ensure we don't flip position
            )
            
            # 1. Try to get executed price from immediate response
            executed_price = float(response.get('data', {}).get('average_executed_price', 0))
            
            # 2. If 0 (Async), fetch order details
            if executed_price == 0 and response.get('success'):
                order_id = response.get('data', {}).get('order_id')
                if order_id:
                    print(f"⏳ Closing Order {order_id} sent. Waiting for confirmation...")
                    time.sleep(1) # Wait for matching
                    try:
                        order_info = self.client.get_order(order_id)
                        if order_info and 'data' in order_info:
                             executed_price = float(order_info['data'].get('average_executed_price', 0))
                             print(f"✅ Position Closed. Actual Exit Price: {executed_price}")
                    except Exception as e:
                        print(f"⚠️ Failed to fetch close order info: {e}")

            print(f"✅ Position Closed: {response}")
            return response, executed_price
        except Exception as e:
            print(f"❌ Close failed: {e}")
            return None, 0

    def monitor_risks(self, positions, md):
        """
        Checks open positions against TP/SL thresholds.
        supports multi-token monitoring.
        """
        if not positions or not isinstance(positions, list):
            return

        for pos in positions:
            symbol = pos.get('symbol')
            qty = float(pos.get('position_qty', 0))
            if qty == 0:
                continue
            
            # Fetch current market price for this specific symbol
            # We use the MarketData handler passed in
            current_price = 0
            
            # 1. Try Orderbook (Best Accuracy)
            for attempt in range(3):
                try:
                    ob = md.get_orderbook(symbol)
                    # Handle Orderly SDK response structure: {'success': True, 'data': {'asks':..., 'bids':...}}
                    if ob and 'data' in ob and 'asks' in ob['data'] and 'bids' in ob['data']:
                        asks = ob['data']['asks']
                        bids = ob['data']['bids']
                        if len(asks) > 0 and len(bids) > 0:
                            best_ask = float(asks[0]['price'])
                            best_bid = float(bids[0]['price'])
                            current_price = (best_ask + best_bid) / 2
                            break # Success
                    # Fallback for flat structure (just in case mock or different version)
                    elif ob and 'asks' in ob and 'bids' in ob and len(ob['asks']) > 0:
                        best_ask = float(ob['asks'][0]['price'])
                        best_bid = float(ob['bids'][0]['price'])
                        current_price = (best_ask + best_bid) / 2
                        break
                except Exception as e:
                    time.sleep(0.5) # Short backoff
            
            # 2. Fallback to Candles (If OB failed)
            if current_price == 0:
                print(f"⚠️ Orderbook failed for {symbol}, trying fallback (OHLCV)...")
                try:
                    # Request 1 minute candle for latest price
                    candles = md.get_ohlcv(symbol, timeframe="1m", limit=1)
                    if candles and len(candles) > 0:
                        current_price = float(candles[-1]['close'])
                        print(f"✅ Fallback successful: {current_price}")
                except Exception as e:
                    print(f"❌ Fallback failed for {symbol}: {e}")
            
            if current_price == 0:
                 print(f"❌ Could not fetch price for {symbol} after retries. Skipping risk check.")
                 continue

            # Determine direction & avg price
            avg_price = float(pos.get('average_open_price', 0))
            if avg_price == 0:
                continue

            is_long = qty > 0
            abs_qty = abs(qty)
            
            # Calculate PnL % or Price check
            # TP/SL logic
            
            if is_long:
                # LONG: TP > Entry, SL < Entry
                tp_price = avg_price * (1 + config.TP_PERCENT)
                base_sl = avg_price * (1 - config.SL_PERCENT)
                
                # Fetch High Water Mark (Highest Price) from DB
                log_id, hwm_price, db_entry, entry_time = self.db.get_open_trade_state(symbol) if self.db else (None, 0, 0, None)
                
                # Adopt Orphan Position (If not in DB)
                if self.db and not log_id:
                    log_id = self.db.register_orphan_trade(symbol, avg_price, 'BUY')
                    hwm_price = avg_price

                # Check DB Stale/Mismatch: If DB Entry differs significantly from API Entry, ignore DB
                # Check DB Stale/Mismatch
                if db_entry and abs(db_entry - avg_price) > (avg_price * 0.01):
                    # print(f"⚠️ DB State Mismatch for {symbol}. Ignoring DB HWM.")
                    print(f"⚠️ DB Mismatch {symbol}: DB={db_entry} API={avg_price}. Keeping HWM (Legacy Mode).")
                    # hwm_price = 0
                
                # If HWM is 0 or less than current entry (could be from old logic), init logic
                if hwm_price < avg_price: 
                    hwm_price = avg_price
                
                # Update HWM if current price is higher
                if current_price > hwm_price:
                    hwm_price = current_price
                    if self.db and log_id:
                        self.db.update_highest_price(log_id, hwm_price)

                # Stepped Trailing Stop Logic (Stateful)
                # We use HWM to check if a Tier was EVER reached
                max_pnl_pct = (hwm_price - avg_price) / avg_price
                current_pnl_pct = (current_price - avg_price) / avg_price
                
                effective_sl = base_sl
                sl_type = "Base SL"
                
                # Tier 2 Check (Dynamic Ratchet)
                if max_pnl_pct >= config.TS_ACTIVATION_2:
                    effective_sl = hwm_price * (1 - config.TS_DYNAMIC_CALLBACK)
                    sl_type = "TS Dynamic (Ratchet)"
                # Tier 1 Check
                elif max_pnl_pct >= config.TS_ACTIVATION_1:
                    effective_sl = avg_price * (1 + config.TS_LOCK_1)
                    sl_type = "TS Tier 1 (Fees Covered)"
                
                # Check
                print(f"📊 LONG {qty} {symbol} | Entry: {avg_price:.4f} | Mark: {current_price:.4f} | CurPnL: {current_pnl_pct*100:.2f}% | MaxPnL: {max_pnl_pct*100:.2f}%")
                print(f"   🎯 TP: {tp_price:.4f} | 🛑 {sl_type}: {effective_sl:.4f}")
                
                if current_price >= tp_price:
                    print(f"💰 TP Triggered for LONG {symbol}: Price {current_price} >= {tp_price}")
                    _, exit_price = self.close_position(symbol, abs_qty, "SELL")
                    if self.db:
                        # Use real exit price if available, else current_price
                        final_price = exit_price if exit_price > 0 else current_price
                        pnl_amount = (final_price - avg_price) * abs_qty
                        self.db.log_pnl(symbol, final_price, pnl_amount, "CLOSED_TP")
                        
                elif current_price <= effective_sl:
                    print(f"🛑 SL Triggered ({sl_type}) for LONG {symbol}: Price {current_price} <= {effective_sl}")
                    _, exit_price = self.close_position(symbol, abs_qty, "SELL")
                    if self.db:
                        final_price = exit_price if exit_price > 0 else current_price
                        pnl_amount = (final_price - avg_price) * abs_qty
                        self.db.log_pnl(symbol, final_price, pnl_amount, "CLOSED_SL")
                    
            else:
                # SHORT: TP < Entry, SL > Entry
                tp_price = avg_price * (1 - config.TP_PERCENT)
                base_sl = avg_price * (1 + config.SL_PERCENT)
                
                # Fetch High Water Mark (Lowest Price for Short) from DB
                # Note: We reuse 'highest_price' column to store the 'Best Price' seen
                log_id, hwm_price, db_entry, entry_time = self.db.get_open_trade_state(symbol) if self.db else (None, 0, 0, None)
                
                # Adopt Orphan Position (If not in DB)
                if self.db and not log_id:
                    log_id = self.db.register_orphan_trade(symbol, avg_price, 'SELL')
                    hwm_price = avg_price

                # Check DB Stale/Mismatch
                if db_entry and abs(db_entry - avg_price) > (avg_price * 0.01):
                    # print(f"⚠️ DB State Mismatch for {symbol}. Ignoring DB HWM.")
                    print(f"⚠️ DB Mismatch {symbol}: DB={db_entry} API={avg_price}. Keeping HWM (Legacy Mode).")
                    # hwm_price = 0
                
                # Init HWM (For Short, HWM is 0 or > Entry is bad/init state)
                if hwm_price == 0: 
                    hwm_price = avg_price
                
                # Update HWM (Best Price) if current price is LOWER (Better for Short)
                if current_price < hwm_price:
                    hwm_price = current_price
                    if self.db and log_id:
                        self.db.update_highest_price(log_id, hwm_price)

                # Stepped Trailing Stop Logic (Stateful)
                # Max PnL for Short = (Entry - Lowest_Price) / Entry
                max_pnl_pct = (avg_price - hwm_price) / avg_price
                current_pnl_pct = (avg_price - current_price) / avg_price
                
                effective_sl = base_sl
                sl_type = "Base SL"
                
                # Tier 2 Check (Dynamic Ratchet)
                if max_pnl_pct >= config.TS_ACTIVATION_2:
                    effective_sl = hwm_price * (1 + config.TS_DYNAMIC_CALLBACK) # SL moves down (Profit)
                    sl_type = "TS Dynamic (Ratchet)"
                # Tier 1 Check
                elif max_pnl_pct >= config.TS_ACTIVATION_1:
                    effective_sl = avg_price * (1 - config.TS_LOCK_1) # SL moves down
                    sl_type = "TS Tier 1 (Fees Covered)"
                
                # Check
                print(f"📊 SHORT {abs_qty} {symbol} | Entry: {avg_price:.4f} | Mark: {current_price:.4f} | CurPnL: {current_pnl_pct*100:.2f}% | MaxPnL: {max_pnl_pct*100:.2f}%")
                print(f"   🎯 TP: {tp_price:.4f} | 🛑 {sl_type}: {effective_sl:.4f}")
                
                if current_price <= tp_price:
                    print(f"💰 TP Triggered for SHORT {symbol}: Price {current_price} <= {tp_price}")
                    _, exit_price = self.close_position(symbol, abs_qty, "BUY")
                    if self.db:
                        final_price = exit_price if exit_price > 0 else current_price
                        pnl_amount = (avg_price - final_price) * abs_qty
                        self.db.log_pnl(symbol, final_price, pnl_amount, "CLOSED_TP")

                elif current_price >= effective_sl:
                    print(f"🛑 SL Triggered ({sl_type}) for SHORT {symbol}: Price {current_price} >= {effective_sl}")
                    _, exit_price = self.close_position(symbol, abs_qty, "BUY")
                    if self.db:
                        final_price = exit_price if exit_price > 0 else current_price
                        pnl_amount = (avg_price - final_price) * abs_qty
                        self.db.log_pnl(symbol, final_price, pnl_amount, "CLOSED_SL")

    def check_stale_positions(self, positions, md, ai):
        """
        Iterates through active positions and asks AI to review 'stale' ones.
        Stale = Held > MAX_HOLD_HOURS and NOT in high-profit zone.
        """
        if not self.db or not ai: return
        
        current_time_dt = datetime.datetime.now()
        
        for pos in positions:
            symbol = pos.get('symbol')
            qty = float(pos.get('position_qty', 0))
            if qty == 0: continue
            
            # Fetch State
            log_id, hwm_price, db_entry, entry_time = self.db.get_open_trade_state(symbol)
            
            if not entry_time:
                continue # Can't calculate age
            
            # Robust Timezone Handling
            # Ensure both are offset-naive (Local/UTC) to allow subtraction
            if entry_time.tzinfo:
                entry_time = entry_time.replace(tzinfo=None)
            
            # Calculate Age
            age = current_time_dt - entry_time
            hours_held = age.total_seconds() / 3600
            
            if hours_held > config.MAX_HOLD_HOURS:
                # Determine PnL
                mark_price = pos.get('mark_price', 0)
                if not mark_price:
                     # Try fallback
                     candles = md.get_ohlcv(symbol, timeframe="1m", limit=1)
                     if candles: mark_price = float(candles[-1]['close'])
                
                if not mark_price: continue

                avg_price = float(pos.get('average_open_price', 0))
                if qty > 0: # LONG
                    pnl_pct = (mark_price - avg_price) / avg_price
                else: # SHORT
                    pnl_pct = (avg_price - mark_price) / avg_price
                
                # Filter: Only check if NOT in Tier 2 Profit (If it's mooning, let Ratchet handle it)
                if pnl_pct < config.TS_ACTIVATION_2:
                    print(f"🕰️ Stale Check for {symbol} (Held {hours_held:.1f}h, PnL {pnl_pct*100:.2f}%)... Asking AI.")
                    
                    # Fetch Candles for Context
                    candles_ctx = md.get_ohlcv(symbol, timeframe="15m", limit=20)
                    if not candles_ctx: continue
                    
                    decision = ai.evaluate_stale_position(symbol, pnl_pct, hours_held, candles_ctx)
                    
                    if decision == "CLOSE":
                        print(f"🛑 AI Decided to CLOSE Stale Position {symbol} (Reason: Trend Invalidated)")
                        side = "SELL" if qty > 0 else "BUY"
                        _, exit_price = self.close_position(symbol, abs(qty), side)
                        if self.db:
                            final_price = exit_price if exit_price > 0 else mark_price
                            pnl_val = (final_price - avg_price) * qty if qty > 0 else (avg_price - final_price) * abs(qty)
                            self.db.log_pnl(symbol, final_price, pnl_val, "CLOSED_AI_STALE")
                    else:
                         print(f"🧘 AI Decided to HOLD Stale Position {symbol}.")


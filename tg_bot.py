import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from database import DatabaseHandler
import config
import matplotlib.pyplot as plt
import io

from market_data import MarketData

# Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

db = DatabaseHandler()
md = MarketData()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume Trading"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    db.set_config("is_paused", "false")
    await update.message.reply_text("▶️ Trading Resumed.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause Trading"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    db.set_config("is_paused", "true")
    await update.message.reply_text("⏸️ Trading Paused (Finish active trades only).")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Status with Detailed Position Info"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    is_paused = db.get_config("is_paused", "false")
    pos_size_str = db.get_config("position_size", "30.0")
    status_emoji = "⏸️" if is_paused == "true" else "▶️"
    
    msg = f"🤖 **Bot Status**\n"
    msg += f"State: {status_emoji} (Paused={is_paused})\n"
    msg += f"Size: {pos_size_str} USDC\n"

    # Fetch Active Positions from DB
    open_symbols = db.get_all_open_symbols()
    
    if not open_symbols:
        msg += "Active Positions: None (Idle)"
    else:
        msg += f"Active Positions: {len(open_symbols)}\n"
        for symbol in open_symbols:
            # 1. Get Live Market Data
            orderbook = md.get_orderbook(symbol)
            mark_price = 0
            
            # Robust Parsing (Handle both nested 'data' and flat structures)
            if orderbook:
                if 'data' in orderbook and 'asks' in orderbook['data'] and 'bids' in orderbook['data']:
                    asks = orderbook['data']['asks']
                    bids = orderbook['data']['bids']
                elif 'asks' in orderbook and 'bids' in orderbook:
                     asks = orderbook['asks']
                     bids = orderbook['bids']
                else:
                    asks = []
                    bids = []

                if asks and bids and len(asks) > 0 and len(bids) > 0:
                    best_ask = float(asks[0]['price'])
                    best_bid = float(bids[0]['price'])
                    mark_price = (best_ask + best_bid) / 2
            
            # 2. Get Trade Details from DB
            entry, highest, action, ts = db.get_active_trade_details(symbol)
            
            # 3. Calculate Metrics
            if entry > 0 and mark_price > 0:
                # PnL Calculation
                pnl_pct = 0
                max_pnl_pct = 0
                
                if action == 'BUY': # LONG
                    pnl_pct = (mark_price - entry) / entry * 100
                    max_pnl_pct = (highest - entry) / entry * 100
                    # Targets
                    tp_price = entry * (1 + config.TP_PERCENT)
                else: # SHORT
                    pnl_pct = (entry - mark_price) / entry * 100
                     # For Short, 'highest' in DB tracks the lowest price seen (logic in execution.py)
                    max_pnl_pct = (entry - highest) / entry * 100 if highest > 0 else 0
                    tp_price = entry * (1 - config.TP_PERCENT)

                # Emoji Selection
                pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
                
                msg += f"\n📊 **{action}** `{symbol}`\n"
                msg += f"   Entry: `{entry}` | Mark: `{mark_price:.4f}`\n"
                msg += f"   {pnl_emoji} CurPnL: `{pnl_pct:.2f}%` | 🚀 MaxPnL: `{max_pnl_pct:.2f}%`\n"
                msg += f"   🎯 TP: `{tp_price:.4f}`\n"
            else:
                msg += f"\n⚠️ `{symbol}`: Data Unavailable (Entry={entry}, Mark={mark_price})\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def set_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set Position Size"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    try:
        new_size = float(context.args[0])
        if new_size < 10 or new_size > 1000:
             await update.message.reply_text("⚠️ Size must be between 10 and 1000.")
             return
             
        db.set_config("position_size", str(new_size))
        await update.message.reply_text(f"✅ Position Size updated to {new_size} USDC.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /set_size <amount>")

async def close_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force Close Position"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    try:
        symbol = context.args[0].upper()
        # Verify symbol format roughly
        if not "PERP" in symbol and len(symbol) < 6:
             # Auto-fix PERP suffix if missing (optional but handy)
             symbol += "_USDC" 

        db.add_command("CLOSE_POSITION", {"symbol": symbol})
        await update.message.reply_text(f"⚠️ Close command queued for {symbol}. Will execute on next tick.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /close <symbol> (e.g. PERP_BTC_USDC or just PERP_BTC)")

async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View Recent Signals"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    rows = db.get_recent_signals(limit=5)
    if not rows:
        await update.message.reply_text("📭 No recent signals found.")
        return

    msg = "📡 **Recent Signals**\n"
    for r in rows:
        symbol, action, conf, ts, reason = r
        ts_str = ts.strftime("%H:%M") if ts else "?"
        msg += f"• `{symbol}` **{action}** ({conf})\n  _{reason[:50]}..._ @ {ts_str}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate PnL Chart"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    rows = db.get_pnl_history(limit=50)
    if not rows:
        await update.message.reply_text("📭 No PnL history to plot.")
        return

    # Data Prep
    times = [r[0] for r in rows]
    pnls = [r[1] for r in rows]
    cumulative = []
    total = 0
    for p in pnls:
        total += p
        cumulative.append(total)

    # Plotting
    plt.figure(figsize=(10, 5))
    plt.plot(times, cumulative, marker='o', linestyle='-', color='g')
    plt.title(f"Cumulative PnL (Last {len(rows)} Trades)")
    plt.xlabel("Time")
    plt.ylabel("USDC")
    plt.grid(True)
    
    # Save to Buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await update.message.reply_photo(photo=buf, caption=f"💰 Total PnL: {total:.2f} USDC")

async def audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force AI Audit of Positions"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    db.add_command("FORCE_ANALYZE", {})
    await update.message.reply_text("🔍 **Manual Audit Requested**\nAI will review all positions on next tick.")

async def close_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Panic Button: Close All & Pause"""
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: return
    
    db.add_command("CLOSE_ALL", {})
    await update.message.reply_text("⚠️ **PANIC INITIATED**\nQueueing CLOSE ALL and PAUSING bot...")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Help Message"""
    print(f"DEBUG: Help command received from {update.effective_chat.id}") # Debug Log
    if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID: 
        print(f"DEBUG: Chat ID mismatch. Config: {config.TELEGRAM_CHAT_ID}, User: {update.effective_chat.id}")
        return
    
    # Use standard formatting without risky Markdown for now to ensure delivery
    msg = (
        "🤖 Orderly Bot Helper\n\n"
        "🕹️ Control\n"
        "/start - Resume Trading\n"
        "/stop - Pause Trading\n"
        "/set_size [amount] - Set Order Size\n"
        "/close [symbol] - Force Close\n\n"
        "📊 Monitoring\n"
        "/status - View Bot State\n"
        "/pnl - View PnL Chart\n"
        "/signals - View AI Signals\n"
        "/audit - Force AI Check\n"
        "/close_all - PANIC CLOSE & PAUSE\n"
    )
    try:
        await update.message.reply_text(msg) # Removed parse_mode just to be 100% safe
    except Exception as e:
        print(f"❌ Error sending help message: {e}")

def run_tg_bot():
    if not config.TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        return

    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('set_size', set_size))
    # NEW: Close Command
    application.add_handler(CommandHandler('close', close_position))
    # NEW: Report Commands
    application.add_handler(CommandHandler('signals', signals_command))
    application.add_handler(CommandHandler('pnl', pnl_command))
    # NEW: Audit Command
    application.add_handler(CommandHandler('audit', audit_command))
    # NEW: Panic Command
    application.add_handler(CommandHandler('close_all', close_all_command))
    # NEW: Help Command
    application.add_handler(CommandHandler('help', help_command))
    
    print("🤖 Telegram Bot Listening...")
    application.run_polling()

if __name__ == '__main__':
    run_tg_bot()

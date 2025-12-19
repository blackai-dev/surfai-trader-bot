#!/bin/bash

# Auto-restart script for Orderly Bot
while true; do
    echo "=========================================="
    echo "🚀 Starting Orderly Bot..."
    echo "Time: $(date)"
    echo "=========================================="
    
    # Initialize Conda for shell script
    conda activate orderly_trading_bot
    
    # Run the bot
    python3 -u main.py
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Bot stopped gracefully."
        # Optional: break loop if you want it to stop on clean exit
        # break 
    else
        echo "❌ Bot crashed with exit code $EXIT_CODE."
    fi
    
    echo "⚠️ Restarting in 5 seconds... (Press Ctrl+C to stop)"
    sleep 5
done

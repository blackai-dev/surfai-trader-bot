import requests
import config

class TelegramNotifier:
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage" if self.bot_token else None

    def send_message(self, message):
        """
        Sends a message to Telegram.
        Non-blocking behavior: If network fails, it just logs error and returns.
        """
        if not self.api_url or not self.chat_id:
            # Silent fail if not configured
            return

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            # Timeout is critical here to prevent blocking the trading loop
            requests.post(self.api_url, json=payload, timeout=2) 
        except Exception as e:
            print(f"⚠️ Failed to send Telegram notification: {e}")

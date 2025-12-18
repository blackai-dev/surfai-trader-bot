import requests
import config
import json
import time
from dotenv import load_dotenv

load_dotenv()

class AIAnalyst:
    def __init__(self):
        self.api_key = config.ASKSURF_API_KEY
        self.url = "https://api.asksurf.ai/surf-ai/v1/chat/completions"

    def evaluate_stale_position(self, symbol, current_pnl_pct, hours_held, candles):
        """
        Asks AI whether to HOLD or CLOSE a stagnant position.
        Returns: "CLOSE" or "HOLD"
        """
        prompt = (
            f"I have held a position in {symbol} for {hours_held:.1f} hours.\n"
            f"Current PnL: {current_pnl_pct*100:.2f}%.\n"
            f"The price action has been stagnant or unfavorable.\n"
            f"Review the recent 20 candles below. Has the trend invalidated my original thesis?\n"
            f"Output JSON: {{\"action\": \"CLOSE\"}} or {{\"action\": \"HOLD\"}}, with reasoning.\n\n"
        )
        # Add Candle Data
        prompt += self._create_prompt(candles, None)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a Risk Manager AI. Your job is to cut dead money. If a trend is dead or reversing against us, CLOSE it. Output valid JSON: {\"action\": \"CLOSE\"/\"HOLD\", \"reasoning\": \"...\"}"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "model": "surf-ask",
            "stream": False,
            "response_format": {"type": "json_object"} 
        }

        # Reuse Simple Retry Logic
        for attempt in range(3):
            try:
                response = requests.post(self.url, headers=headers, json=payload, timeout=20)
                if response.status_code == 200:
                    try:
                        res = response.json()
                        content = res['choices'][0]['message']['content']
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0]
                        data = json.loads(content.strip())
                        return data.get("action", "HOLD").upper()
                    except:
                        return "HOLD"
            except:
                time.sleep(1)
        return "HOLD"

    def analyze_market(self, candles, indicators=None):
        """
        Sends market data to Surf AI and returns a trading signal.
        """
        prompt = self._create_prompt(candles, indicators)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a trading bot backend. You MUST output ONLY valid JSON. Do not use Markdown, tables, or bold text. Format: {\"action\": \"BUY/SELL/HOLD\", \"confidence\": 0.8, \"entry_price\": 0.0, \"stop_loss\": 0.0, \"take_profit\": 0.0, \"reasoning\": \"string\"}"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "model": "surf-ask",
            "stream": False,
            "response_format": {"type": "json_object"} 
        }

        # Retry Logic (Backoff)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(self.url, headers=headers, json=payload, timeout=20)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        content = result['choices'][0]['message']['content']
                        # parsing logic...
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0]
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0]
                        return json.loads(content.strip())
                    except Exception as e:
                        print(f"⚠️ Error parsing AI response: {e}")
                        print(f"   Raw Content: {content[:200]}...") # Debug raw
                        return None
                        
                elif response.status_code in [429, 500, 502, 503, 504]:
                    wait_time = 2 ** (attempt + 1) # 2s, 4s, 8s
                    print(f"⚠️ AI Server Error ({response.status_code}). Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ AI Request failed: {response.status_code} - {response.text}")
                    return None
                    
            except Exception as e:
                print(f"❌ AI Connection Error: {e}")
                time.sleep(2)
        
        print("❌ AI Analysis failed after retries.")
        return None

    def _create_prompt(self, candles, indicators):
        data_str = "Timestamp | Open | High | Low | Close | Volume\n"
        # Only show last 20 candles for prompt brevity, even if we fetched 100
        display_candles = candles[-20:]
        for row in display_candles:
            row_str = f"{row.get('end_timestamp')} | {row.get('open')} | {row.get('high')} | {row.get('low')} | {row.get('close')} | {row.get('volume')}"
            data_str += row_str + "\n"
        
        ma_context = ""
        if indicators:
            ma_context = (
                f"\nTechnical Indicators (State):\n"
                f"- MA{config.MA_SHORT}: {indicators.get('MA_SHORT')}\n"
                f"- MA{config.MA_MEDIUM}: {indicators.get('MA_MEDIUM')}\n"
                f"- MA{config.MA_LONG}: {indicators.get('MA_LONG')}\n"
                f"- Current Price: {indicators.get('current_price')}\n"
            )

        return (
            f"Analyze the following ETH-PERP 15m candle data for a short-term trade.\n"
            f"{ma_context}\n"
            f"{data_str}\n\n"
            f"Instructions:\n"
            f"1. **Trend Filter**: Use MAs to determine trend. If MA{config.MA_SHORT} < MA{config.MA_MEDIUM} < MA{config.MA_LONG}, it is a Strong Downtrend.\n"
            f"2. **Momentum Focus**: If price breaks BELOW MA{config.MA_LONG} with high volume, IGNORE oversold conditions (RSI) and signal SELL.\n"
            f"3. Valid signals must align with the momentum.\n"
            f"4. Provide a scalping trading signal in JSON format."
        )

    def _parse_response(self, content):
        try:
            # Find the JSON object start and end
            start = content.find('{')
            end = content.rfind('}')
            
            if start != -1 and end != -1:
                json_str = content[start:end+1]
                return json.loads(json_str)
            else:
                 # Fallback to naive cleanup
                cleaned = content.replace("```json", "").replace("```", "").strip()
                return json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"Failed to parse AI response: {content}")
            return None

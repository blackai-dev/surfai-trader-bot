
from orderly_evm_connector.rest import Rest as OrderlyClient
import config
import json

def check_filters():
    client = OrderlyClient(
        orderly_key=config.ORDERLY_KEY, 
        orderly_secret=config.ORDERLY_SECRET,
        orderly_account_id=config.ORDERLY_ACCOUNT_ID
    )
    
    print("\n--- Testing get_exchange_info (PERP_SOL_USDC) ---")
    try:
        res = client.get_exchange_info("PERP_SOL_USDC")
        print(json.dumps(res, indent=2))
    except Exception as e:
        print(f"Error get_exchange_info: {e}")
        
    print("\n--- Testing get_available_symbols ---")
    try:
        res = client.get_available_symbols()
        # Print just the first few or filter for SOL
        if res.get('success'):
            rows = res['data']['rows']
            for r in rows:
                if r['symbol'] == "PERP_SOL_USDC":
                    print(json.dumps(r, indent=2))
                    break
    except Exception as e:
        print(f"Error get_available_symbols: {e}")

if __name__ == "__main__":
    check_filters()

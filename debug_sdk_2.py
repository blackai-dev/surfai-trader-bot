
from orderly_evm_connector.rest import Rest as OrderlyClient
import config
import json

def test_methods():
    client = OrderlyClient(
        orderly_key=config.ORDERLY_KEY, 
        orderly_secret=config.ORDERLY_SECRET,
        orderly_account_id=config.ORDERLY_ACCOUNT_ID
    )
    
    print("\n--- Testing get_futures_info_for_all_markets ---")
    try:
        res = client.get_futures_info_for_all_markets()
        print(json.dumps(res, indent=2)[:1000]) # Print first 1000 chars
    except Exception as e:
        print(e)
        
if __name__ == "__main__":
    test_methods()

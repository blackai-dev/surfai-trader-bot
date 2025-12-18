
from orderly_evm_connector.rest import Rest as OrderlyClient
import config
import json

def inspect_client():
    client = OrderlyClient(
        orderly_key=config.ORDERLY_KEY, 
        orderly_secret=config.ORDERLY_SECRET,
        orderly_account_id=config.ORDERLY_ACCOUNT_ID
    )
    
    print("Listing attributes of OrderlyClient:")
    attributes = dir(client)
    for attr in attributes:
        if not attr.startswith('__'):
            print(attr)

if __name__ == "__main__":
    inspect_client()

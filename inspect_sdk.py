from orderly_evm_connector.rest import Rest
import inspect

print("Methods in Rest client:")
for name, data in inspect.getmembers(Rest):
    if name.startswith('get_') or name.startswith('public_'):
        print(name)

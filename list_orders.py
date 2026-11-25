import sys, os, requests
sys.path.insert(0, 'D:/AlgoTrading/libs')
from alpaca_config.keys import config

headers = {
    'APCA-API-KEY-ID': config['key_id'],
    'APCA-API-SECRET-KEY': config['secret_key']
}
r = requests.get('https://paper-api.alpaca.markets/v2/orders?status=all', headers=headers)
orders = r.json()
print(f"Total Paper Orders: {len(orders)}")
for o in orders[:5]:
    print(f"ID: {o['id']} | Symbol: {o['symbol']} | Qty: {o['qty']} | Side: {o['side']} | Status: {o['status']} | Created: {o['created_at']}")

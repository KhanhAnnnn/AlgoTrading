"""
verify_slack_and_send_test_ping.py — Safely verifies Slack credentials, auth, channel access,
and sends exactly ONE authorized test ping message.
NEVER outputs or logs the raw token.
"""
import os
import sys
import json
import time
import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from dotenv import load_dotenv
env_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=env_path, override=True)

from alpaca_config.keys import config

def mask_token(token: str) -> str:
    if not token or len(token) < 10:
        return "<EMPTY/INVALID>"
    return f"{token[:5]}...{token[-4:]} (len={len(token)})"

def mask_channel(ch: str) -> str:
    if not ch or len(ch) < 4:
        return "<EMPTY/INVALID>"
    return f"{ch[:3]}...{ch[-2:]} (len={len(ch)})"

def main():
    print("=" * 65)
    print("SLACK CREDENTIALS & LIVE AUTHENTICATION VERIFICATION")
    print("=" * 65)

    token = os.environ.get('SLACK_BOT_TOKEN', '').strip()
    channel = os.environ.get('SLACK_CHANNEL_ID', '').strip()

    # 1. Credentials presence check
    print(f"Token Configured: {mask_token(token)}")
    print(f"Channel Configured: {mask_channel(channel)}")

    if not token or 'YOUR' in token:
        print("ERROR: Token is still placeholder or missing.")
        sys.exit(1)
    if not channel or 'YOUR' in channel:
        print("ERROR: Channel ID is still placeholder or missing.")
        sys.exit(1)

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8'
    }

    # 2. auth.test
    print("\n[Step 1/3] Calling Slack auth.test...")
    r_auth = requests.post('https://slack.com/api/auth.test', headers=headers, timeout=10)
    auth_data = r_auth.json()
    if not auth_data.get('ok'):
        print(f"ERROR: auth.test failed: {auth_data.get('error')}")
        sys.exit(1)

    print("Slack auth.test SUCCESS:")
    print(f"  Bot User: {auth_data.get('user')}")
    print(f"  User ID: {auth_data.get('user_id')}")
    print(f"  Bot ID: {auth_data.get('bot_id')}")
    print(f"  Team: {auth_data.get('team')}")
    print(f"  Team URL: {auth_data.get('url')}")

    # 3. conversations.info
    print(f"\n[Step 2/3] Checking channel access for channel ID {channel}...")
    r_ch = requests.get('https://slack.com/api/conversations.info', headers=headers, params={'channel': channel}, timeout=10)
    ch_data = r_ch.json()
    if ch_data.get('ok'):
        ch_info = ch_data.get('channel', {})
        print(f"Channel Access SUCCESS:")
        print(f"  Channel Name: #{ch_info.get('name')}")
        print(f"  Is Channel Private: {ch_info.get('is_private')}")
        print(f"  Is Member: {ch_info.get('is_member')}")
    else:
        print(f"WARNING: conversations.info returned: {ch_data.get('error')}")
        print("Proceeding to test message dispatch (bot may have chat:write scope for public channels)...")

    # 4. Send exactly ONE authorized Test Ping
    print(f"\n[Step 3/3] Sending authorized 1-shot Test Ping to #{channel}...")
    ping_payload = {
        'channel': channel,
        'text': "AlgoTrading GĐ11 — Test Ping",
        'blocks': [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚀 AlgoTrading GĐ11 — Test Ping",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*System:*\n`AlgoTrading Bot`"},
                    {"type": "mrkdwn", "text": "*Environment:*\n`DRY_RUN (Safe)`"},
                    {"type": "mrkdwn", "text": "*Status:*\n`CONNECTED & VERIFIED`"},
                    {"type": "mrkdwn", "text": f"*Timestamp:*\n`{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}`"}
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "✅ *Live Slack Notification Pipeline Acceptance — GĐ11*"}
                ]
            }
        ]
    }

    r_msg = requests.post('https://slack.com/api/chat.postMessage', headers=headers, json=ping_payload, timeout=10)
    msg_data = r_msg.json()

    if not msg_data.get('ok'):
        print(f"ERROR: Failed to post message: {msg_data.get('error')}")
        sys.exit(1)

    print("\nTest Ping Delivered SUCCESSFULLY!")
    print(f"  API Response ok: {msg_data.get('ok')}")
    print(f"  Channel ID: {msg_data.get('channel')}")
    print(f"  Message Timestamp (ts): {msg_data.get('ts')}")
    # Safe print
    text_val = msg_data.get('message', {}).get('text', '')
    safe_text = text_val.encode('ascii', errors='replace').decode('ascii')
    print(f"  Message Text: {safe_text}")

    # Save receipt
    receipt = {
        'timestamp': time.time(),
        'iso_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'auth_test': {
            'ok': auth_data.get('ok'),
            'bot_user': auth_data.get('user'),
            'user_id': auth_data.get('user_id'),
            'bot_id': auth_data.get('bot_id'),
            'team': auth_data.get('team'),
            'team_url': auth_data.get('url')
        },
        'channel_access': {
            'channel_id': channel,
            'write_scope_verified': True
        },
        'test_ping': {
            'ok': msg_data.get('ok'),
            'channel': msg_data.get('channel'),
            'ts': msg_data.get('ts'),
            'message_text': text_val
        }
    }
    receipt_file = os.path.join(BASE_DIR, 'data', 'status', 'gd11_slack_test_ping_receipt.json')
    os.makedirs(os.path.dirname(receipt_file), exist_ok=True)
    with open(receipt_file, 'w', encoding='utf-8') as f:
        json.dump(receipt, f, indent=2)

    print(f"\nVerification receipt saved to: {receipt_file}")

if __name__ == '__main__':
    main()

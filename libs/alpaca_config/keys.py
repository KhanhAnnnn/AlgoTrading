"""
Alpaca & Slack configuration loader.
Reads credentials from .env file or environment variables.
DO NOT hardcode any API keys in this file.
"""
import os
from pathlib import Path

# Try to load .env from project root
env_file = Path(__file__).resolve().parent.parent.parent / '.env'
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_file)
    except ImportError:
        # Fallback basic .env parser
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val

config = {
    # Alpaca API credentials - set via environment variables or .env file
    'key_id': os.environ.get('ALPACA_KEY_ID', ''),
    'secret_key': os.environ.get('ALPACA_SECRET_KEY', ''),

    # Alpaca endpoints
    # News API (v1beta1 uses paper base url or data base url)
    'news_base_url': os.environ.get('ALPACA_NEWS_BASE_URL', 'https://data.alpaca.markets'),

    # Paper Trading endpoint - NEVER use live trading endpoint
    'trade_api_base_url': os.environ.get('ALPACA_TRADE_BASE_URL', 'https://paper-api.alpaca.markets'),

    # Redpanda broker addresses (host-accessible)
    'redpanda_brokers': os.environ.get(
        'REDPANDA_BROKERS', 'localhost:9092,localhost:9093'
    ).split(','),

    # Slack credentials - set via environment variables or .env file
    'slack_token': os.environ.get('SLACK_BOT_TOKEN', ''),
    'slack_channel_id': os.environ.get('SLACK_CHANNEL_ID', ''),

    # Trading mode
    'trading_mode': os.environ.get('TRADING_MODE', 'DRY_RUN').upper(),
}

# Validate that critical credentials are present at import time (warn only)
import logging
_logger = logging.getLogger(__name__)

if not config['key_id']:
    _logger.warning("ALPACA_KEY_ID is not set in .env or environment.")
if not config['secret_key']:
    _logger.warning("ALPACA_SECRET_KEY is not set in .env or environment.")

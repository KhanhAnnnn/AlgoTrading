"""
backtest/run_backtest.py — Master Backtesting Runner & Strategy Evaluation
Executes comprehensive out-of-sample backtests across:
- Assets: NVDA, AAPL (Stocks) and BTC/USD, ETH/USD (Crypto)
- Strategies:
  1. PDF Baseline (Dip-Buying Crossover)
  2. Corrected Crossover Baseline (Lagged SMA)
  3. Trend-Following Momentum
  4. Dual SMA (20/50 Golden Cross)
  5. Trend-Following with Stateful Decaying Sentiment
- Splits: Train (60%), Validation (20%), Test (20% Out-of-Sample)
- Realistic execution with t+1 open execution and friction modeling
Generates:
  data/status/gd13_backtest_results.json
  data/status/gd13_backtest_trades.csv
  data/status/gd13_strategy_comparison.csv
"""
import os
import sys
import json
import math
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATUS_DIR = os.path.join(DATA_DIR, 'status')
HISTORICAL_DIR = os.path.join(DATA_DIR, 'historical')
os.makedirs(STATUS_DIR, exist_ok=True)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backtest.engine import BacktestEngine
from backtest.strategies import (
    make_strategy_1_pdf_baseline,
    make_strategy_2_corrected_baseline,
    make_strategy_3_trend_momentum,
    make_strategy_4_dual_sma,
    make_strategy_5_decaying_sentiment
)

def prepare_merged_dataset(bars_file: str, news_file: str, symbol: str) -> pd.DataFrame:
    """Loads bars and maps sparse news sentiment onto the timeline."""
    df_bars = pd.read_csv(bars_file)
    df_news = pd.read_csv(news_file)

    # Filter by symbol
    b = df_bars[df_bars['symbol'] == symbol].copy()
    if 'timestamp_ms' in b.columns:
        b['ts_s'] = b['timestamp_ms'] // 1000
    else:
        b['ts_s'] = b['timestamp'] // 1000

    b = b.sort_values('ts_s').reset_index(drop=True)

    # Filter news
    n = df_news[df_news['symbol'] == symbol].copy()
    if not n.empty:
        n['news_ts_s'] = n['timestamp_ms'] // 1000
        # Map each news sentiment to the nearest bar without look-ahead
        # (news at t is only available at or after t)
        b['sentiment'] = 0.0
        for _, nrow in n.iterrows():
            nts = nrow['news_ts_s']
            score = float(nrow.get('sentiment', 0.0))
            # Find the bar immediately at or after news arrival
            future_bars = b[b['ts_s'] >= nts]
            if not future_bars.empty:
                first_idx = future_bars.index[0]
                b.loc[first_idx, 'sentiment'] = score
    else:
        b['sentiment'] = 0.0

    return b

def run_all_backtests():
    print("=================================================================")
    print("  AlgoTrading GD13 Quantitative Backtesting Engine Execution")
    print("=================================================================")

    # Configurations
    stocks_bars_path = os.path.join(HISTORICAL_DIR, 'stock_prices.csv')
    stocks_news_path = os.path.join(HISTORICAL_DIR, 'market_news.csv')
    crypto_bars_path = os.path.join(HISTORICAL_DIR, 'crypto_bars_1m.csv')
    crypto_news_path = os.path.join(HISTORICAL_DIR, 'crypto_news.csv')

    assets = [
        {"name": "NVDA", "type": "STOCKS", "bars": stocks_bars_path, "news": stocks_news_path, "fee": 0.0005, "slip": 0.0002},
        {"name": "AAPL", "type": "STOCKS", "bars": stocks_bars_path, "news": stocks_news_path, "fee": 0.0005, "slip": 0.0002},
        {"name": "BTC/USD", "type": "CRYPTO", "bars": crypto_bars_path, "news": crypto_news_path, "fee": 0.0025, "slip": 0.0005},
        {"name": "ETH/USD", "type": "CRYPTO", "bars": crypto_bars_path, "news": crypto_news_path, "fee": 0.0025, "slip": 0.0005},
    ]

    strategies = [
        ("Strategy 1: PDF Baseline (Dip-Buying Crossover)", make_strategy_1_pdf_baseline()),
        ("Strategy 2: Corrected Baseline (Lagged SMA)", make_strategy_2_corrected_baseline()),
        ("Strategy 3: Trend Momentum (Breakout Crossover)", make_strategy_3_trend_momentum()),
        ("Strategy 4: Dual SMA (Golden/Death Cross)", make_strategy_4_dual_sma()),
        ("Strategy 5: Stateful Decaying Sentiment", make_strategy_5_decaying_sentiment(half_life_bars=60)),
    ]

    all_results = {
        "suite": "GD13 Historical Backtest Evaluation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assets_tested": [a["name"] for a in assets],
        "evaluations": []
    }

    all_trades_flat = []
    comparison_rows = []

    for a in assets:
        sym = a["name"]
        print(f"\nEvaluating Asset: {sym} ({a['type']})")
        df_full = prepare_merged_dataset(a["bars"], a["news"], sym)
        total_bars = len(df_full)
        print(f"Loaded {total_bars} 1-minute bars with real news mapping.")

        if total_bars < 55:
            print(f"Skipping {sym}: Insufficient bars ({total_bars}) for 50-SMA warmup.")
            continue

        # Split: Train (60%), Validation (20%), Test (20% Out-of-Sample)
        idx_train = int(total_bars * 0.60)
        idx_val = int(total_bars * 0.80)

        splits = [
            ("FULL_PERIOD", df_full),
            ("TRAIN_SAMPLE", df_full.iloc[:idx_train].reset_index(drop=True)),
            ("VAL_SAMPLE", df_full.iloc[idx_train:idx_val].reset_index(drop=True)),
            ("TEST_OUT_OF_SAMPLE", df_full.iloc[idx_val:].reset_index(drop=True))
        ]

        engine = BacktestEngine(
            initial_capital=100000.0,
            fee_rate=a["fee"],
            slippage_rate=a["slip"],
            fixed_trade_size_usd=10000.0
        )

        for s_name, s_fn in strategies:
            for split_name, split_df in splits:
                if len(split_df) < 55:
                    continue

                res = engine.run(split_df, s_fn, strategy_name=s_name)
                m = res["metrics"]

                eval_record = {
                    "asset": sym,
                    "asset_type": a["type"],
                    "strategy": s_name,
                    "split": split_name,
                    "bars_count": len(split_df),
                    "metrics": m
                }
                all_results["evaluations"].append(eval_record)

                # Record for comparison CSV
                comparison_rows.append({
                    "Asset": sym,
                    "Asset_Type": a["type"],
                    "Strategy": s_name,
                    "Split": split_name,
                    "Bars": len(split_df),
                    "Total_Return_Pct": m.get("total_return_pct"),
                    "Benchmark_Return_Pct": m.get("benchmark_return_pct"),
                    "Alpha_Pct": m.get("alpha_pct"),
                    "Max_Drawdown_Pct": m.get("max_drawdown_pct"),
                    "Sharpe_Ratio": m.get("sharpe_ratio"),
                    "Trades": m.get("total_trades"),
                    "Win_Rate_Pct": m.get("win_rate_pct"),
                    "Profit_Factor": m.get("profit_factor"),
                    "Total_Fees_USD": m.get("total_fees_usd"),
                    "Total_Slippage_USD": m.get("total_slippage_usd")
                })

                # Flatten trades for trade log
                for t in res["trade_log"]:
                    t_flat = dict(t)
                    t_flat["asset"] = sym
                    t_flat["strategy"] = s_name
                    t_flat["split"] = split_name
                    all_trades_flat.append(t_flat)

            # Print Full Period summary
            full_m = next((e["metrics"] for e in all_results["evaluations"] if e["asset"] == sym and e["strategy"] == s_name and e["split"] == "FULL_PERIOD"), {})
            print(f"  [{s_name[:24]}] Return: {full_m.get('total_return_pct'):>6}% | Bench: {full_m.get('benchmark_return_pct'):>6}% | Trades: {full_m.get('total_trades'):>2} | WinRate: {full_m.get('win_rate_pct'):>5}% | MDD: {full_m.get('max_drawdown_pct'):>5}%")

    # Save Results
    json_path = os.path.join(STATUS_DIR, 'gd13_backtest_results.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2)

    df_comp = pd.DataFrame(comparison_rows)
    comp_csv_path = os.path.join(STATUS_DIR, 'gd13_strategy_comparison.csv')
    df_comp.to_csv(comp_csv_path, index=False)

    df_trades = pd.DataFrame(all_trades_flat)
    trades_csv_path = os.path.join(STATUS_DIR, 'gd13_backtest_trades.csv')
    df_trades.to_csv(trades_csv_path, index=False)

    print("\n=================================================================")
    print("  Backtest Execution Completed Successfully!")
    print(f"  Total Evaluations: {len(all_results['evaluations'])}")
    print(f"  Total Trades Simulated: {len(all_trades_flat)}")
    print(f"  JSON Results: {json_path}")
    print(f"  Comparison CSV: {comp_csv_path}")
    print(f"  Trades CSV: {trades_csv_path}")
    print("=================================================================")
    return all_results

if __name__ == '__main__':
    run_all_backtests()

"""
analytics_service.py — Quantitative Strategy Analytics Service (GĐ15.1)
Provides strategy comparison metrics, equity curves, drawdown series,
trade logs, out-of-sample evaluations, and sample-size warnings.
Guarantees quantitative integrity:
- Zero-trade Alpha is explicitly annotated as cash capital preservation, NOT predictive edge.
- Zero-trade metrics (Win Rate, Profit Factor, Sharpe) are set to None / N/A rather than misleading 0.0.
- Clear status separation between active streaming baseline (Strategy 1) vs research proposals (Strategies 2-5).
"""
import os
import json
import pandas as pd
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATUS_DIR = os.path.join(DATA_DIR, 'status')

COMP_CSV = os.path.join(STATUS_DIR, 'gd13_strategy_comparison.csv')
TRADES_CSV = os.path.join(STATUS_DIR, 'gd13_backtest_trades.csv')
RESULTS_JSON = os.path.join(STATUS_DIR, 'gd13_backtest_results.json')
EQUITY_CURVES_JSON = os.path.join(STATUS_DIR, 'gd15_equity_curves.json')

STRATEGY_DESCRIPTIONS = {
    1: {
        "title": "PDF Baseline",
        "name": "Strategy 1: PDF Baseline (Dip-Buying Crossover)",
        "tag": "STREAMING_PRODUCTION_BASELINE",
        "description": "Original specification from Real-Time Algorithmic Trading PDF: sentiment > 0 AND close < SMA20 AND lag >= SMA20.",
        "status": "ACTIVE_FLINK_STREAMING_PRODUCTION",
        "is_production": True,
    },
    2: {
        "title": "Corrected Baseline",
        "name": "Strategy 2: Corrected Baseline (Lagged SMA)",
        "tag": "ANALYTICAL_STUDY",
        "description": "Corrects phantom crossover by comparing lag_close against lag_sma20 rather than current sma20.",
        "status": "RESEARCH_STUDY_NOT_DEPLOYED",
        "is_production": False,
    },
    3: {
        "title": "Trend Momentum",
        "name": "Strategy 3: Trend Momentum (Breakout Crossover)",
        "tag": "ANALYTICAL_STUDY",
        "description": "Bullish breakout strategy: buys when price crosses ABOVE SMA20 with positive sentiment.",
        "status": "RESEARCH_STUDY_NOT_DEPLOYED",
        "is_production": False,
    },
    4: {
        "title": "Dual SMA Cross",
        "name": "Strategy 4: Dual SMA (Golden/Death Cross)",
        "tag": "ANALYTICAL_STUDY",
        "description": "Classic Golden Cross (SMA20 crosses above SMA50) + Death Cross with sentiment confirmation.",
        "status": "RESEARCH_STUDY_NOT_DEPLOYED",
        "is_production": False,
    },
    5: {
        "title": "Decaying Sentiment",
        "name": "Strategy 5: Stateful Decaying Sentiment",
        "tag": "RESEARCH_PROPOSAL",
        "description": "Persistent memory buffer with exponential half-life decay (60m) to decouple sparse news from 1m candles.",
        "status": "RESEARCH_STUDY_NOT_DEPLOYED",
        "is_production": False,
    },
}

_STRAT_CACHE = {}
_STRAT_CACHE_TIME = 0.0


def get_strategies_summary(asset: str = "NVDA", split: str = "FULL_PERIOD") -> List[Dict[str, Any]]:
    """Returns the 5 quantitative strategies with performance metrics for the requested asset and split."""
    global _STRAT_CACHE, _STRAT_CACHE_TIME
    import time
    cache_key = f"{asset}_{split}"
    if (time.time() - _STRAT_CACHE_TIME) < 10.0 and cache_key in _STRAT_CACHE:
        return _STRAT_CACHE[cache_key]

    if not os.path.exists(COMP_CSV):
        return []

    try:
        df = pd.read_csv(COMP_CSV)
        filtered = df[(df['Asset'] == asset) & (df['Split'] == split)].copy()
        if filtered.empty:
            # Fallback to NVDA if asset not found
            filtered = df[(df['Asset'] == 'NVDA') & (df['Split'] == split)].copy()

        strategies_list = []
        for s_idx in range(1, 6):
            meta = STRATEGY_DESCRIPTIONS.get(s_idx, {})
            s_name = meta.get("name", "")
            row = filtered[filtered['Strategy'] == s_name]

            if not row.empty:
                r = row.iloc[0]
                trades = int(r.get('Trades', 0))
                ret_pct = float(r.get('Total_Return_Pct', 0.0))
                bench_pct = float(r.get('Benchmark_Return_Pct', 0.0))
                alpha_pct = float(r.get('Alpha_Pct', 0.0))
                mdd_pct = float(r.get('Max_Drawdown_Pct', 0.0))
                sharpe_str = str(r.get('Sharpe_Ratio', 'N/A'))
                win_rate = float(r.get('Win_Rate_Pct', 0.0)) if trades > 0 else None
                pf = float(r.get('Profit_Factor', 0.0)) if trades > 0 else None
                fees = float(r.get('Total_Fees_USD', 0.0))
                slip = float(r.get('Total_Slippage_USD', 0.0))
            else:
                trades = 0
                ret_pct = 0.0
                bench_pct = 0.0
                alpha_pct = 0.0
                mdd_pct = 0.0
                sharpe_str = 'N/A'
                win_rate = None
                pf = None
                fees = 0.0
                slip = 0.0

            # Alpha annotation guard
            alpha_note = None
            if trades == 0:
                sharpe_str = 'N/A'
                if alpha_pct > 0:
                    alpha_note = "Alpha reflects cash capital preservation during market dip; zero predictive trades executed."
                else:
                    alpha_note = "Zero trades executed; portfolio remained 100% cash."

            sample_warning = trades < 30
            if trades == 0:
                sample_msg = "Notice: Zero trades executed in this evaluation partition. Portfolio remained in cash."
            elif trades < 30:
                sample_msg = f"Warning: Small sample size (N = {trades} < 30 trades). Statistical metrics have wide confidence intervals; avoid overfitting."
            else:
                sample_msg = None

            strategies_list.append({
                "strategy_id": s_idx,
                "strategy_name": s_name,
                "short_title": meta.get("title"),
                "tag": meta.get("tag"),
                "description": meta.get("description"),
                "is_production": meta.get("is_production", False),
                "status": meta.get("status"),
                "asset": asset,
                "split": split,
                "total_return_pct": ret_pct,
                "benchmark_return_pct": bench_pct,
                "alpha_pct": alpha_pct,
                "alpha_annotation": alpha_note,
                "max_drawdown_pct": mdd_pct,
                "sharpe_ratio": sharpe_str,
                "total_trades": trades,
                "win_rate_pct": win_rate,
                "profit_factor": pf,
                "total_fees_usd": fees,
                "total_slippage_usd": slip,
                "sample_size_warning": sample_warning,
                "sample_size_message": sample_msg,
                "data_source_mode": "BACKTEST_HISTORICAL_EVALUATION"
            })

        _STRAT_CACHE[cache_key] = strategies_list
        _STRAT_CACHE_TIME = time.time()
        return strategies_list
    except Exception as e:
        print(f"Error loading strategy summary: {e}")
        return []


def get_equity_curve(asset: str = "NVDA", strategy_id: int = 1) -> Dict[str, Any]:
    """Returns the pre-calculated equity curve and drawdown curve for asset & strategy."""
    if os.path.exists(EQUITY_CURVES_JSON):
        try:
            with open(EQUITY_CURVES_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            asset_data = data.get(asset) or data.get('NVDA', {})
            strat_data = asset_data.get(str(strategy_id)) or asset_data.get('1', {})

            pts = strat_data.get('points', [])
            peak = 100000.0
            enriched_pts = []
            for p in pts:
                eq = float(p.get('equity', 100000.0))
                if eq > peak:
                    peak = eq
                dd = round(((peak - eq) / peak) * 100.0, 3) if peak > 0 else 0.0
                enriched_pts.append({
                    "time": p.get('time'),
                    "equity": eq,
                    "drawdown_pct": dd,
                    "benchmark_close": p.get('benchmark_close')
                })

            return {
                "asset": asset,
                "strategy_id": strategy_id,
                "strategy_name": strat_data.get('strategy_name', f"Strategy {strategy_id}"),
                "initial_capital": strat_data.get('initial_capital', 100000.0),
                "final_equity": strat_data.get('final_equity', 100000.0),
                "points_count": len(enriched_pts),
                "points": enriched_pts,
                "data_mode": "BACKTEST_REPLAY"
            }
        except Exception as e:
            print(f"Error reading equity curves: {e}")

    return {
        "asset": asset,
        "strategy_id": strategy_id,
        "strategy_name": f"Strategy {strategy_id}",
        "initial_capital": 100000.0,
        "final_equity": 100000.0,
        "points_count": 0,
        "points": [],
        "data_mode": "EMPTY_STATE"
    }


def get_historical_trades(asset: Optional[str] = None, strategy_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Returns list of trades simulated in GD13 backtests."""
    if not os.path.exists(TRADES_CSV):
        return []

    try:
        df = pd.read_csv(TRADES_CSV)
        if asset:
            df = df[df['asset'] == asset]
        if strategy_id and strategy_id in STRATEGY_DESCRIPTIONS:
            s_name = STRATEGY_DESCRIPTIONS[strategy_id]['name']
            df = df[df['strategy'] == s_name]

        trades = []
        for _, row in df.iterrows():
            trades.append({
                "trade_id": int(row.get('trade_id', 0)),
                "asset": str(row.get('asset', '')),
                "strategy": str(row.get('strategy', '')),
                "split": str(row.get('split', '')),
                "side": str(row.get('side', '')),
                "entry_bar": int(row.get('entry_bar', 0)),
                "exit_bar": int(row.get('exit_bar', 0)),
                "holding_bars": int(row.get('holding_bars', 0)),
                "entry_price": round(float(row.get('entry_price', 0.0)), 4),
                "exit_price": round(float(row.get('exit_price', 0.0)), 4),
                "qty": round(float(row.get('qty', 0.0)), 6),
                "pnl": round(float(row.get('pnl', 0.0)), 2),
                "pnl_pct": round(float(row.get('pnl_pct', 0.0)), 2),
                "fees": round(float(row.get('fees', 0.0)), 2),
                "slippage": round(float(row.get('slippage', 0.0)), 2),
                "exit_time": int(row.get('exit_time', 0)) if pd.notnull(row.get('exit_time')) else None
            })
        return trades
    except Exception as e:
        print(f"Error loading trades: {e}")
        return []


def get_out_of_sample_splits(asset: str = "NVDA", strategy_id: int = 1) -> List[Dict[str, Any]]:
    """Returns performance breakdown across Train (60%), Val (20%), and Test Out-of-Sample (20%)."""
    if not os.path.exists(COMP_CSV):
        return []

    try:
        df = pd.read_csv(COMP_CSV)
        s_name = STRATEGY_DESCRIPTIONS.get(strategy_id, {}).get("name", "")
        filtered = df[(df['Asset'] == asset) & (df['Strategy'] == s_name)].copy()

        splits_data = []
        for split in ['TRAIN_SAMPLE', 'VAL_SAMPLE', 'TEST_OUT_OF_SAMPLE', 'FULL_PERIOD']:
            row = filtered[filtered['Split'] == split]
            if not row.empty:
                r = row.iloc[0]
                trades = int(r.get('Trades', 0))
                splits_data.append({
                    "split": split,
                    "split_label": "Train (In-Sample 60%)" if split == 'TRAIN_SAMPLE' else ("Validation (20%)" if split == 'VAL_SAMPLE' else ("Test (Out-of-Sample 20%)" if split == 'TEST_OUT_OF_SAMPLE' else "Full Dataset (100%)")),
                    "bars": int(r.get('Bars', 0)),
                    "total_return_pct": float(r.get('Total_Return_Pct', 0.0)),
                    "benchmark_return_pct": float(r.get('Benchmark_Return_Pct', 0.0)),
                    "alpha_pct": float(r.get('Alpha_Pct', 0.0)),
                    "max_drawdown_pct": float(r.get('Max_Drawdown_Pct', 0.0)),
                    "trades": trades,
                    "win_rate_pct": float(r.get('Win_Rate_Pct', 0.0)) if trades > 0 else None,
                    "sharpe_ratio": str(r.get('Sharpe_Ratio', 'N/A')) if trades > 0 else 'N/A'
                })
        return splits_data
    except Exception as e:
        print(f"Error loading splits: {e}")
        return []

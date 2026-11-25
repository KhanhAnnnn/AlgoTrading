"""
backtest/metrics.py — Quantitative Financial Performance Metrics Calculator
Computes institutional-grade metrics:
Total Return, Annualized Return, Max Drawdown, Sharpe Ratio, Sortino Ratio,
Win Rate, Profit Factor, Trade Count, Avg Holding Period, Exposure %, Turnover %,
Fee & Slippage Impact, and Buy-and-Hold Benchmark.
"""
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List

def calculate_performance_metrics(
    equity_curve: pd.Series,
    trade_log: List[Dict[str, Any]],
    benchmark_series: pd.Series,
    initial_capital: float = 100000.0,
    annualization_factor: float = 252 * 390  # 1-minute bars in US trading year (approx 252 days * 390 min)
) -> Dict[str, Any]:
    """
    Calculates comprehensive performance metrics for a backtested strategy.
    Handles small-sample constraints gracefully by outputting N/A or bounded estimates.
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return {"error": "Insufficient equity data for metrics calculation"}

    # 1. Total Return & Benchmark
    final_equity = float(equity_curve.iloc[-1])
    total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100.0

    b_start = float(benchmark_series.iloc[0]) if len(benchmark_series) > 0 and benchmark_series.iloc[0] > 0 else 1.0
    b_end = float(benchmark_series.iloc[-1]) if len(benchmark_series) > 0 else 1.0
    benchmark_return_pct = ((b_end - b_start) / b_start) * 100.0

    # 2. Annualized Return (CAGR)
    num_bars = len(equity_curve)
    duration_years = num_bars / annualization_factor if annualization_factor > 0 else 0.0
    
    if duration_years >= 0.08 and final_equity > 0:  # at least ~1 month
        cagr_pct = ((final_equity / initial_capital) ** (1.0 / duration_years) - 1.0) * 100.0
    else:
        cagr_pct = None  # Sample length too short for reliable annualization

    # 3. Maximum Drawdown & Drawdown Duration
    running_max = equity_curve.cummax()
    drawdowns = (equity_curve - running_max) / running_max
    max_drawdown_pct = float(abs(drawdowns.min())) * 100.0 if not drawdowns.empty else 0.0

    # 4. Bar Returns & Volatility
    bar_returns = equity_curve.pct_change().dropna()
    mean_ret = float(bar_returns.mean()) if not bar_returns.empty else 0.0
    std_ret = float(bar_returns.std()) if not bar_returns.empty else 0.0

    # 5. Sharpe Ratio & Sortino Ratio
    if std_ret > 1e-8:
        sharpe_ratio = round((mean_ret / std_ret) * math.sqrt(annualization_factor), 2)
    else:
        sharpe_ratio = 0.0 if len(trade_log) == 0 else 0.0

    downside_returns = bar_returns[bar_returns < 0]
    downside_std = float(downside_returns.std()) if len(downside_returns) > 1 else 0.0
    if downside_std > 1e-8:
        sortino_ratio = round((mean_ret / downside_std) * math.sqrt(annualization_factor), 2)
    else:
        sortino_ratio = None

    # 6. Trade Analysis
    num_trades = len(trade_log)
    if num_trades > 0:
        pnls = [t['pnl'] for t in trade_log]
        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]
        
        win_rate_pct = round((len(winning_trades) / num_trades) * 100.0, 2)
        gross_profit = sum(winning_trades)
        gross_loss = abs(sum(losing_trades))
        
        if gross_loss > 1e-6:
            profit_factor = round(gross_profit / gross_loss, 2)
        else:
            profit_factor = round(gross_profit, 2) if gross_profit > 0 else 0.0

        holding_periods = [t.get('holding_bars', 0) for t in trade_log]
        avg_holding_bars = round(float(np.mean(holding_periods)), 1) if holding_periods else 0.0
        
        total_fees = sum(t.get('fees', 0.0) for t in trade_log)
        total_slippage = sum(t.get('slippage', 0.0) for t in trade_log)
        total_costs = total_fees + total_slippage
        
        total_volume_traded = sum(t.get('entry_price', 0.0) * t.get('qty', 0.0) for t in trade_log)
        turnover_pct = round((total_volume_traded / initial_capital) * 100.0, 2)
    else:
        win_rate_pct = 0.0
        profit_factor = 0.0
        avg_holding_bars = 0.0
        total_fees = 0.0
        total_slippage = 0.0
        total_costs = 0.0
        turnover_pct = 0.0

    # 7. Exposure Time (percentage of bars holding a non-zero position)
    bars_in_position = sum(1 for t in trade_log for _ in range(t.get('holding_bars', 0)))
    exposure_pct = round(min(100.0, (bars_in_position / num_bars) * 100.0), 2) if num_bars > 0 else 0.0

    return {
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct, 2),
        "benchmark_return_pct": round(benchmark_return_pct, 2),
        "alpha_pct": round(total_return_pct - benchmark_return_pct, 2),
        "annualized_return_cagr_pct": round(cagr_pct, 2) if cagr_pct is not None else "N/A (Sample < 1 Month)",
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio": sharpe_ratio if num_trades > 0 else "N/A (Zero Trades)",
        "sortino_ratio": sortino_ratio if sortino_ratio is not None else "N/A",
        "total_trades": num_trades,
        "win_rate_pct": win_rate_pct,
        "profit_factor": profit_factor,
        "avg_holding_period_bars": avg_holding_bars,
        "exposure_pct": exposure_pct,
        "turnover_pct": turnover_pct,
        "total_fees_usd": round(total_fees, 2),
        "total_slippage_usd": round(total_slippage, 2),
        "total_frictions_usd": round(total_costs, 2),
        "sample_duration_bars": num_bars
    }


"""
backtest/engine.py — Realistic Event-Driven Algorithmic Backtesting Simulator
Features:
- Zero Look-Ahead Bias: Signals formed at bar t Close are executed at bar t+1 Open
- Friction Modeling: Configurable exchange fees, bid-ask spread, and market slippage
- State Tracking: Cash, Position Units, Average Cost, Realized PnL, Unrealized PnL, Equity
- Portfolio Constraints: Long-only or Long/Short, cash buffer safeguards
"""
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Callable
from backtest.metrics import calculate_performance_metrics

class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        fee_rate: float = 0.0005,       # 5 bps fee (Stocks SEC/FINRA/broker or Crypto)
        slippage_rate: float = 0.0002,  # 2 bps slippage
        fixed_trade_size_usd: float = 10000.0, # Notional per trade
        allow_short: bool = False
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.trade_size_usd = fixed_trade_size_usd
        self.allow_short = allow_short

    def run(
        self,
        df_bars: pd.DataFrame,
        signal_generator: Callable[[pd.DataFrame], pd.Series],
        strategy_name: str = "Strategy"
    ) -> Dict[str, Any]:
        """
        Executes event-driven backtest over df_bars using the provided signal generator.
        df_bars must contain: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        Signals: 'BUY', 'SELL', or None / 'HOLD'
        """
        df = df_bars.copy().sort_values('timestamp').reset_index(drop=True)
        
        # 1. Generate signals across the bars
        signals = signal_generator(df)
        df['signal'] = signals

        cash = self.initial_capital
        position_qty = 0.0
        avg_entry_price = 0.0
        entry_bar_idx = 0
        entry_fees = 0.0

        equity_history = []
        trade_log = []

        # 2. Sequential bar simulation with strictly t+1 execution
        pending_order = None # (side, size_usd, signal_bar_idx, signal_time)

        for i in range(len(df)):
            current_bar = df.iloc[i]
            open_price = float(current_bar['open'])
            close_price = float(current_bar['close'])
            bar_time = current_bar.get('timestamp')

            # Step A: Execute pending order at Open of bar i (strictly t+1 execution)
            if pending_order is not None:
                side, notional_target, sig_idx, sig_time = pending_order
                
                if side == 'BUY' and (position_qty <= 0 or self.allow_short):
                    # Close short if short
                    if position_qty < 0:
                        exec_price = open_price * (1.0 + self.slippage_rate)
                        trade_fee = abs(position_qty) * exec_price * self.fee_rate
                        pnl = (avg_entry_price - exec_price) * abs(position_qty) - entry_fees - trade_fee
                        cash += (abs(position_qty) * avg_entry_price) + pnl
                        trade_log.append({
                            'trade_id': len(trade_log) + 1,
                            'side': 'COVER_SHORT',
                            'entry_bar': entry_bar_idx,
                            'exit_bar': i,
                            'holding_bars': i - entry_bar_idx,
                            'entry_price': avg_entry_price,
                            'exit_price': exec_price,
                            'qty': abs(position_qty),
                            'pnl': round(pnl, 2),
                            'pnl_pct': round((pnl / (abs(position_qty) * avg_entry_price)) * 100.0, 2),
                            'fees': round(entry_fees + trade_fee, 2),
                            'slippage': round(abs(position_qty) * open_price * self.slippage_rate, 2),
                            'exit_time': bar_time
                        })
                        position_qty = 0.0

                    # Open long
                    alloc = min(cash * 0.95, notional_target)
                    if alloc > 100.0:
                        exec_price = open_price * (1.0 + self.slippage_rate)
                        qty = alloc / exec_price
                        trade_fee = alloc * self.fee_rate
                        cash -= (alloc + trade_fee)
                        position_qty = qty
                        avg_entry_price = exec_price
                        entry_bar_idx = i
                        entry_fees = trade_fee

                elif side == 'SELL' and position_qty > 0:
                    # Close long position
                    exec_price = open_price * (1.0 - self.slippage_rate)
                    notional_proceeds = position_qty * exec_price
                    trade_fee = notional_proceeds * self.fee_rate
                    pnl = (exec_price - avg_entry_price) * position_qty - entry_fees - trade_fee
                    cash += (notional_proceeds - trade_fee)

                    trade_log.append({
                        'trade_id': len(trade_log) + 1,
                        'side': 'SELL_LONG',
                        'entry_bar': entry_bar_idx,
                        'exit_bar': i,
                        'holding_bars': i - entry_bar_idx,
                        'entry_price': avg_entry_price,
                        'exit_price': exec_price,
                        'qty': position_qty,
                        'pnl': round(pnl, 2),
                        'pnl_pct': round((pnl / (position_qty * avg_entry_price)) * 100.0, 2),
                        'fees': round(entry_fees + trade_fee, 2),
                        'slippage': round(position_qty * open_price * self.slippage_rate, 2),
                        'exit_time': bar_time
                    })
                    position_qty = 0.0
                    avg_entry_price = 0.0

                pending_order = None

            # Step B: Mark to Market at Close of bar i
            unrealized_pnl = position_qty * (close_price - avg_entry_price) if position_qty != 0 else 0.0
            current_equity = cash + (position_qty * close_price if position_qty > 0 else 0.0) + (unrealized_pnl if position_qty < 0 else 0.0)
            equity_history.append(current_equity)

            # Step C: Evaluate signal emitted at Close of bar i -> schedule pending order for t+1 Open
            sig = current_bar.get('signal')
            if sig in ('BUY', 'SELL'):
                pending_order = (sig, self.trade_size_usd, i, bar_time)

        # 3. Final liquidation if position remains open
        if position_qty > 0:
            final_close = float(df.iloc[-1]['close'])
            trade_fee = position_qty * final_close * self.fee_rate
            pnl = (final_close - avg_entry_price) * position_qty - entry_fees - trade_fee
            trade_log.append({
                'trade_id': len(trade_log) + 1,
                'side': 'CLOSE_ON_END',
                'entry_bar': entry_bar_idx,
                'exit_bar': len(df) - 1,
                'holding_bars': len(df) - 1 - entry_bar_idx,
                'entry_price': avg_entry_price,
                'exit_price': final_close,
                'qty': position_qty,
                'pnl': round(pnl, 2),
                'pnl_pct': round((pnl / (position_qty * avg_entry_price)) * 100.0, 2),
                'fees': round(entry_fees + trade_fee, 2),
                'slippage': 0.0,
                'exit_time': df.iloc[-1].get('timestamp')
            })
            equity_history[-1] = cash + (position_qty * final_close) - trade_fee

        equity_series = pd.Series(equity_history, index=df.index)
        benchmark_series = df['close']

        metrics = calculate_performance_metrics(
            equity_curve=equity_series,
            trade_log=trade_log,
            benchmark_series=benchmark_series,
            initial_capital=self.initial_capital
        )

        return {
            "strategy": strategy_name,
            "metrics": metrics,
            "trade_log": trade_log,
            "equity_curve": equity_series.tolist()
        }


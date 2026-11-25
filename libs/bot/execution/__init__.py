"""
libs/bot/execution/__init__.py — Order Management & Simulation Broker Exports (GĐ33)
"""

from libs.bot.execution.lifecycle import (
    OrderState,
    TERMINAL_STATES,
    ACTIVE_STATES,
    OrderLifecycleStateMachine,
    InvalidOrderStateTransitionError,
)
from libs.bot.execution.slippage import (
    SlippageModel,
    ZeroSlippageModel,
    FixedBpsSlippageModel,
    ConfigurableImpactSlippageModel,
)
from libs.bot.execution.fees import (
    FeeModel,
    ZeroFeeModel,
    ConfigurableFeeModel,
    FeeResult,
)
from libs.bot.execution.fill_engine import FillEngine
from libs.bot.execution.portfolio_adapter import PortfolioExecutionAdapter
from libs.bot.execution.ledger import ExecutionLedger, LedgerEntry, ReconciliationReport
from libs.bot.execution.order_store import OrderStore
from libs.bot.execution.fill_store import FillStore
from libs.bot.execution.order_manager import SimulationOrderManager
from libs.bot.execution.simulation_broker import SimulationBroker

__all__ = [
    "OrderState",
    "TERMINAL_STATES",
    "ACTIVE_STATES",
    "OrderLifecycleStateMachine",
    "InvalidOrderStateTransitionError",
    "SlippageModel",
    "ZeroSlippageModel",
    "FixedBpsSlippageModel",
    "ConfigurableImpactSlippageModel",
    "FeeModel",
    "ZeroFeeModel",
    "ConfigurableFeeModel",
    "FeeResult",
    "FillEngine",
    "PortfolioExecutionAdapter",
    "ExecutionLedger",
    "LedgerEntry",
    "ReconciliationReport",
    "OrderStore",
    "FillStore",
    "SimulationOrderManager",
    "SimulationBroker",
]

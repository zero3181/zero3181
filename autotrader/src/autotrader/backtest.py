"""단일 종목 일봉 백테스트.

미래 데이터 참조를 막기 위한 규칙:
- i번째 봉의 종가까지 보고 신호를 낸다.
- 주문은 다음 봉(i+1)의 시가에 체결된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from autotrader.models import BAR_COLUMNS, Position, Side
from autotrader.risk import AccountState, RiskManager
from autotrader.strategy.base import Strategy


@dataclass(frozen=True)
class CostModel:
    fee_rate: float = 0.00015  # 매매 수수료 (예시값. 실제 수수료 확인 필요)
    sell_tax_rate: float = 0.0018  # 매도 시 세금 (예시값. 국내 증권거래세는 연도/시장별로 다름)
    slippage_rate: float = 0.0005  # 체결가 불리 가정


@dataclass
class Trade:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    quantity: int
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl: float | None = None  # 비용 포함 손익


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[Trade]
    metrics: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        m = self.metrics
        lines = [
            f"총 수익률        : {m['total_return']:.2%}",
            f"연환산 수익률    : {m['cagr']:.2%}",
            f"최대 낙폭(MDD)   : {m['max_drawdown']:.2%}",
            f"거래 횟수        : {int(m['num_trades'])}",
            f"승률             : {m['win_rate']:.2%}",
            f"단순 보유 수익률 : {m['buy_hold_return']:.2%}  (비교 기준)",
        ]
        return "\n".join(lines)


def validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in BAR_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(f"시세 데이터에 컬럼이 없습니다: {missing}")
    if not bars.index.is_monotonic_increasing:
        bars = bars.sort_index()
    return bars


def run_backtest(
    symbol: str,
    bars: pd.DataFrame,
    strategy: Strategy,
    risk: RiskManager,
    initial_cash: float,
    costs: CostModel | None = None,
) -> BacktestResult:
    bars = validate_bars(bars)
    costs = costs or CostModel()

    cash = initial_cash
    position: Position | None = None
    pending = None  # 다음 봉 시가에 체결할 OrderRequest
    trades: list[Trade] = []
    equity_points: list[float] = []

    current_day = None
    day_start_equity = initial_cash
    buys_today = 0
    last_equity = initial_cash

    for i, (ts, row) in enumerate(bars.iterrows()):
        day = ts.date() if hasattr(ts, "date") else ts
        if day != current_day:
            current_day = day
            day_start_equity = last_equity
            buys_today = 0

        # 1) 직전 봉에서 낸 주문을 이번 봉 시가에 체결
        if pending is not None:
            if pending.side == Side.BUY:
                fill = row["open"] * (1 + costs.slippage_rate)
                # 신호는 전날 종가로 수량을 정했으므로, 시가가 올라 현금이 모자라면 살 수 있는 만큼만 산다.
                affordable = int(cash // (fill * (1 + costs.fee_rate)))
                qty = min(pending.quantity, affordable)
                if qty >= 1:
                    cash -= fill * qty * (1 + costs.fee_rate)
                    position = Position(symbol, qty, fill)
                    trades.append(Trade(symbol, ts, fill, qty))
                    buys_today += 1
            elif position is not None:
                fill = row["open"] * (1 - costs.slippage_rate)
                proceeds = fill * position.quantity * (1 - costs.fee_rate - costs.sell_tax_rate)
                cash += proceeds
                t = trades[-1]
                t.exit_time, t.exit_price = ts, fill
                t.pnl = proceeds - t.entry_price * t.quantity * (1 + costs.fee_rate)
                position = None
            pending = None

        # 2) 종가 기준 평가금
        holding_value = position.quantity * row["close"] if position else 0.0
        last_equity = cash + holding_value
        equity_points.append(last_equity)

        # 3) 이번 봉 종가까지 보고 신호 생성 (마지막 봉은 다음 체결 기회가 없으므로 생략)
        if i + 1 < strategy.min_bars or i == len(bars) - 1:
            continue
        signal = strategy.generate(symbol, bars.iloc[: i + 1], position)
        if signal is None:
            continue
        account = AccountState(
            cash=cash,
            positions={symbol: position} if position else {},
            equity=last_equity,
            day_start_equity=day_start_equity,
            buys_today=buys_today,
        )
        decision = risk.evaluate(signal, row["close"], account)
        if decision.approved:
            pending = decision.order

    equity = pd.Series(equity_points, index=bars.index, name="equity")
    return BacktestResult(equity, trades, _metrics(equity, trades, bars))


def _metrics(equity: pd.Series, trades: list[Trade], bars: pd.DataFrame) -> dict[str, float]:
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    days = (bars.index[-1] - bars.index[0]).days if isinstance(bars.index, pd.DatetimeIndex) else 0
    years = days / 365.25
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else float("nan")
    drawdown = equity / equity.cummax() - 1
    closed = [t for t in trades if t.pnl is not None]
    wins = sum(1 for t in closed if t.pnl > 0)
    return {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "max_drawdown": float(drawdown.min()),
        "num_trades": float(len(closed)),
        "win_rate": wins / len(closed) if closed else 0.0,
        "buy_hold_return": float(bars["close"].iloc[-1] / bars["close"].iloc[0] - 1),
    }


def make_demo_bars(days: int = 750, seed: int = 42, start_price: float = 50_000) -> pd.DataFrame:
    """테스트/데모용 가짜 일봉 (랜덤워크). 실제 시장 데이터가 아니다."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=days)
    rets = rng.normal(0.0003, 0.02, size=days)
    close = start_price * np.exp(np.cumsum(rets))
    open_ = close * (1 + rng.normal(0, 0.005, size=days))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, size=days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, size=days)))
    volume = rng.integers(100_000, 1_000_000, size=days)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )

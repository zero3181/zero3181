import pandas as pd

from autotrader.backtest import CostModel, make_demo_bars, run_backtest
from autotrader.models import Position, Side, Signal
from autotrader.risk import RiskLimits, RiskManager
from autotrader.strategy.base import Strategy


class BuyOnBar(Strategy):
    """지정한 봉 번호에서 매수, 다음 지정 봉에서 매도."""

    name = "test"

    def __init__(self, buy_at: int, sell_at: int):
        self.buy_at, self.sell_at = buy_at, sell_at
        self.seen_lengths = []

    @property
    def min_bars(self):
        return 1

    def generate(self, symbol, bars, position):
        self.seen_lengths.append(len(bars))
        n = len(bars) - 1
        if n == self.buy_at and position is None:
            return Signal(symbol, Side.BUY)
        if n == self.sell_at and position is not None:
            return Signal(symbol, Side.SELL)
        return None


def _bars(opens, closes):
    idx = pd.bdate_range("2024-01-01", periods=len(opens))
    return pd.DataFrame(
        {"open": opens, "high": closes, "low": opens, "close": closes, "volume": 1}, index=idx
    )


def test_fills_at_next_open_no_lookahead():
    bars = _bars(opens=[100, 110, 120, 130], closes=[100, 115, 125, 135])
    strat = BuyOnBar(buy_at=0, sell_at=1)
    risk = RiskManager(RiskLimits(max_order_value=1000))
    res = run_backtest("A", bars, strat, risk, initial_cash=1000, costs=CostModel(0, 0, 0))

    # 전략은 항상 '지금까지'의 봉만 받는다
    assert strat.seen_lengths == [1, 2, 3]
    t = res.trades[0]
    # 0번 봉 종가(100) 기준 10주 신호 → 1번 봉 시가 110에 체결.
    # 10주 * 110 = 1100 > 현금 1000 이므로 살 수 있는 9주만 산다.
    assert t.entry_price == 110 and t.quantity == 9
    # 1번 봉에서 매도 신호 → 2번 봉 시가 120에 체결
    assert t.exit_price == 120
    assert t.pnl == 9 * (120 - 110)


def test_costs_reduce_return():
    bars = make_demo_bars(days=300)

    def run(costs):
        strat = BuyOnBar(buy_at=10, sell_at=200)
        risk = RiskManager(RiskLimits(max_order_value=10_000_000))
        return run_backtest("A", bars, strat, risk, 10_000_000, costs).metrics["total_return"]

    assert run(CostModel(0.001, 0.002, 0.001)) < run(CostModel(0, 0, 0))


def test_demo_backtest_runs():
    from autotrader.strategy import MovingAverageCross

    res = run_backtest(
        "DEMO",
        make_demo_bars(),
        MovingAverageCross(5, 20),
        RiskManager(RiskLimits(max_order_value=10_000_000)),
        10_000_000,
    )
    assert len(res.equity) == 750
    assert -1 <= res.metrics["max_drawdown"] <= 0

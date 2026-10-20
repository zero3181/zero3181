from autotrader.models import Position, Side, Signal
from autotrader.risk import AccountState, RiskLimits, RiskManager


def account(**kw):
    base = dict(cash=1_000_000, positions={}, equity=1_000_000, day_start_equity=1_000_000, buys_today=0)
    base.update(kw)
    return AccountState(**base)


BUY = Signal("A", Side.BUY)
SELL = Signal("A", Side.SELL)


def test_buy_sized_by_max_order_value():
    rm = RiskManager(RiskLimits(max_order_value=100_000))
    d = rm.evaluate(BUY, 30_000, account())
    assert d.order.quantity == 3


def test_buy_limited_by_cash():
    rm = RiskManager(RiskLimits(max_order_value=1_000_000))
    d = rm.evaluate(BUY, 30_000, account(cash=50_000))
    assert d.order.quantity == 1


def test_buy_rejected_when_too_expensive():
    rm = RiskManager(RiskLimits(max_order_value=10_000))
    assert not rm.evaluate(BUY, 30_000, account()).approved


def test_daily_loss_limit_blocks_buy_but_not_sell():
    rm = RiskManager(RiskLimits(max_order_value=100_000, daily_loss_limit_pct=0.03))
    acc = account(equity=960_000, positions={"A": Position("A", 5, 1000)})
    assert not rm.evaluate(Signal("B", Side.BUY), 1000, acc).approved
    d = rm.evaluate(SELL, 1000, acc)
    assert d.approved and d.order.quantity == 5


def test_max_buys_per_day():
    rm = RiskManager(RiskLimits(max_order_value=100_000, max_buys_per_day=2))
    assert not rm.evaluate(BUY, 1000, account(buys_today=2)).approved


def test_max_positions():
    rm = RiskManager(RiskLimits(max_order_value=100_000, max_positions=1))
    acc = account(positions={"X": Position("X", 1, 1000)})
    assert not rm.evaluate(BUY, 1000, acc).approved


def test_sell_without_position_rejected():
    rm = RiskManager(RiskLimits(max_order_value=100_000))
    assert not rm.evaluate(SELL, 1000, account()).approved


def test_kill_switch_blocks_everything(tmp_path):
    stop = tmp_path / "STOP"
    rm = RiskManager(RiskLimits(max_order_value=100_000), kill_switch_path=stop)
    acc = account(positions={"A": Position("A", 5, 1000)})
    assert rm.evaluate(SELL, 1000, acc).approved
    stop.touch()
    assert not rm.evaluate(SELL, 1000, acc).approved
    assert not rm.evaluate(BUY, 1000, acc).approved

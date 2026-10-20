from autotrader.models import Position, Side
from autotrader.strategy import MovingAverageCross, build_strategy


def test_golden_cross_buy(make_bars):
    # 하락하다가 마지막에 급등 → 단기선이 장기선을 상향 돌파
    bars = make_bars([10, 9, 8, 7, 6, 5, 20])
    s = MovingAverageCross(short=2, long=5)
    sig = s.generate("A", bars, None)
    assert sig is not None and sig.side == Side.BUY


def test_no_buy_when_holding(make_bars):
    bars = make_bars([10, 9, 8, 7, 6, 5, 20])
    s = MovingAverageCross(short=2, long=5)
    assert s.generate("A", bars, Position("A", 10, 5)) is None


def test_dead_cross_sell_only_when_holding(make_bars):
    bars = make_bars([1, 2, 3, 4, 5, 6, -10])
    s = MovingAverageCross(short=2, long=5)
    assert s.generate("A", bars, None) is None
    sig = s.generate("A", bars, Position("A", 10, 5))
    assert sig is not None and sig.side == Side.SELL


def test_not_enough_bars(make_bars):
    assert MovingAverageCross(2, 5).generate("A", make_bars([1, 2, 3]), None) is None


def test_build_strategy_unknown():
    import pytest

    with pytest.raises(ValueError):
        build_strategy("nope")

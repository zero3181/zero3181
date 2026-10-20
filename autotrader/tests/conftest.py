import pandas as pd
import pytest

from autotrader.broker.base import MarketData


def bars_from_closes(closes: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1000},
        index=idx,
    )


class FakeMarketData(MarketData):
    def __init__(self, bars: dict[str, pd.DataFrame]):
        self.bars = bars

    def get_bars(self, symbol, count):
        return self.bars[symbol].tail(count)

    def get_price(self, symbol):
        return float(self.bars[symbol]["close"].iloc[-1])


@pytest.fixture
def make_bars():
    return bars_from_closes

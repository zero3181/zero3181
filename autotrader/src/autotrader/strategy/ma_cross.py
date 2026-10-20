from __future__ import annotations

import pandas as pd

from autotrader.models import Position, Side, Signal
from autotrader.strategy.base import Strategy


class MovingAverageCross(Strategy):
    """예시 전략: 단기 이동평균이 장기 이동평균을 상향 돌파하면 매수, 하향 돌파하면 매도.

    구조를 보여주기 위한 예시일 뿐, 수익을 보장하지 않는다.
    """

    name = "ma_cross"

    def __init__(self, short: int = 5, long: int = 20):
        if short >= long:
            raise ValueError("short는 long보다 작아야 합니다")
        self.short = short
        self.long = long

    @property
    def min_bars(self) -> int:
        return self.long + 1  # 직전 봉과 비교해야 하므로 +1

    def generate(
        self, symbol: str, bars: pd.DataFrame, position: Position | None
    ) -> Signal | None:
        if len(bars) < self.min_bars:
            return None

        close = bars["close"]
        short_ma = close.rolling(self.short).mean()
        long_ma = close.rolling(self.long).mean()

        prev_diff = short_ma.iloc[-2] - long_ma.iloc[-2]
        curr_diff = short_ma.iloc[-1] - long_ma.iloc[-1]
        holding = position is not None and position.quantity > 0

        if prev_diff <= 0 < curr_diff and not holding:
            return Signal(symbol, Side.BUY, f"골든크로스 MA{self.short}/MA{self.long}")
        if prev_diff >= 0 > curr_diff and holding:
            return Signal(symbol, Side.SELL, f"데드크로스 MA{self.short}/MA{self.long}")
        return None

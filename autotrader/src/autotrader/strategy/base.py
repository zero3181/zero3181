from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from autotrader.models import Position, Signal


class Strategy(ABC):
    """매매 룰의 기본 클래스.

    규칙:
    - `bars`에는 '지금 시점까지'의 데이터만 들어온다. 미래 데이터를 보면 안 된다.
    - 증권사 API를 직접 호출하지 않는다. 그래야 백테스트와 실전에 같은 코드를 쓸 수 있다.
    - 신호(매수/매도)만 낸다. 수량과 한도는 RiskManager가 정한다.
    """

    name: str = "base"

    @property
    @abstractmethod
    def min_bars(self) -> int:
        """신호를 내기 위해 필요한 최소 봉 개수."""

    @abstractmethod
    def generate(
        self, symbol: str, bars: pd.DataFrame, position: Position | None
    ) -> Signal | None:
        """신호가 없으면 None."""
